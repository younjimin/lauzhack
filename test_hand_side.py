"""
test_hand_side.py — checks that the patient's real hand is tracked even when MediaPipe's
"Left"/"Right" hand label is wrong (back of the hand to the camera, low confidence, flicker).

    python test_hand_side.py
"""
import math
import random
import sys

from analyzer import OPPOSITION_SEQUENCE, RehabAnalyzer

W, H, FPS = 640, 480, 30
TIPS = {"index": (250, 200), "middle": (290, 190), "ring": (330, 200), "pinky": (370, 230)}
OPEN_THUMB = (190, 330)


def lm(x, y, vis=0.95):
    return {"x_norm": x / W, "y_norm": y / H, "x_px": int(x), "y_px": int(y), "visibility": vis}


def hand_at(thumb):
    h = {"wrist": lm(300, 400), "middle_finger_mcp": lm(300, 300), "thumb_tip": lm(*thumb)}
    h.update({f"{n}_finger_tip" if n != "pinky" else "pinky_tip": lm(*p) for n, p in TIPS.items()})
    return h


def thumb_path(t):
    """Thumb touches index, middle, ring, pinky, ring, middle … one touch per second."""
    i, u = int(t // 1.0), t % 1.0
    target = TIPS[OPPOSITION_SEQUENCE[i % len(OPPOSITION_SEQUENCE)]]
    if u < 0.3:
        k = u / 0.3
    elif u < 0.5:
        k = 1.0
    elif u < 0.8:
        k = 1 - (u - 0.5) / 0.3
    else:
        k = 0.0
    return (OPEN_THUMB[0] + (target[0] - OPEN_THUMB[0]) * k, OPEN_THUMB[1] + (target[1] - OPEN_THUMB[1]) * k)


def pose_with_wrists():
    """Body in view. Mirrored webcam: the patient's real RIGHT wrist carries MediaPipe's 'left_wrist' label."""
    return {"left_wrist": lm(302, 404), "right_wrist": lm(520, 420)}


def run(label_fn, with_pose, seconds=5.9, side="auto"):
    an = RehabAnalyzer({"exercise": "finger_opposition", "side": side, "reps": 6}, mirrored=True)
    hidden = 0
    for i in range(int(seconds * FPS)):
        t = i / FPS
        data = {"pose": pose_with_wrists() if with_pose else None,
                "hands": {label_fn(i, t): hand_at(thumb_path(t))}}
        r = an.update(data, i * 1000 / FPS, W, H)
        hidden += r["message_key"] == "hidden"
    s = an.finish()
    return s["reps"], s["side"], hidden


results = []
random.seed(1)
cases = [
    ("Label always correct ('Right')", lambda i, t: "Right"),
    ("Label wrong for the first 0.5 s", lambda i, t: "Left" if t < 0.5 else "Right"),
    ("Label flickers on 20% of frames", lambda i, t: "Left" if random.random() < 0.2 else "Right"),
    ("Label always wrong (back of hand)", lambda i, t: "Left"),
]
for name, fn in cases:
    for with_pose in (True, False):
        reps, side, hidden = run(fn, with_pose)
        results.append((name, with_pose, reps, side, hidden))

ok_all = True
print(f"{'case':<36} {'body visible':<13} {'reps':>4}  side   'show hand' frames")
for name, with_pose, reps, side, hidden in results:
    # with the body in view the real (right) hand must always be found;
    # without it only the label is available, so an always-wrong label cannot be detected
    must_pass = with_pose or "always wrong" not in name
    ok = reps == 6 and (side == "right" or not with_pose and "always wrong" in name)
    ok_all &= ok or not must_pass
    flag = "PASS" if ok else ("(expected)" if not must_pass else "FAIL")
    print(f"{name:<36} {str(with_pose):<13} {reps:>4}  {str(side):<6} {hidden:>4}   {flag}")
print("\nALL PASS" if ok_all else "\nSOME FAILED")
sys.exit(0 if ok_all else 1)
