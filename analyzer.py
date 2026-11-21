"""
analyzer.py — Rehab Assistant, Step 2 (exercise logic), Python version.

Same logic as analyzer.js, written to plug straight into Person 1's
PoseDetector.process_frame() output.

    from analyzer import RehabAnalyzer
    an = RehabAnalyzer({"exercise": "side_arm_raise", "side": "auto",
                        "min_angle": 15, "target_angle": 90, "safe_max": 120, "reps": 10},
                       mirrored=True)          # main.py flips the webcam image
    r = an.update(tracking_data["pose"], timestamp_ms, width, height)
    # r["angle"], r["state"], r["reps"], r["partial_reps"], r["message"], r["events"] ...
    an.report_pain(timestamp_ms)               # pain button / key
    summary = an.finish(timestamp_ms)          # session result (dict, JSON-serialisable)

Pose input can be either
  * Person 1's dict:  {"left_shoulder": {"x_norm", "y_norm", "visibility", ...}, ...}
  * MediaPipe list:   [{"x", "y", "visibility"}, ...] (33 items, index order)
  * None              (no person detected)

About `mirrored`: main.py calls cv2.flip(frame, 1) BEFORE detection, so MediaPipe's
"left"/"right" labels refer to the mirrored body. mirrored=True swaps them back, so
side="right" means the patient's real right side. Check once: raise your right arm
and confirm the analyzer reports side "right".
"""
from __future__ import annotations

import math
from typing import Any

POSE_LANDMARK_NAMES = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky",
    "left_index", "right_index", "left_thumb", "right_thumb",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel",
    "left_foot_index", "right_foot_index",
]

# joints: (A, B, C) — angle measured at B
EXERCISES: dict[str, dict[str, Any]] = {
    "side_arm_raise": {
        "label": "Side arm raise", "view": "front", "body_part": "arm",
        "joints": {"left": ("left_hip", "left_shoulder", "left_elbow"),
                   "right": ("right_hip", "right_shoulder", "right_elbow")},
        "defaults": {"min_angle": 15, "target_angle": 90, "safe_max": 120, "reps": 10},
        "messages": {"raise": "Raise your arm a bit more",
                     "lower": "Good, now lower slowly",
                     "partial": "Nearly there - try to reach the target next time"},
    },
    "seated_knee_extension": {
        "label": "Seated knee extension", "view": "side", "body_part": "leg",
        "joints": {"left": ("left_hip", "left_knee", "left_ankle"),
                   "right": ("right_hip", "right_knee", "right_ankle")},
        # a 3-point angle cannot exceed 180°, so safe_max 180 never triggers
        "defaults": {"min_angle": 90, "target_angle": 160, "safe_max": 180, "reps": 10},
        "messages": {"raise": "Straighten your knee a bit more",
                     "lower": "Good, now bend it back slowly",
                     "partial": "Nearly there - try to straighten a little further next time"},
    },
}

DEFAULTS = {
    "smoothing_alpha": 0.4,          # EMA weight at 30 fps (adjusted for other frame rates)
    "visibility_threshold": 0.5,
    "hidden_grace_sec": 0.3,
    "start_fraction": 0.2,           # rep starts at min + 20% of the range
    "hysteresis_deg": 5,             # rep ends 5° below the start threshold
    "target_tolerance_deg": 3,       # target reached at target − 3°
    "min_rep_sec": 0.5,
    "min_partial_amplitude_deg": 10,
    "max_jump_deg": 35,
    "max_rejected_frames": 3,
    "safe_frames": 3,
    "safe_release_deg": 3,
    "message_hold_sec": 1.0,
    "partial_message_sec": 2.0,
}

MSG_PRIO = {"pain": 4, "stop": 3, "hidden": 2, "done": 1, "raise": 1, "lower": 1,
            "partial": 1, "ready": 0, "start": 0, "rest_first": 0}


