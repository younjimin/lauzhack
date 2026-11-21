"""
test_analyzer_py.py — checks that analyzer.py gives the same results as analyzer.js.

Uses the frame files written by `node test_analyzer.js --dump` (in ../step2/out/ or a
folder given as the first argument). Frames are converted into Person 1's
PoseDetector format ({"left_shoulder": {"x_norm", "y_norm", "x_px", ...}}) so the
real adapter path is tested.

    python3 test_analyzer_py.py [path/to/out]
"""
import glob
import json
import os
import sys

from analyzer import POSE_LANDMARK_NAMES, RehabAnalyzer

folder = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "step2", "out")
files = sorted(glob.glob(os.path.join(folder, "*.frames.json")))
if not files:
    sys.exit(f"No *.frames.json in {folder}. Run: node test_analyzer.js --dump")


def to_person1_format(landmarks, width, height):
    """MediaPipe list → the dict PoseDetector.process_frame() returns under 'pose'."""
    return {
        POSE_LANDMARK_NAMES[i]: {
            "id": i, "x_norm": p["x"], "y_norm": p["y"], "z_norm": 0.0,
            "x_px": int(p["x"] * width), "y_px": int(p["y"] * height),
            "visibility": p.get("visibility", 1.0),
        }
        for i, p in enumerate(landmarks)
    }


fails = 0
for f in files:
    d = json.load(open(f))
    an = RehabAnalyzer(d["rx"])
    for fr in d["frames"]:
        an.update(to_person1_format(fr["landmarks"], fr["width"], fr["height"]), fr["t"], fr["width"], fr["height"])
    py, js = an.finish(d["finishT"]), d["summary"]
    pairs = [("reps", "reps"), ("partial_reps", "partialReps"), ("out_of_range", "outOfRange"), ("side", "side")]
    diffs = [f"{a}: py={py[a]} js={js[b]}" for a, b in pairs if py[a] != js[b]]
    if abs((py["max_angle"] or 0) - (js["maxAngle"] or 0)) > 0.2:
        diffs.append(f"max_angle: py={py['max_angle']} js={js['maxAngle']}")
    py_ev = [e["type"] for e in py["events"]]
    js_ev = [e["type"] for e in js["events"]]
    if py_ev != js_ev:
        diffs.append(f"events differ ({len(py_ev)} vs {len(js_ev)})")
    name = os.path.basename(f).replace(".frames.json", "")
    print(f"{'PASS' if not diffs else 'FAIL'}  {name:<20} reps={py['reps']} partial={py['partial_reps']} "
          f"oor={py['out_of_range']} max={py['max_angle']}  {'; '.join(diffs)}")
    fails += bool(diffs)

print(f"\n{len(files) - fails}/{len(files)} scenarios match analyzer.js")
sys.exit(1 if fails else 0)
