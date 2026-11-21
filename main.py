"""
Rehab Assistant web app — Flask backend.

Step 1  pose_detector.py   webcam → body + hand landmarks
Step 2  analyzer.py        landmarks → angle, reps, safety, feedback, session summary
Step 3  frontend/gem.html  patient screen (polls /api/tracking)

Run:   python main.py          then open http://127.0.0.1:5000
Test without a webcam:  REHAB_VIDEO=test.mp4 python main.py   (plays a video file instead)
"""
import json
import os
import threading
import time

import cv2
from flask import Flask, Response, jsonify, request, send_from_directory

from analyzer import RehabAnalyzer
from pose_detector import PoseDetector


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
MODEL_DIR = os.path.join(BASE_DIR, "models")
SESSION_DIR = os.path.join(BASE_DIR, "sessions")

POSE_MODEL = os.path.join(MODEL_DIR, "pose_landmarker_full.task")
HAND_MODEL = os.path.join(MODEL_DIR, "hand_landmarker.task")

VIDEO_SOURCE = os.environ.get("REHAB_VIDEO")   # None = webcam
MIRROR = VIDEO_SOURCE is None                  # the webcam image is flipped like a mirror

# Prescriptions for the exercises in the patient screen (keys match the <select> values).
# Later these come from the therapist (Step 4 / Step 5).
PRESCRIPTIONS = {
    "curl": {"exercise": "elbow_curl", "side": "right",
             "rest_angle": 160, "target_angle": 100, "safe_limit": 85, "reps": 10},
    "tap": {"exercise": "finger_tap", "side": "auto",
            "rest_angle": 90, "target_angle": 45, "reps": 20},
}

app = Flask(__name__)


# --------------------------------------------------
# SHARED STATE
# --------------------------------------------------

lock = threading.Lock()

camera_thread = None
camera_stop = threading.Event()
latest_frame = None
analyzer = None          # RehabAnalyzer for the running session (Step 2)

tracking = {
    "camera_connected": False,
    "pose_detected": False,
    "hands": 0,
    "angle": None,
    "reps": 0,
    "feedback": "Connect your camera to begin.",
    "exercise": "curl",
    "running": False,
    # from Step 2
    "partial_reps": 0,
    "target_reps": PRESCRIPTIONS["curl"]["reps"],
    "out_of_range": 0,
    "in_danger": False,
    "state": "REST",
    "progress": 0.0,
    "message_key": None,
    "status": None,
    "min_angle": None,   # lowest angle this session (shown as "LOWEST ANGLE")
    "max_angle": None,
}


# --------------------------------------------------
# STEP 2: ANALYSE ONE FRAME
# --------------------------------------------------

def process_tracking(data, t_ms, width, height):
    """Feed one frame of Step 1 data to the analyzer and update the shared state.
    Returns the analyzer result (or None when no session is running)."""
    with lock:
        hands = data.get("hands") or {}
        uses_hands = PRESCRIPTIONS[tracking["exercise"]]["exercise"] == "finger_tap"
        tracking["pose_detected"] = bool(hands) if uses_hands else data.get("pose") is not None
        tracking["hands"] = len(hands)

        if not tracking["running"] or analyzer is None:
            tracking["angle"] = None
            if tracking["camera_connected"]:
                tracking["feedback"] = "Camera connected. Press Start exercise."
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
            progress=round(r["progress"], 3),
            message_key=r["message_key"],
            status=r["status"],
            min_angle=r["lowest_angle"],
            max_angle=r["highest_angle"],
            feedback=r["message"],
        )
        for e in r["events"]:
            if e["type"] in ("rep", "partial_rep", "out_of_range", "set_complete", "side_selected"):
                print(f"[{t_ms / 1000:7.2f}s] {e}")
        return r