def _msg_text(key: str, ex: dict) -> str:
    return {
        "pain": "Exercise stopped. Take a rest.",
        "stop": "Stop - that is beyond your safe range",
        "hidden": f"Please make sure your whole {ex['body_part']} is visible",
        "done": "Set complete - well done!",
        "ready": "Good. Ready for the next one",
        "start": "Get ready - start when you are ready",
        "rest_first": f"Start from the resting position - lower your {ex['body_part']} first",
    }.get(key) or ex["messages"][key]


def _r1(x):
    return None if x is None else round(x * 10) / 10


# ---------------- reusable helpers (also for Step 5) ----------------
def compute_angle(a, b, c, width: float = 1, height: float = 1):
    """Angle at b in degrees. a, b, c are (x, y). Pass width/height for normalised coords."""
    ax, ay = (a[0] - b[0]) * width, (a[1] - b[1]) * height
    cx, cy = (c[0] - b[0]) * width, (c[1] - b[1]) * height
    na, nc = math.hypot(ax, ay), math.hypot(cx, cy)
    if not na or not nc:
        return None
    cos = max(-1.0, min(1.0, (ax * cx + ay * cy) / (na * nc)))
    return math.degrees(math.acos(cos))


class Smoother:
    """Exponential moving average that behaves the same at any frame rate."""

    def __init__(self, alpha: float = 0.4, ref_frame_ms: float = 1000 / 30):
        self.alpha, self.ref, self.value = alpha, ref_frame_ms, None

    def push(self, x: float, dt_ms: float | None = None) -> float:
        if self.value is None:
            self.value = x
            return x
        dt = self.ref if dt_ms is None else max(dt_ms, 1)
        a = 1 - (1 - self.alpha) ** (dt / self.ref)
        self.value += a * (x - self.value)
        return self.value

    def reset(self):
        self.value = None


def percentile(values, p: float):
    v = sorted(x for x in values if x is not None and math.isfinite(x))
    if not v:
        return None
    i = (len(v) - 1) * p
    lo, hi = math.floor(i), math.ceil(i)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def prescription_from_demo(exercise: str, angles, margin_deg: float = 10, reps: int = 10, side: str = "auto") -> dict:
    """Step 5: angles recorded while the therapist demonstrates → prescription draft."""
    lo, hi = percentile(angles, 0.05), percentile(angles, 0.95)
    if lo is None:
        raise ValueError("No angles recorded")
    return {"exercise": exercise, "side": side, "reps": reps, "min_angle": round(lo),
            "target_angle": round(hi), "safe_max": min(180, round(hi + margin_deg))}


def _point(pose, name: str):
    """(x, y, visibility) from Person 1's dict or a MediaPipe-style list; None if missing."""
    if pose is None:
        return None
    if isinstance(pose, dict):
        p = pose.get(name)
        if p is None:
            return None
        x = p.get("x_norm", p.get("x"))
        y = p.get("y_norm", p.get("y"))
    else:
        i = POSE_LANDMARK_NAMES.index(name)
        if i >= len(pose) or pose[i] is None:
            return None
        p = pose[i]
        x, y = p.get("x"), p.get("y")
    vis = p.get("visibility", 1.0)
    return (x, y, 1.0 if vis is None else vis)


