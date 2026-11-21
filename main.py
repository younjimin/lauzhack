"""
Rehab Assistant web app — Flask backend.

Login, SQL storage and patient <-> physiotherapist data exchange: see auth_db.py.
Pages: /login, / (patient mode selector + physical & cognitive screens), /doctor (physiotherapist dashboard).

Supports:
  - Arm curl (left, right, or auto-detected arm — 5 reps)
  - Sequential finger opposition (Index -> Middle -> Ring -> Pinky -> Ring -> Middle — 10 touches)
  - Dual-task mode: hold a posture while answering questions by head tilt (rehab_modes.py, /api/dual/*)
  - Fatigue detection → guided breathing break (pause/resume), shoulder-tension check
"""
import json
import os
import threading
import time

import cv2
from flask import Flask, Response, jsonify, redirect, request, send_from_directory

from analyzer import RehabAnalyzer
from auth_db import current_user, init_auth, login_required, patient_prescriptions, save_session_to_db
from pose_detector import PoseDetector
from rehab_modes import POSTURES, DualTaskSession, FatigueMonitor, shoulder_ratio


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
MODEL_DIR = os.path.join(BASE_DIR, "models")
SESSION_DIR = os.path.join(BASE_DIR, "sessions")

POSE_MODEL = os.path.join(MODEL_DIR, "pose_landmarker_full.task")
HAND_MODEL = os.path.join(MODEL_DIR, "hand_landmarker.task")

VIDEO_SOURCE = os.environ.get("REHAB_VIDEO")
MIRROR = VIDEO_SOURCE is None

PRESCRIPTIONS = {
    "curl": {
        "exercise": "elbow_curl",
        "side": "auto",
        "rest_angle": 160,
        "target_angle": 100,
        "safe_limit": 85,
        "reps": 5,
    },
    "tap": {
        "exercise": "finger_opposition",
        "side": "auto",
        "rest_angle": 90,
        "target_angle": 34,
        "reps": 10,
    },
}

app = Flask(__name__)
init_auth(app, PRESCRIPTIONS, lambda rx: dict(RehabAnalyzer(rx).rx))


# --------------------------------------------------
# SHARED STATE (PHYSICAL MODEL — UNCHANGED)
# --------------------------------------------------

lock = threading.Lock()

camera_thread = None
camera_stop = threading.Event()
latest_frame = None
analyzer = None
session_owner = None
fatigue = None          # FatigueMonitor for the running physical session
session_breaks = []     # breathing breaks taken during the running physical session
dual = None             # DualTaskSession (dual-task mode)
dual_owner = None

tracking = {
    "camera_connected": False,
    "pose_detected": False,
    "hands": 0,
    "angle": None,
    "reps": 0,
    "feedback": "Connect your camera to begin.",
    "exercise": "curl",
    "side": "auto",
    "running": False,
    "partial_reps": 0,
    "target_reps": PRESCRIPTIONS["curl"]["reps"],
    "out_of_range": 0,
    "in_danger": False,
    "state": "REST",
    "progress": 0.0,
    "message_key": None,
    "status": None,
    "min_angle": None,
    "max_angle": None,
    "finger_metrics": None,
    "paused": False,          # breathing break in progress
    "fatigue_alert": None,    # {"id", "reason", "message"} when movement quality drops sharply
    "shoulder_ratio": None,   # neck length / shoulder width (smaller = shoulders raised)
    "dual_active": False,
}


# --------------------------------------------------
# STEP 2: ANALYSE ONE FRAME (PHYSICAL MODEL — UNCHANGED)
# --------------------------------------------------

