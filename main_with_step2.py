"""
main_with_step2.py — Step 1 + Step 2 debug runner in an OpenCV window (no web server).
The web app is main.py; use this to tune thresholds or measure accuracy on test videos.

    python main_with_step2.py                                   # webcam, side arm raise
    python main_with_step2.py --exercise finger_opposition
    python main_with_step2.py --exercise seated_knee_extension --side left
    python main_with_step2.py --video test.mp4 --expected 10    # test video, compare with true count
    python main_with_step2.py --video test.mp4 --dump frames.json   # save frames for run_frames.js / re-runs

Keys in the window:  q = finish & save   p = pain (stop)   c = continue after pain   r = reset

At the end the session result is printed and saved to session_<time>.json
(this is what Step 3/4 will store and show on the dashboard).
"""
import argparse
import json
import time

import cv2

from analyzer import EXERCISES, RehabAnalyzer
from pose_detector import PoseDetector


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exercise", default="side_arm_raise", choices=list(EXERCISES))
    ap.add_argument("--side", default="auto", choices=["auto", "left", "right"])
    ap.add_argument("--rest", dest="rest_angle", type=float, help="resting angle (default per exercise)")
    ap.add_argument("--target", dest="target_angle", type=float, help="target angle")
    ap.add_argument("--safe", dest="safe_limit", type=float, help="safe limit")
    ap.add_argument("--reps", type=int, help="prescribed reps")
    ap.add_argument("--video", help="test video file instead of the webcam")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--expected", type=int, help="true rep count of the test video")
    ap.add_argument("--dump", help="save every frame's pose to this JSON file")
    ap.add_argument("--no-window", action="store_true", help="run without showing a window")
    return ap.parse_args()


def draw_overlay(img, r):
    """Step 2 output on top of Person 1's skeleton (debug view, not the final patient UI)."""
    h, w = img.shape[:2]
    bad = r["message_key"] in ("stop", "hidden", "pain")
    color = (60, 60, 255) if bad else (255, 255, 255)
    angle = "--" if r["angle"] is None else f"{r['angle']:.0f} deg"
    cv2.putText(img, angle, (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3)
    cv2.putText(img, f"target {r['thresholds']['target']:.0f} | safe {r['thresholds']['safe_limit']:.0f}",
                (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 1)
    cv2.putText(img, f"Reps {r['reps']}/{r['target_reps']}  partial {r['partial_reps']}  out-of-range {r['out_of_range']}",
                (20, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(img, f"{r['state']}  side={r['side']}", (20, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
    # progress gauge
    x0, y0, bw = 20, 180, min(300, w - 40)
    cv2.rectangle(img, (x0, y0), (x0 + bw, y0 + 14), (90, 90, 90), -1)
    cv2.rectangle(img, (x0, y0), (x0 + int(bw * r["progress"]), y0 + 14), (0, 200, 255), -1)
    # feedback message
    cv2.rectangle(img, (0, h - 50), (w, h), (30, 30, 30), -1)
    cv2.putText(img, r["message"], (20, h - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    return img


def main():
    args = parse_args()
    rx = {"exercise": args.exercise, "side": args.side}
    for k in ("rest_angle", "target_angle", "safe_limit", "reps"):
        if getattr(args, k) is not None:
            rx[k] = getattr(args, k)

    use_video = bool(args.video)
    cap = cv2.VideoCapture(args.video if use_video else args.camera)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open {'video ' + args.video if use_video else 'webcam'}.")

    detector = PoseDetector(pose_model_path="models/pose_landmarker_full.task",
                            hand_model_path="models/hand_landmarker.task", min_confidence=0.5)
    # The webcam image is flipped before detection, so left/right labels must be swapped back.
    analyzer = RehabAnalyzer(rx, mirrored=not use_video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    start_ms = int(time.time() * 1000)
    frame_idx, last_t, dumped = 0, 0, []
    print(f"{EXERCISES[args.exercise]['label']} | q = finish  p = pain  c = continue  r = reset")

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            if use_video:
                t = int(frame_idx * 1000 / fps)              # video time, independent of processing speed
            else:
                frame = cv2.flip(frame, 1)                   # mirror like main.py
                t = int(time.time() * 1000) - start_ms
            t = max(t, last_t + 1)                           # MediaPipe needs increasing timestamps
            last_t = t
            h, w = frame.shape[:2]

            tracking = detector.process_frame(frame, t)                 # Step 1
            r = analyzer.update(tracking, t, w, h)                      # Step 2
            for e in r["events"]:
                if e["type"] in ("rep", "partial_rep", "out_of_range", "hidden", "set_complete", "side_selected"):
                    print(f"[{t / 1000:6.2f}s] {e}")
            if args.dump:
                pose = tracking["pose"]
                lms = None if pose is None else [
                    {"x": p["x_norm"], "y": p["y_norm"], "visibility": p["visibility"]}
                    for p in sorted(pose.values(), key=lambda p: p["id"])]
                dumped.append({"t": t, "width": w, "height": h, "landmarks": lms})

            if not args.no_window:
                img = detector.draw_skeleton(frame, tracking, vis_threshold=0.5)
                cv2.imshow("ability+ debug - Step 1 + Step 2", draw_overlay(img, r))
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("p"):
                    analyzer.report_pain(t)
                if key == ord("c"):
                    analyzer.resume(t)
                if key == ord("r"):
                    analyzer.reset()
            frame_idx += 1
    finally:
        summary = analyzer.finish(last_t)
        cap.release()
        detector.close()
        cv2.destroyAllWindows()

    summary.pop("events", None)
    print(json.dumps(summary, indent=2))
    if args.expected is not None:
        err = summary["reps"] - args.expected
        print(f"Expected {args.expected} reps -> error {err:+d} ({'OK' if abs(err) <= 1 else 'check the thresholds'})")
    out = f"session_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Saved {out}")
    if args.dump:
        with open(args.dump, "w") as f:
            json.dump(dumped, f)
        print(f"Saved {len(dumped)} frames to {args.dump}")


if __name__ == "__main__":
    main()