# ---------------- the analyzer ----------------
class RehabAnalyzer:
    def __init__(self, prescription: dict, mirrored: bool = False, **options):
        # accept the camelCase keys used by analyzer.js too (minAngle → min_angle …)
        alias = {"minAngle": "min_angle", "targetAngle": "target_angle", "safeMax": "safe_max"}
        prescription = {alias.get(k, k): v for k, v in prescription.items()}
        ex = EXERCISES.get(prescription.get("exercise"))
        if ex is None:
            raise ValueError(f"Unknown exercise {prescription.get('exercise')!r}. Known: {', '.join(EXERCISES)}")
        rx = {"side": "auto", **ex["defaults"], **prescription}
        self._validate(rx)
        unknown = set(options) - set(DEFAULTS)
        if unknown:
            raise ValueError(f"Unknown options: {unknown}")
        self.ex, self.rx, self.o = ex, rx, {**DEFAULTS, **options}
        self.mirrored = mirrored
        o = self.o
        self.range = rx["target_angle"] - rx["min_angle"]
        start = rx["min_angle"] + o["start_fraction"] * self.range
        self.th = {"start": start, "end": start - o["hysteresis_deg"],
                   "reach": rx["target_angle"] - o["target_tolerance_deg"]}
        self.smoother = Smoother(o["smoothing_alpha"])
        self.reset()

    @staticmethod
    def _validate(rx):
        lo, tg, sm = rx["min_angle"], rx["target_angle"], rx["safe_max"]
        if not all(isinstance(v, (int, float)) for v in (lo, tg, sm)):
            raise ValueError("min_angle, target_angle and safe_max must be numbers")
        if not lo < tg:
            raise ValueError("min_angle must be smaller than target_angle")
        if not tg <= sm:
            raise ValueError("target_angle must not exceed safe_max")
        if not rx["reps"] >= 1:
            raise ValueError("reps must be at least 1")
        if rx["side"] not in ("left", "right", "auto"):
            raise ValueError("side must be 'left', 'right' or 'auto'")

    def reset(self):
        self.smoother.reset()
        rx = self.rx
        self.s = dict(
            state="REST", armed=False, side=None if rx["side"] == "auto" else rx["side"],
            raw=None, rejected=0, reps=0, partial_reps=0, out_of_range=0, max_angle=None,
            rep_peak=0.0, rep_start_t=0.0, rep_log=[], over_count=0, latched=False,
            hidden_since=None, hidden=False, first_t=None, last_t=None, active_ms=0.0,
            pain=False, pain_at=None, stopped=False, set_complete=False, flash=None,
            msg={"key": None, "text": "", "prio": -1, "since": -math.inf}, log=[],
        )

    # ---- internals ----
    def _label_side(self, side: str) -> str:
        """Patient side → MediaPipe label (swapped if the image was mirrored)."""
        if not self.mirrored:
            return side
        return "left" if side == "right" else "right"

    def _emit(self, events, e):
        events.append(e)
        self.s["log"].append(e)

    def _pick_side(self, pose):
        if pose is None:
            return None
        def vis(side):
            total = 0.0
            for name in self.ex["joints"][self._label_side(side)]:
                p = _point(pose, name)
                total += p[2] if p else 0.0
            return total
        l, r = vis("left"), vis("right")
        if max(l, r) < 3 * self.o["visibility_threshold"]:
            return None
        return "left" if l > r else "right"

    def _end_rep(self, full: bool, t: float, events):
        s, o = self.s, self.o
        dur = (t - s["rep_start_t"]) / 1000
        peak = _r1(s["rep_peak"])
        s["state"] = "REST"
        if dur < o["min_rep_sec"]:
            self._emit(events, {"type": "rep_ignored", "t": t, "reason": "too_short", "peak": peak, "duration_sec": _r1(dur)})
            return
        if full:
            s["reps"] += 1
            s["rep_log"].append({"n": s["reps"] + s["partial_reps"], "type": "full", "peak": peak, "duration_sec": _r1(dur), "t": t})
            self._emit(events, {"type": "rep", "t": t, "count": s["reps"], "peak": peak, "duration_sec": _r1(dur)})
            if not s["set_complete"] and s["reps"] >= self.rx["reps"]:
                s["set_complete"] = True
                self._emit(events, {"type": "set_complete", "t": t, "reps": s["reps"]})
        elif s["rep_peak"] - self.th["start"] >= o["min_partial_amplitude_deg"]:
            s["partial_reps"] += 1
            s["rep_log"].append({"n": s["reps"] + s["partial_reps"], "type": "partial", "peak": peak, "duration_sec": _r1(dur), "t": t})
            self._emit(events, {"type": "partial_rep", "t": t, "count": s["partial_reps"], "peak": peak, "duration_sec": _r1(dur)})
            s["flash"] = {"key": "partial", "until": t + o["partial_message_sec"] * 1000}
        else:
            self._emit(events, {"type": "rep_ignored", "t": t, "reason": "too_small", "peak": peak, "duration_sec": _r1(dur)})

    def _choose_message(self, status: str, t: float) -> str:
        s = self.s
        if s["stopped"]:
            return "pain"
        if s["latched"]:
            return "stop"
        if status == "hidden":
            return "hidden"
        if s["state"] == "RAISING":
            return "raise"
        if s["state"] == "TOP":
            return "lower"
        if s["flash"] and t < s["flash"]["until"]:
            return s["flash"]["key"]
        if s["set_complete"]:
            return "done"
        if not s["armed"]:
            return "rest_first"
        return "ready" if s["reps"] + s["partial_reps"] > 0 else "start"

    def _apply_message(self, key: str, t: float):
        m = self.s["msg"]
        if key == m["key"]:
            return
        held = t - m["since"] >= self.o["message_hold_sec"] * 1000
        if MSG_PRIO[key] > m["prio"] or held or m["key"] is None:
            self.s["msg"] = {"key": key, "text": _msg_text(key, self.ex), "prio": MSG_PRIO[key], "since": t}

    def _result(self, status: str, t, events):
        s, rx = self.s, self.rx
        if t is not None:
            self._apply_message(self._choose_message(status, t), t)
        a = self.smoother.value
        return {
            "status": status,                  # 'ok' | 'hidden' | 'stopped' | 'waiting'
            "angle": _r1(a), "raw_angle": _r1(s["raw"]),
            "state": s["state"], "side": s["side"],
            "reps": s["reps"], "partial_reps": s["partial_reps"], "target_reps": rx["reps"],
            "out_of_range": s["out_of_range"], "in_danger": s["latched"],
            "set_complete": s["set_complete"],
            "progress": 0.0 if a is None else max(0.0, min(1.0, (a - rx["min_angle"]) / self.range)),
            "thresholds": {"start": _r1(self.th["start"]), "end": _r1(self.th["end"]), "reach": _r1(self.th["reach"]),
                           "target": rx["target_angle"], "safe_max": rx["safe_max"]},
            "message": s["msg"]["text"], "message_key": s["msg"]["key"],
            "events": events,
        }

    # ---- public API ----
    def update(self, pose, t: float, width: float = 1, height: float = 1) -> dict:
        """pose: Person 1's tracking_data['pose'] (or list / None); t: milliseconds."""
        s, o, rx, th = self.s, self.o, self.rx, self.th
        events: list = []
        if s["first_t"] is None:
            s["first_t"] = t
        dt = 1000 / 30 if s["last_t"] is None else max(0.0, t - s["last_t"])
        s["last_t"] = t
        if s["stopped"]:
            return self._result("stopped", t, events)

        if not s["side"]:
            s["side"] = self._pick_side(pose)
            if not s["side"]:
                return self._result("waiting", t, events)
            self._emit(events, {"type": "side_selected", "t": t, "side": s["side"]})

        pts = [_point(pose, n) for n in self.ex["joints"][self._label_side(s["side"])]]
        visible = all(p is not None and p[2] >= o["visibility_threshold"] for p in pts)
        if not visible:
            if s["hidden_since"] is None:
                s["hidden_since"] = t
            if not s["hidden"] and t - s["hidden_since"] >= o["hidden_grace_sec"] * 1000:
                s["hidden"] = True
                self._emit(events, {"type": "hidden", "t": t})
            return self._result("hidden" if s["hidden"] else "ok", t, events)
        if s["hidden"]:
            self._emit(events, {"type": "visible", "t": t})
            self.smoother.reset()
        s["hidden"], s["hidden_since"] = False, None
        s["active_ms"] += min(dt, 250)

        raw = compute_angle(pts[0][:2], pts[1][:2], pts[2][:2], width, height)
        if raw is None:
            return self._result("ok", t, events)
        s["raw"] = raw

        prev = self.smoother.value
        if prev is not None and abs(raw - prev) > o["max_jump_deg"] and s["rejected"] < o["max_rejected_frames"]:
            s["rejected"] += 1
            return self._result("ok", t, events)
        s["rejected"] = 0
        a = self.smoother.push(raw, dt)
        s["max_angle"] = a if s["max_angle"] is None else max(s["max_angle"], a)

        # safe range
        if a > rx["safe_max"]:
            s["over_count"] += 1
            if not s["latched"] and s["over_count"] >= o["safe_frames"]:
                s["latched"] = True
                s["out_of_range"] += 1
                self._emit(events, {"type": "out_of_range", "t": t, "angle": _r1(a)})
        else:
            s["over_count"] = 0
            if s["latched"] and a < rx["safe_max"] - o["safe_release_deg"]:
                s["latched"] = False
                self._emit(events, {"type": "back_in_range", "t": t, "angle": _r1(a)})

        # rep state machine
        if s["state"] == "REST" and not s["armed"]:
            # only count reps that start from the resting position
            if a <= th["start"]:
                s["armed"] = True
        elif s["state"] == "REST":
            if a > th["start"]:
                s.update(state="RAISING", rep_start_t=t, rep_peak=a, flash=None)
                self._emit(events, {"type": "rep_start", "t": t})
        elif s["state"] == "RAISING":
            s["rep_peak"] = max(s["rep_peak"], a)
            if a >= th["reach"]:
                s["state"] = "TOP"
                self._emit(events, {"type": "target_reached", "t": t, "angle": _r1(a)})
            elif a < th["end"]:
                self._end_rep(False, t, events)
        elif s["state"] == "TOP":
            s["rep_peak"] = max(s["rep_peak"], a)
            if a < th["end"]:
                self._end_rep(True, t, events)
        return self._result("ok", t, events)

    def report_pain(self, t: float) -> dict:
        events: list = []
        if not self.s["pain"]:
            self.s["pain"], self.s["pain_at"] = True, t
        self.s["stopped"] = True
        self._emit(events, {"type": "pain", "t": t})
        return self._result("stopped", t, events)

    def resume(self, t: float) -> dict:
        self.s["stopped"], self.s["state"], self.s["armed"] = False, "REST", False
        self.smoother.reset()
        events: list = []
        self._emit(events, {"type": "resumed", "t": t})
        return self._result("ok", t, events)

    def finish(self, t: float | None = None) -> dict:
        s, rx = self.s, self.rx
        t = s["last_t"] if t is None else t
        if s["state"] == "TOP":   # reached the target but not lowered yet — still counts
            self._end_rep(True, t, [])
        rel = lambda x: None if x is None or s["first_t"] is None else _r1((x - s["first_t"]) / 1000)
        return {
            "exercise": rx["exercise"], "side": s["side"],
            "prescription": {k: rx[k] for k in ("min_angle", "target_angle", "safe_max", "reps")},
            "reps": s["reps"], "partial_reps": s["partial_reps"], "out_of_range": s["out_of_range"],
            "max_angle": _r1(s["max_angle"]),
            "duration_sec": 0 if s["first_t"] is None or t is None else _r1((t - s["first_t"]) / 1000),
            "active_sec": _r1(s["active_ms"] / 1000),
            "pain": s["pain"], "pain_at_sec": rel(s["pain_at"]),
            "completed": s["reps"] >= rx["reps"],
            "rep_details": [{**x, "t": rel(x["t"])} for x in s["rep_log"]],
            "events": [{**e, "t": rel(e["t"])} for e in s["log"]],
        }