def process_tracking(data, t_ms, width, height):
    with lock:
        tracking["shoulder_ratio"] = shoulder_ratio(data.get("pose"), width, height)
        if dual is not None and dual.phase not in ("done", "stopped"):
            dual.update(data, t_ms, width, height)          # dual-task mode owns the camera frames
            return None

        hands = data.get("hands") or {}
        uses_hands = PRESCRIPTIONS[tracking["exercise"]]["exercise"] in ("finger_tap", "finger_opposition")
        tracking["pose_detected"] = bool(hands) if uses_hands else data.get("pose") is not None
        tracking["hands"] = len(hands)

        if not tracking["running"] or analyzer is None:
            tracking["angle"] = None
            tracking["finger_metrics"] = None
            tracking["in_danger"] = False
            if tracking["camera_connected"]:
                tracking["feedback"] = "Camera connected. Press Start exercise."
            return None

        if tracking["paused"]:
            tracking["feedback"] = "Paused — breathing break"
            tracking["in_danger"] = False
            return None

        r = analyzer.update(data, t_ms, width, height)
        tracking.update(
            angle=None if r["angle"] is None else round(r["angle"]),
            reps=r["reps"],
            partial_reps=r["partial_reps"],
            target_reps=r["target_reps"],
            out_of_range=r["out_of_range"],
            in_danger=r["in_danger"],
            state=r["state"],
            side=r["side"] or tracking["side"],
            progress=round(r["progress"], 3),
            message_key=r["message_key"],
            status=r["status"],
            min_angle=r["lowest_angle"],
            max_angle=r["highest_angle"],
            feedback=r["message"],
            finger_metrics=r.get("finger_metrics"),
        )
        for e in r["events"]:
            if e["type"] in ("rep", "partial_rep", "missed_touch", "out_of_range", "set_complete", "side_selected"):
                print(f"[{t_ms / 1000:7.2f}s] {e}")
            if fatigue is not None and not r["set_complete"]:
                alert = fatigue.feed(e)
                if alert:
                    tracking["fatigue_alert"] = alert
                    print(f"[{t_ms / 1000:7.2f}s] fatigue: {alert}")
        return r