def draw_overlay(img, r, reps, pose_detected, num_hands):
    """Status text on the video feed."""
    h, w = img.shape[:2]
    cv2.putText(img, f"Body: {'Detected' if pose_detected else 'Not detected'}", (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(img, f"Hands: {num_hands} | Reps: {reps}", (20, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    if r is not None:
        if r["angle"] is not None:
            cv2.putText(img, f"{r['angle']:.0f} deg", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        bw = min(300, w - 40)
        cv2.rectangle(img, (20, 125), (20 + bw, 139), (90, 90, 90), -1)
        cv2.rectangle(img, (20, 125), (20 + int(bw * r["progress"]), 139), (0, 200, 255), -1)
        bad = r["message_key"] in ("stop", "hidden", "pain")
        cv2.rectangle(img, (0, h - 46), (w, h), (30, 30, 30), -1)
        cv2.putText(img, r["message"], (16, h - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (60, 60, 255) if bad else (255, 255, 255), 2)
    return img


# --------------------------------------------------
# CAMERA AND MEDIAPIPE THREAD (Step 1)
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
            tracking["feedback"] = "Cannot access webcam. Check macOS camera permissions."
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
                if VIDEO_SOURCE:                      # loop the test video
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                time.sleep(0.03)
                continue

            if MIRROR:
                frame = cv2.flip(frame, 1)            # mirror webcam

            if VIDEO_SOURCE:
                time.sleep(1 / fps)                   # play at real speed
            timestamp_ms = max(int((time.monotonic() - start_time) * 1000), last_ts + 1)
            last_ts = timestamp_ms
            height, width = frame.shape[:2]

            data = detector.process_frame(frame, timestamp_ms)                 # Step 1
            r = process_tracking(data, timestamp_ms, width, height)            # Step 2

            annotated = detector.draw_skeleton(frame, data, vis_threshold=0.5)
            with lock:
                reps, pose_detected, num_hands = tracking["reps"], tracking["pose_detected"], tracking["hands"]
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


# --------------------------------------------------
# CAMERA CONTROL
# --------------------------------------------------

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

@app.route("/")
def home():
    return send_from_directory(FRONTEND_DIR, "gem.html")


@app.route("/video_feed")
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
# API ROUTES
# --------------------------------------------------

@app.route("/api/camera/start", methods=["POST"])
def api_camera_start():
    start_camera()
    return jsonify({"success": True})


@app.route("/api/camera/stop", methods=["POST"])
def api_camera_stop():
    stop_camera()
    return jsonify({"success": True})


@app.route("/api/session/start", methods=["POST"])
def api_session_start():
    global analyzer
    body = request.get_json(silent=True) or {}

    with lock:
        if not tracking["camera_connected"]:
            return jsonify({"success": False, "error": "Camera is not connected."}), 400

        exercise = body.get("exercise", tracking["exercise"])
        if exercise not in PRESCRIPTIONS:
            return jsonify({"success": False, "error": f"Unknown exercise '{exercise}'."}), 400

        rx = PRESCRIPTIONS[exercise]
        analyzer = RehabAnalyzer(rx, mirrored=MIRROR)
        tracking.update(exercise=exercise, running=True, reps=0, partial_reps=0, out_of_range=0,
                        in_danger=False, angle=None, min_angle=None, max_angle=None, progress=0.0,
                        state="REST", target_reps=rx["reps"], message_key=None, status=None)

    return jsonify({"success": True, "reps": 0, "target_reps": rx["reps"], "prescription": rx})


@app.route("/api/session/stop", methods=["POST"])
def api_session_stop():
    body = request.get_json(silent=True) or {}
    reason = body.get("reason", "manual")       # 'manual' | 'pain' | 'completed'

    with lock:
        tracking["running"] = False
        if analyzer is None:
            return jsonify({"success": True, "reps": tracking["reps"], "min_angle": None, "summary": None})
        if reason == "pain":
            analyzer.report_pain()
        summary = analyzer.finish()
        summary.update(ui_exercise=tracking["exercise"], ended_by=reason,
                       saved_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        tracking["reps"] = summary["reps"]

    # Save the session result (Step 4 can read these, or replace this with a database insert)
    os.makedirs(SESSION_DIR, exist_ok=True)
    path = os.path.join(SESSION_DIR, f"session_{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)

    return jsonify({"success": True, "reps": summary["reps"], "min_angle": summary["lowest_angle"],
                    "summary": summary})


@app.route("/api/tracking")
def api_tracking():
    with lock:
        result = dict(tracking)
    return jsonify(result)


# --------------------------------------------------
# START SERVER
# --------------------------------------------------

if __name__ == "__main__":
    print("GEM backend starting...")
    print("Open http://127.0.0.1:5000 in your browser.")
    if VIDEO_SOURCE:
        print(f"Using test video instead of the webcam: {VIDEO_SOURCE}")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True, use_reloader=False)