def draw_overlay(img, r, reps, pose_detected, num_hands):
    h, w = img.shape[:2]
    tracked = f" | Tracking: {r['side'].upper()}" if r is not None and r.get("side") else ""
    cv2.putText(
        img,
        f"Detected: {'Yes' if pose_detected else 'No'} | Hands: {num_hands} | Reps: {reps}{tracked}",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2,
    )

    if r is not None:
        fm = r.get("finger_metrics")
        if fm:
            cv2.putText(
                img,
                f"Target: {fm['target_finger'].upper()} ({fm['sequence_step']}/{fm['sequence_length']}) | Acc: {fm['accuracy_pct']}%",
                (20, 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
            )
        elif r["angle"] is not None:
            side_lbl = f" ({r['side'].upper()})" if r.get("side") else ""
            cv2.putText(
                img,
                f"{r['angle']:.0f} deg{side_lbl}",
                (20, 75),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (255, 255, 255),
                2,
            )

        bw = min(300, w - 40)
        cv2.rectangle(img, (20, 95), (20 + bw, 109), (90, 90, 90), -1)
        cv2.rectangle(img, (20, 95), (20 + int(bw * r["progress"]), 109), (0, 200, 255), -1)
        bad = r["in_danger"] or r["message_key"] in ("stop", "hidden", "pain")
        cv2.rectangle(img, (0, h - 46), (w, h), (30, 30, 30), -1)
        cv2.putText(
            img,
            r["message"],
            (16, h - 16),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.68,
            (60, 60, 255) if bad else (255, 255, 255),
            2,
        )
    return img


def draw_dual_overlay(img, ds):
    h, w = img.shape[:2]
    angle = "--" if ds["angle"] is None else f"{ds['angle']:.0f} deg"
    color = (0, 200, 0) if ds["in_zone"] else (60, 60, 255)
    cv2.putText(img, f"Dual-task | {ds['phase'].upper()} | {angle} (target {ds['zone'][0]:.0f}-{ds['zone'][1]:.0f})",
                (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
    head = ds["head"]
    if head["direction"]:
        cv2.putText(img, f"Head: {head['direction'].upper()} {int(head['progress'] * 100)}%", (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
    cv2.rectangle(img, (0, h - 46), (w, h), (30, 30, 30), -1)
    cv2.putText(img, ds["motor_message"] or "", (16, h - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.68,
                (255, 255, 255) if ds["in_zone"] else (60, 60, 255), 2)
    return img


# --------------------------------------------------
# CAMERA AND MEDIAPIPE THREAD (PHYSICAL MODEL — UNCHANGED)
# --------------------------------------------------

def open_capture():
    if VIDEO_SOURCE:
        return cv2.VideoCapture(VIDEO_SOURCE)
    cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(0)
    return cap


def camera_worker():
    global latest_frame

    cap = open_capture()
    if not cap.isOpened():
        with lock:
            tracking["camera_connected"] = False
            tracking["feedback"] = "Cannot access webcam. Check camera permissions."
        return

    detector = None
    try:
        detector = PoseDetector(pose_model_path=POSE_MODEL, hand_model_path=HAND_MODEL, min_confidence=0.5)
        start_time = time.monotonic()
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_index, last_ts = 0, -1

        with lock:
            tracking["camera_connected"] = True
            tracking["feedback"] = "Camera connected. Choose an exercise and press Start."

        while not camera_stop.is_set():
            success, frame = cap.read()
            if not success:
                if VIDEO_SOURCE:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                time.sleep(0.03)
                continue

            if MIRROR:
                frame = cv2.flip(frame, 1)

            if VIDEO_SOURCE:
                time.sleep(1 / fps)
            timestamp_ms = max(int((time.monotonic() - start_time) * 1000), last_ts + 1)
            last_ts = timestamp_ms
            height, width = frame.shape[:2]

            data = detector.process_frame(frame, timestamp_ms)
            r = process_tracking(data, timestamp_ms, width, height)

            annotated = detector.draw_skeleton(frame, data, vis_threshold=0.5, show_hand_labels=False)
            with lock:
                reps, pose_detected, num_hands = tracking["reps"], tracking["pose_detected"], tracking["hands"]
            with lock:
                ds = dual.state() if dual is not None and dual.phase not in ("done", "stopped") else None
            if ds:
                draw_dual_overlay(annotated, ds)
            else:
                draw_overlay(annotated, r, reps, pose_detected, num_hands)

            ok, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                with lock:
                    latest_frame = buffer.tobytes()
            frame_index += 1

    except Exception as error:
        print("Camera error:", error)
        with lock:
            tracking["feedback"] = f"Tracking error: {error}"

    finally:
        cap.release()
        if detector:
            detector.close()
        with lock:
            tracking["camera_connected"] = False
            tracking["running"] = False
            tracking["feedback"] = "Camera disconnected."


def start_camera():
    global camera_thread
    if camera_thread and camera_thread.is_alive():
        return
    camera_stop.clear()
    camera_thread = threading.Thread(target=camera_worker, daemon=True)
    camera_thread.start()


def stop_camera():
    camera_stop.set()
    if camera_thread and camera_thread.is_alive():
        camera_thread.join(timeout=3)
    with lock:
        tracking["running"] = False
        tracking["camera_connected"] = False


# --------------------------------------------------
# WEBSITE ROUTES
# --------------------------------------------------

@app.route("/login")
def login_page():
    return send_from_directory(FRONTEND_DIR, "login.html")


@app.route("/gem-auth.js")
def gem_auth_js():
    return send_from_directory(FRONTEND_DIR, "gem-auth.js", mimetype="application/javascript")


@app.route("/doctor")
@login_required("doctor")
def doctor_page():
    return send_from_directory(FRONTEND_DIR, "doctor.html")


@app.route("/")
@login_required()
def home():
    if current_user()["role"] == "doctor":
        return redirect("/doctor")
    with open(os.path.join(FRONTEND_DIR, "gem.html"), encoding="utf-8") as f:
        page = f.read()
    tags = ('<script src="/cognitive.js" defer></script>\n<script src="/gem-auth.js" defer></script>\n'
            '<script src="/rehab-modes.js" defer></script>')
    idx = page.lower().rfind("</body>")
    page = page[:idx] + tags + page[idx:] if idx != -1 else page + tags
    return Response(page, mimetype="text/html")


@app.route("/rehab-modes.js")
@login_required()
def rehab_modes_js():
    return send_from_directory(FRONTEND_DIR, "rehab-modes.js", mimetype="application/javascript")


@app.route("/cognitive.js")
@login_required()
def cognitive_js():
    return send_from_directory(FRONTEND_DIR, "cognitive.js", mimetype="application/javascript")


@app.route("/video_feed")
@login_required()
def video_feed():
    def generate():
        while True:
            with lock:
                frame = latest_frame
            if frame is None:
                time.sleep(0.05)
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(0.03)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


# --------------------------------------------------
# API ROUTES (PHYSICAL MODEL — UNCHANGED)
# --------------------------------------------------

@app.route("/api/camera/start", methods=["POST"])
@login_required()
def api_camera_start():
    start_camera()
    return jsonify({"success": True})


@app.route("/api/camera/stop", methods=["POST"])
@login_required()
def api_camera_stop():
    stop_camera()
    return jsonify({"success": True})


@app.route("/api/session/start", methods=["POST"])
@login_required("patient")
def api_session_start():
    global analyzer, session_owner, fatigue, session_breaks
    body = request.get_json(silent=True) or {}
    patient_id = current_user()["id"]
    my_prescriptions = patient_prescriptions(patient_id)

    with lock:
        if not tracking["camera_connected"]:
            return jsonify({"success": False, "error": "Camera is not connected."}), 400
        if dual is not None and dual.phase not in ("done", "stopped"):
            return jsonify({"success": False, "error": "Finish the dual-task session first."}), 409

        exercise = body.get("exercise", tracking["exercise"])
        if exercise not in PRESCRIPTIONS:
            return jsonify({"success": False, "error": f"Unknown exercise '{exercise}'."}), 400

        rx = {k: v for k, v in my_prescriptions[exercise].items() if k != "updated_at"}
        side = body.get("side", rx.get("side", "auto"))
        if side not in ("auto", "left", "right"):
            side = "auto"

        rx = {**rx, "side": side}
        analyzer = RehabAnalyzer(rx, mirrored=MIRROR)
        session_owner = patient_id
        fatigue = FatigueMonitor(analyzer.rx, sequence=analyzer.ex["source"] == "hand_sequence")
        session_breaks = []
        tracking.update(
            exercise=exercise,
            side=side,
            running=True,
            reps=0,
            partial_reps=0,
            out_of_range=0,
            in_danger=False,
            angle=None,
            min_angle=None,
            max_angle=None,
            progress=0.0,
            state="REST",
            target_reps=rx["reps"],
            message_key=None,
            status=None,
            finger_metrics=None,
            paused=False,
            fatigue_alert=None,
        )

    return jsonify({"success": True, "reps": 0, "target_reps": rx["reps"], "prescription": rx})


@app.route("/api/session/stop", methods=["POST"])
@login_required("patient")
def api_session_stop():
    global analyzer, session_owner
    body = request.get_json(silent=True) or {}
    reason = body.get("reason", "manual")

    with lock:
        tracking["running"] = False
        tracking["in_danger"] = False
        tracking["paused"] = False
        tracking["fatigue_alert"] = None
        if analyzer is None:
            return jsonify({"success": True, "reps": tracking["reps"], "min_angle": None, "summary": None})
        if reason == "pain":
            analyzer.report_pain()
        summary = analyzer.finish()
        summary.update(
            ui_exercise=tracking["exercise"],
            ended_by=reason,
            saved_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            breaks=list(session_breaks),
        )
        tracking["reps"] = summary["reps"]
        owner = session_owner or current_user()["id"]
        analyzer, session_owner = None, None

    session_id = save_session_to_db(owner, summary)

    os.makedirs(SESSION_DIR, exist_ok=True)
    path = os.path.join(SESSION_DIR, f"session_{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)

    return jsonify({
        "success": True,
        "reps": summary["reps"],
        "min_angle": summary["lowest_angle"],
        "session_id": session_id,
        "summary": summary,
    })


# --------------------------------------------------
# BREATHING BREAK: PAUSE / RESUME A PHYSICAL SESSION
# --------------------------------------------------

@app.route("/api/session/pause", methods=["POST"])
@login_required("patient")
def api_session_pause():
    body = request.get_json(silent=True) or {}
    with lock:
        if not tracking["running"] or analyzer is None:
            return jsonify({"success": False, "error": "No exercise is running."}), 400
        if not tracking["paused"]:
            tracking["paused"] = True
            session_breaks.append({"trigger": str(body.get("trigger", "manual"))[:20],
                                   "reason": (tracking["fatigue_alert"] or {}).get("reason"),
                                   "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        tracking["fatigue_alert"] = None
    return jsonify({"success": True})


@app.route("/api/session/resume", methods=["POST"])
@login_required("patient")
def api_session_resume():
    body = request.get_json(silent=True) or {}
    with lock:
        if analyzer is None:
            return jsonify({"success": False, "error": "No exercise is running."}), 400
        if tracking["paused"] and session_breaks:
            session_breaks[-1]["completed"] = bool(body.get("completed", True))
            session_breaks[-1]["seconds"] = body.get("seconds")
        tracking["paused"] = False
    return jsonify({"success": True})


# --------------------------------------------------
# DUAL-TASK MODE (hold a posture + answer questions)
# --------------------------------------------------

@app.route("/api/dual/start", methods=["POST"])
@login_required("patient")
def api_dual_start():
    global dual, dual_owner
    body = request.get_json(silent=True) or {}
    patient_id = current_user()["id"]
    my_rx = patient_prescriptions(patient_id)
    posture = body.get("posture", "curl_hold")
    if posture not in POSTURES:
        return jsonify({"success": False, "error": f"Unknown posture '{posture}'."}), 400
    rx = dict(my_rx["curl"]) if posture == "curl_hold" else {}
    side = body.get("side", rx.get("side", "auto"))
    rx["side"] = side if side in ("auto", "left", "right") else "auto"
    try:
        session = DualTaskSession(
            posture, rx, n_questions=int(body.get("questions", 6)),
            baseline_sec=float(body.get("baseline_sec", 10)), question_sec=float(body.get("question_sec", 8)),
            hold_ms=int(body.get("hold_ms", 1200)), level=int(body.get("level", 1)), mirrored=MIRROR)
    except (ValueError, TypeError) as error:
        return jsonify({"success": False, "error": str(error)}), 400

    with lock:
        if not tracking["camera_connected"]:
            return jsonify({"success": False, "error": "Camera is not connected."}), 400
        if tracking["running"]:
            return jsonify({"success": False, "error": "Finish the current exercise first."}), 409
        dual, dual_owner = session, patient_id
        tracking["dual_active"] = True
        state = dual.state()
    return jsonify({"success": True, "state": state})


@app.route("/api/dual/state")
@login_required()
def api_dual_state():
    with lock:
        return jsonify({"state": dual.state() if dual is not None else None})


@app.route("/api/dual/answer", methods=["POST"])
@login_required("patient")
def api_dual_answer():
    choice = (request.get_json(silent=True) or {}).get("choice")
    if choice not in ("left", "right", 0, 1):
        return jsonify({"success": False, "error": "choice must be 'left' or 'right'."}), 400
    with lock:
        ok = dual is not None and dual.answer(choice, via="click")
        state = dual.state() if dual is not None else None
    return jsonify({"success": bool(ok), "state": state})


@app.route("/api/dual/stop", methods=["POST"])
@login_required("patient")
def api_dual_stop():
    global dual, dual_owner
    reason = (request.get_json(silent=True) or {}).get("reason", "manual")
    with lock:
        if dual is None:
            return jsonify({"success": True, "summary": None})
        summary = dual.finish(reason)
        summary["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        owner = dual_owner or current_user()["id"]
        dual, dual_owner = None, None
        tracking["dual_active"] = False

    session_id = save_session_to_db(owner, summary)
    os.makedirs(SESSION_DIR, exist_ok=True)
    with open(os.path.join(SESSION_DIR, f"session_{time.strftime('%Y%m%d_%H%M%S')}_dual.json"), "w") as f:
        json.dump(summary, f, indent=2)
    return jsonify({"success": True, "session_id": session_id, "summary": summary})


@app.route("/api/tracking")
@login_required()
def api_tracking():
    with lock:
        result = dict(tracking)
    return jsonify(result)


if __name__ == "__main__":
    print("GEM backend starting...")
    print("Open http://127.0.0.1:5000/login in your browser.")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True, use_reloader=False)