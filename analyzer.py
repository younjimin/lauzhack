"""
analyzer.py — Rehab Assistant, Step 2 (exercise logic).

Turns Step 1's tracking data (PoseDetector.process_frame output) into
angle / finger sequence → smoothing → visibility check → rep counting → safe-range check →
feedback message → detailed session summary.
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

FINGER_TIPS = {
    "index": "index_finger_tip",
    "middle": "middle_finger_tip",
    "ring": "ring_finger_tip",
    "pinky": "pinky_tip",
}

OPPOSITION_SEQUENCE = ["index", "middle", "ring", "pinky", "ring", "middle"]

EXERCISES: dict[str, dict[str, Any]] = {
    "side_arm_raise": {
        "label": "Side shoulder raise", "view": "front", "body_part": "arm", "source": "pose", "direction": "up",
        "joints": {"left": ("left_hip", "left_shoulder", "left_elbow"),
                   "right": ("right_hip", "right_shoulder", "right_elbow")},
        "defaults": {"rest_angle": 20, "target_angle": 90, "safe_limit": 120, "reps": 5},
        "messages": {"raise": "Raise your arm a bit higher",
                     "lower": "Good, now lower your arm slowly",
                     "partial": "Nearly there - try to reach shoulder height next time"},
    },
    "seated_knee_extension": {
        "label": "Seated knee extension", "view": "side", "body_part": "leg", "source": "pose", "direction": "up",
        "joints": {"left": ("left_hip", "left_knee", "left_ankle"),
                   "right": ("right_hip", "right_knee", "right_ankle")},
        "defaults": {"rest_angle": 90, "target_angle": 160, "safe_limit": 180, "reps": 5},
        "messages": {"raise": "Straighten your knee a bit more",
                     "lower": "Good, now bend it back slowly",
                     "partial": "Nearly there - try to straighten a little further next time"},
    },
    "elbow_curl": {
        "label": "Arm curl", "view": "front or side", "body_part": "arm", "source": "pose", "direction": "down",
        "joints": {"left": ("left_shoulder", "left_elbow", "left_wrist"),
                   "right": ("right_shoulder", "right_elbow", "right_wrist")},
        "defaults": {"rest_angle": 160, "target_angle": 100, "safe_limit": 85, "reps": 5},
        "messages": {"raise": "Slowly bend your elbow a bit more",
                     "lower": "Good! Now slowly straighten your arm",
                     "partial": "Nearly there - bend a little further next time",
                     "stop": "Stop - do not bend past 90 degrees",
                     "rest_first": "Start with your arm straight"},
    },
    "finger_tap": {
        "label": "Finger tapping", "view": "hand to camera", "body_part": "hand", "source": "hand", "direction": "down",
        "defaults": {"rest_angle": 90, "target_angle": 45, "safe_limit": 0, "reps": 10},
        "options": {"min_rep_sec": 0.15, "smoothing_alpha": 0.7, "max_jump_deg": 90, "min_partial_amplitude_deg": 8},
        "messages": {"raise": "Touch your thumb to your index finger",
                     "lower": "Good! Now open your fingers",
                     "partial": "Try to touch your fingertips together",
                     "hidden": "Show your hand to the camera",
                     "rest_first": "Open your hand to start"},
    },
    "finger_opposition": {
        "label": "Sequential finger opposition",
        "view": "hand to camera",
        "body_part": "hand",
        "source": "hand_sequence",
        "direction": "down",
        "defaults": {"rest_angle": 90, "target_angle": 34, "safe_limit": 0, "reps": 10},
        "options": {
            "min_rep_sec": 0.12,
            "smoothing_alpha": 0.75,
            "max_jump_deg": 100,
            "min_partial_amplitude_deg": 10,
            "touch_threshold_deg": 34,
            "release_threshold_deg": 52,
        },
        "messages": {
            "raise": "Touch your thumb to the highlighted finger",
            "lower": "Good! Open your fingers before the next touch",
            "partial": "Close the gap completely until fingertips touch",
            "hidden": "Show your open palm clearly to the camera",
            "rest_first": "Hold your hand open with fingers extended to start",
        },
    },
}

DEFAULTS = {
    "smoothing_alpha": 0.4,
    "visibility_threshold": 0.5,
    "hidden_grace_sec": 0.3,
    "start_fraction": 0.2,
    "hysteresis_deg": 5,
    "target_tolerance_deg": 3,
    "min_rep_sec": 0.5,
    "min_partial_amplitude_deg": 10,
    "max_jump_deg": 35,
    "max_rejected_frames": 3,
    "safe_frames": 3,
    "safe_release_deg": 3,
    "message_hold_sec": 1.0,
    "partial_message_sec": 2.0,
    "touch_threshold_deg": 34,
    "release_threshold_deg": 52,
}

MSG_PRIO = {"pain": 4, "stop": 3, "hidden": 2, "done": 1, "raise": 1, "lower": 1,
            "partial": 1, "ready": 0, "start": 0, "rest_first": 0}

_KEY_ALIASES = {"minAngle": "rest_angle", "min_angle": "rest_angle", "restAngle": "rest_angle",
                "targetAngle": "target_angle", "safeMax": "safe_limit", "safe_max": "safe_limit",
                "safeLimit": "safe_limit"}


def _msg_text(key: str, ex: dict) -> str:
    if key in ex["messages"]:
        return ex["messages"][key]
    return {
        "pain": "Exercise stopped. Take a rest.",
        "stop": "Stop - that is beyond your safe range",
        "hidden": f"Please make sure your whole {ex['body_part']} is visible",
        "done": "Set complete - well done!",
        "ready": "Good. Ready for the next one",
        "start": "Get ready - start when you are ready",
        "rest_first": f"Start from the resting position - lower your {ex['body_part']} first",
    }[key]


def _r1(x):
    return None if x is None else round(x * 10) / 10


def _compute_consistency(durations: list[float]) -> float | None:
    """Computes rhythm consistency (0–100%) from active touch durations."""
    if not durations:
        return None
    if len(durations) == 1:
        return 100.0
    mean_d = sum(durations) / len(durations)
    if mean_d <= 0:
        return 100.0
    std_d = math.sqrt(sum((d - mean_d) ** 2 for d in durations) / len(durations))
    cv = std_d / mean_d
    # Smooth, bounded score: CV=0 -> 100%, CV=0.25 -> 80%, CV=0.5 -> 66.7%, CV=1.0 -> 50%
    return round(100.0 / (1.0 + cv), 1)


def compute_angle(a, b, c, width: float = 1, height: float = 1):
    ax, ay = (a[0] - b[0]) * width, (a[1] - b[1]) * height
    cx, cy = (c[0] - b[0]) * width, (c[1] - b[1]) * height
    na, nc = math.hypot(ax, ay), math.hypot(cx, cy)
    if not na or not nc:
        return None
    cos = max(-1.0, min(1.0, (ax * cx + ay * cy) / (na * nc)))
    return math.degrees(math.acos(cos))


class Smoother:
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


def prescription_from_demo(exercise: str, angles, margin_deg: float = 10, reps: int = 5, side: str = "auto") -> dict:
    lo, hi = percentile(angles, 0.05), percentile(angles, 0.95)
    if lo is None:
        raise ValueError("No angles recorded")
    if EXERCISES[exercise]["direction"] == "down":
        return {"exercise": exercise, "side": side, "reps": reps, "rest_angle": round(hi),
                "target_angle": round(lo), "safe_limit": max(0, round(lo - margin_deg))}
    return {"exercise": exercise, "side": side, "reps": reps, "rest_angle": round(lo),
            "target_angle": round(hi), "safe_limit": min(180, round(hi + margin_deg))}


def _point(part, name: str, width: float, height: float):
    if part is None:
        return None
    if isinstance(part, dict):
        p = part.get(name)
        if p is None:
            return None
        x, y = p.get("x_norm", p.get("x")), p.get("y_norm", p.get("y"))
    else:
        i = POSE_LANDMARK_NAMES.index(name)
        if i >= len(part) or part[i] is None:
            return None
        p = part[i]
        x, y = p.get("x"), p.get("y")
    if x is None or y is None:
        return None
    vis = p.get("visibility", 1.0)
    return (x * width, y * height, 1.0 if vis is None else vis)


class RehabAnalyzer:
    def __init__(self, prescription: dict, mirrored: bool = False, **options):
        prescription = {_KEY_ALIASES.get(k, k): v for k, v in prescription.items()}
        ex = EXERCISES.get(prescription.get("exercise"))
        if ex is None:
            raise ValueError(f"Unknown exercise {prescription.get('exercise')!r}. Known: {', '.join(EXERCISES)}")
        rx = {"side": "auto", **ex["defaults"], **prescription}
        unknown = set(options) - set(DEFAULTS)
        if unknown:
            raise ValueError(f"Unknown options: {unknown}")
        self.ex, self.rx, self.mirrored = ex, rx, mirrored
        self.o = {**DEFAULTS, **ex.get("options", {}), **options}
        self.down = ex["direction"] == "down"
        self._validate(rx)

        f = self._internal
        self.lo, self.tg, self.sm = f(rx["rest_angle"]), f(rx["target_angle"]), f(rx["safe_limit"])
        o = self.o
        self.range = self.tg - self.lo
        start = self.lo + o["start_fraction"] * self.range
        self.th = {"start": start, "end": start - o["hysteresis_deg"], "reach": self.tg - o["target_tolerance_deg"]}
        self.smoother = Smoother(o["smoothing_alpha"])
        self.reset()

    def _internal(self, v):
        return None if v is None else (180 - v if self.down else v)

    _display = _internal

    def _validate(self, rx):
        rest, tg, safe = rx["rest_angle"], rx["target_angle"], rx["safe_limit"]
        if not all(isinstance(v, (int, float)) for v in (rest, tg, safe)):
            raise ValueError("rest_angle, target_angle and safe_limit must be numbers")
        if self.down:
            if not rest > tg:
                raise ValueError("for this exercise rest_angle must be larger than target_angle")
            if not tg >= safe:
                raise ValueError("for this exercise safe_limit must not be larger than target_angle")
        else:
            if not rest < tg:
                raise ValueError("rest_angle must be smaller than target_angle")
            if not tg <= safe:
                raise ValueError("target_angle must not exceed safe_limit")
        if not rx["reps"] >= 1:
            raise ValueError("reps must be at least 1")
        if rx["side"] not in ("left", "right", "auto"):
            raise ValueError("side must be 'left', 'right' or 'auto'")

    def reset(self):
        self.smoother.reset()
        rx = self.rx
        self.s = dict(
            state="REST", armed=False, side=None if rx["side"] == "auto" else rx["side"],
            raw=None, rejected=0, reps=0, partial_reps=0, out_of_range=0,
            max_internal=None, lowest=None, highest=None,
            rep_peak=0.0, rep_start_t=0.0, rep_log=[], over_count=0, latched=False,
            hidden_since=None, hidden=False, first_t=None, last_t=None, active_ms=0.0,
            pain=False, pain_at=None, stopped=False, set_complete=False, flash=None,
            msg={"key": None, "text": "", "prio": -1, "since": -math.inf}, log=[],
        )

    # ---- measuring ----
    def _pose_label(self, side: str) -> str:
        if not self.mirrored:
            return side
        return "left" if side == "right" else "right"

    def _hand_label(self, side: str) -> str:
        if not self.mirrored:
            side = "left" if side == "right" else "right"
        return side.capitalize()

    def _pick_side(self, data):
        if self.ex["source"] in ("hand", "hand_sequence"):
            hands = data.get("hands") or {}
            for side in ("right", "left"):
                if self._hand_label(side) in hands:
                    return side
            return None
        pose = data.get("pose")
        if pose is None:
            return None

        def vis(side):
            total = 0.0
            for name in self.ex["joints"][self._pose_label(side)]:
                p = _point(pose, name, 1, 1)
                total += p[2] if p else 0.0
            return total

        l, r = vis("left"), vis("right")
        if max(l, r) < 3 * self.o["visibility_threshold"]:
            return None
        return "left" if l > r else "right"

    def _measure(self, data, width, height):
        thr = self.o["visibility_threshold"]
        if self.ex["source"] == "hand":
            hand = (data.get("hands") or {}).get(self._hand_label(self.s["side"]))
            if not hand:
                return None, False
            pts = [_point(hand, n, width, height) for n in ("thumb_tip", "index_finger_tip", "wrist", "middle_finger_mcp")]
            if any(p is None or p[2] < thr for p in pts):
                return None, False
            scale = math.hypot(pts[2][0] - pts[3][0], pts[2][1] - pts[3][1])
            if not scale:
                return None, True
            gap = math.hypot(pts[0][0] - pts[1][0], pts[0][1] - pts[1][1])
            return min(180.0, gap / scale * 180), True
        pose = data.get("pose")
        pts = [_point(pose, n, width, height) for n in self.ex["joints"][self._pose_label(self.s["side"])]]
        if any(p is None or p[2] < thr for p in pts):
            return None, False
        return compute_angle(pts[0][:2], pts[1][:2], pts[2][:2]), True

    def _measure_all_fingers(self, data, width, height):
        thr = self.o["visibility_threshold"]
        hand = (data.get("hands") or {}).get(self._hand_label(self.s["side"]))
        if not hand:
            return None, False

        req = ["wrist", "middle_finger_mcp", "thumb_tip", *FINGER_TIPS.values()]
        pts = {name: _point(hand, name, width, height) for name in req}
        if any(p is None or p[2] < thr for p in pts.values()):
            return None, False

        scale = math.hypot(pts["wrist"][0] - pts["middle_finger_mcp"][0],
                           pts["wrist"][1] - pts["middle_finger_mcp"][1])
        if not scale:
            return None, True

        thumb = pts["thumb_tip"]
        gaps = {}
        for fname, tip_name in FINGER_TIPS.items():
            tip = pts[tip_name]
            dist = math.hypot(thumb[0] - tip[0], thumb[1] - tip[1])
            gaps[fname] = min(180.0, (dist / scale) * 180.0)
        return gaps, True

    # ---- internals ----
    def _emit(self, events, e):
        events.append(e)
        self.s["log"].append(e)

    def _end_rep(self, full: bool, t: float, events):
        s, o = self.s, self.o
        dur = (t - s["rep_start_t"]) / 1000
        peak = _r1(self._display(s["rep_peak"]))
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
        if status in ("hidden", "waiting"):
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
        s, rx, d = self.s, self.rx, self._display
        if t is not None:
            self._apply_message(self._choose_message(status, t), t)
        v = self.smoother.value
        return {
            "status": status,
            "angle": _r1(d(v)), "raw_angle": _r1(s["raw"]),
            "lowest_angle": _r1(s["lowest"]), "highest_angle": _r1(s["highest"]),
            "state": s["state"], "side": s["side"],
            "reps": s["reps"], "partial_reps": s["partial_reps"], "target_reps": rx["reps"],
            "out_of_range": s["out_of_range"], "in_danger": s["latched"],
            "set_complete": s["set_complete"],
            "progress": 0.0 if v is None else max(0.0, min(1.0, (v - self.lo) / self.range)),
            "thresholds": {"start": _r1(d(self.th["start"])), "end": _r1(d(self.th["end"])),
                           "reach": _r1(d(self.th["reach"])), "rest": rx["rest_angle"],
                           "target": rx["target_angle"], "safe_limit": rx["safe_limit"]},
            "message": s["msg"]["text"], "message_key": s["msg"]["key"],
            "events": events,
        }

    def _update_finger_sequence(self, data, t: float, width: float, height: float) -> dict:
        s, o = self.s, self.o
        events: list = []
        if s["first_t"] is None:
            s["first_t"] = t
        dt = 1000 / 30 if s["last_t"] is None else max(0.0, t - s["last_t"])
        s["last_t"] = t

        if "seq" not in s:
            s["seq"] = {
                "step_idx": 0,
                "phase": "WAIT_OPEN",
                "step_start_t": t,
                "move_start_t": None,
                "min_target_gap": 180.0,
                "attempted": False,
                "wrong_touch_latched": False,
                "in_error": False,
                "correct_touches": 0,
                "missed_touches": 0,
                "per_finger": {
                    f: {"attempts": 0, "hits": 0, "misses": 0, "durations_sec": [], "min_gaps": []}
                    for f in FINGER_TIPS
                },
                "touch_durations": [],
                "custom_msg": None,
            }
        seq = s["seq"]

        if s["stopped"]:
            return self._result("stopped", t, events)

        if not s["side"]:
            s["side"] = self._pick_side(data)
            if not s["side"]:
                return self._result("waiting", t, events)
            self._emit(events, {"type": "side_selected", "t": t, "side": s["side"]})

        gaps, visible = self._measure_all_fingers(data, width, height)
        if not visible or gaps is None:
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

        target_finger = OPPOSITION_SEQUENCE[seq["step_idx"] % len(OPPOSITION_SEQUENCE)]
        target_gap = gaps[target_finger]
        touch_th = o.get("touch_threshold_deg", 34)
        release_th = o.get("release_threshold_deg", 52)

        s["raw"] = target_gap
        a = self.smoother.push(self._internal(target_gap), dt)
        s["max_internal"] = a if s["max_internal"] is None else max(s["max_internal"], a)
        disp = self._display(a)
        s["lowest"] = disp if s["lowest"] is None else min(s["lowest"], disp)
        s["highest"] = disp if s["highest"] is None else max(s["highest"], disp)

        other_fingers = {f: g for f, g in gaps.items() if f != target_finger}
        closest_other = min(other_fingers, key=other_fingers.get)
        closest_other_gap = other_fingers[closest_other]

        if seq["phase"] == "WAIT_OPEN":
            s["state"] = "REST"
            seq["in_error"] = False
            if all(g >= release_th for g in gaps.values()):
                s["armed"] = True
                seq["phase"] = "SEEK_TOUCH"
                seq["step_start_t"] = t
                seq["move_start_t"] = None
                seq["min_target_gap"] = 180.0
                seq["attempted"] = False
                seq["wrong_touch_latched"] = False
                seq["custom_msg"] = f"Touch thumb to {target_finger.upper()} finger"
            else:
                seq["custom_msg"] = "Hold hand open with all fingers extended"

        elif seq["phase"] == "SEEK_TOUCH":
            s["state"] = "RAISING"
            seq["min_target_gap"] = min(seq["min_target_gap"], disp)

            # Start active movement timer when thumb begins closing toward target finger
            if disp < release_th - 6:
                if seq["move_start_t"] is None:
                    seq["move_start_t"] = t
                seq["attempted"] = True

            # 1. Correct finger touched
            if disp <= touch_th:
                start_ref = seq["move_start_t"] if seq["move_start_t"] is not None else seq["step_start_t"]
                dur = max(0.08, min(5.0, (t - start_ref) / 1000.0))

                fstat = seq["per_finger"][target_finger]
                fstat["attempts"] += 1
                fstat["hits"] += 1
                fstat["durations_sec"].append(round(dur, 2))
                fstat["min_gaps"].append(_r1(disp))

                seq["correct_touches"] += 1
                seq["touch_durations"].append(dur)
                seq["in_error"] = False
                s["reps"] = seq["correct_touches"]
                s["rep_log"].append({
                    "n": s["reps"], "type": "full", "finger": target_finger,
                    "peak": _r1(disp), "duration_sec": round(dur, 2), "t": t
                })
                self._emit(events, {"type": "rep", "t": t, "count": s["reps"], "finger": target_finger, "duration_sec": round(dur, 2)})

                if not s["set_complete"] and s["reps"] >= self.rx["reps"]:
                    s["set_complete"] = True
                    self._emit(events, {"type": "set_complete", "t": t, "reps": s["reps"]})

                seq["phase"] = "WAIT_RELEASE"
                s["state"] = "TOP"
                seq["custom_msg"] = f"Good! Open hand ({target_finger} complete)"

            # 2. Wrong finger touched
            elif closest_other_gap <= touch_th:
                seq["in_error"] = True
                if not seq["wrong_touch_latched"]:
                    seq["wrong_touch_latched"] = True
                    seq["missed_touches"] += 1
                    seq["per_finger"][target_finger]["attempts"] += 1
                    seq["per_finger"][target_finger]["misses"] += 1
                    s["partial_reps"] = seq["missed_touches"]
                    self._emit(events, {"type": "missed_touch", "t": t, "expected": target_finger, "touched": closest_other})
                seq["custom_msg"] = f"Wrong finger ({closest_other}) — touch {target_finger.upper()} instead"

            # 3. Incomplete reach pulled back without touching
            elif seq["attempted"] and disp >= release_th:
                seq["in_error"] = True
                seq["missed_touches"] += 1
                seq["per_finger"][target_finger]["attempts"] += 1
                seq["per_finger"][target_finger]["misses"] += 1
                seq["per_finger"][target_finger]["min_gaps"].append(_r1(seq["min_target_gap"]))
                s["partial_reps"] = seq["missed_touches"]
                seq["attempted"] = False
                seq["move_start_t"] = None
                seq["min_target_gap"] = 180.0
                self._emit(events, {"type": "partial_rep", "t": t, "finger": target_finger, "min_gap": _r1(seq["min_target_gap"])})
                seq["custom_msg"] = f"Missed touch — bring thumb all the way to {target_finger.upper()}"
            else:
                if closest_other_gap > touch_th + 6:
                    seq["wrong_touch_latched"] = False
                seq["custom_msg"] = f"Touch thumb to {target_finger.upper()} finger ({s['reps']}/{self.rx['reps']})"

        elif seq["phase"] == "WAIT_RELEASE":
            s["state"] = "TOP"
            seq["in_error"] = False
            if disp >= release_th and closest_other_gap >= release_th:
                seq["step_idx"] += 1
                next_finger = OPPOSITION_SEQUENCE[seq["step_idx"] % len(OPPOSITION_SEQUENCE)]
                seq["phase"] = "SEEK_TOUCH"
                s["state"] = "REST"
                seq["step_start_t"] = t
                seq["move_start_t"] = None
                seq["min_target_gap"] = 180.0
                seq["attempted"] = False
                seq["wrong_touch_latched"] = False
                seq["custom_msg"] = f"Next: touch thumb to {next_finger.upper()} finger"

        res = self._result("ok", t, events)
        total_attempts = seq["correct_touches"] + seq["missed_touches"]
        accuracy = round((seq["correct_touches"] / total_attempts) * 100, 1) if total_attempts else 100.0
        avg_time = round(sum(seq["touch_durations"]) / len(seq["touch_durations"]), 2) if seq["touch_durations"] else None
        consistency = _compute_consistency(seq["touch_durations"])

        res["message"] = seq["custom_msg"] or res["message"]
        res["in_danger"] = seq["in_error"]
        res["finger_metrics"] = {
            "target_finger": target_finger,
            "sequence_step": (seq["step_idx"] % len(OPPOSITION_SEQUENCE)) + 1,
            "sequence_length": len(OPPOSITION_SEQUENCE),
            "accuracy_pct": accuracy,
            "avg_touch_sec": avg_time,
            "consistency_pct": consistency,
            "missed_touches": seq["missed_touches"],
            "in_error": seq["in_error"],
            "per_finger": seq["per_finger"],
        }
        return res

    # ---- public API ----
    def update(self, data, t: float, width: float = 1, height: float = 1) -> dict:
        if not (isinstance(data, dict) and ("pose" in data or "hands" in data)):
            data = {"pose": data, "hands": {}}

        if self.ex["source"] == "hand_sequence":
            return self._update_finger_sequence(data, t, width, height)

        s, o, th = self.s, self.o, self.th
        events: list = []
        if s["first_t"] is None:
            s["first_t"] = t
        dt = 1000 / 30 if s["last_t"] is None else max(0.0, t - s["last_t"])
        s["last_t"] = t
        if s["stopped"]:
            return self._result("stopped", t, events)

        if not s["side"]:
            s["side"] = self._pick_side(data)
            if not s["side"]:
                return self._result("waiting", t, events)
            self._emit(events, {"type": "side_selected", "t": t, "side": s["side"]})

        raw, visible = self._measure(data, width, height)
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
        if raw is None:
            return self._result("ok", t, events)
        s["raw"] = raw
        x = self._internal(raw)

        prev = self.smoother.value
        if prev is not None and abs(x - prev) > o["max_jump_deg"] and s["rejected"] < o["max_rejected_frames"]:
            s["rejected"] += 1
            return self._result("ok", t, events)
        s["rejected"] = 0
        a = self.smoother.push(x, dt)
        s["max_internal"] = a if s["max_internal"] is None else max(s["max_internal"], a)
        disp = self._display(a)
        s["lowest"] = disp if s["lowest"] is None else min(s["lowest"], disp)
        s["highest"] = disp if s["highest"] is None else max(s["highest"], disp)

        if a > self.sm:
            s["over_count"] += 1
            if not s["latched"] and s["over_count"] >= o["safe_frames"]:
                s["latched"] = True
                s["out_of_range"] += 1
                self._emit(events, {"type": "out_of_range", "t": t, "angle": _r1(disp)})
        else:
            s["over_count"] = 0
            if s["latched"] and a < self.sm - o["safe_release_deg"]:
                s["latched"] = False
                self._emit(events, {"type": "back_in_range", "t": t, "angle": _r1(disp)})

        if s["state"] == "REST" and not s["armed"]:
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
                self._emit(events, {"type": "target_reached", "t": t, "angle": _r1(disp)})
            elif a < th["end"]:
                self._end_rep(False, t, events)
        elif s["state"] == "TOP":
            s["rep_peak"] = max(s["rep_peak"], a)
            if a < th["end"]:
                self._end_rep(True, t, events)
        return self._result("ok", t, events)

    def report_pain(self, t: float | None = None) -> dict:
        t = self.s["last_t"] if t is None else t
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
        if s["state"] == "TOP" and t is not None and "seq" not in s:
            self._end_rep(True, t, [])
        rel = lambda x: None if x is None or s["first_t"] is None else _r1((x - s["first_t"]) / 1000)

        rep_durs = [r["duration_sec"] for r in s["rep_log"] if r.get("duration_sec") is not None]
        avg_rep_sec = round(sum(rep_durs) / len(rep_durs), 2) if rep_durs else None
        rom_deg = None
        if s["lowest"] is not None and s["highest"] is not None:
            rom_deg = _r1(s["highest"] - s["lowest"])

        summary = {
            "exercise": rx["exercise"], "side": s["side"], "direction": self.ex["direction"],
            "prescription": {k: rx[k] for k in ("rest_angle", "target_angle", "safe_limit", "reps")},
            "reps": s["reps"], "partial_reps": s["partial_reps"], "out_of_range": s["out_of_range"],
            "best_angle": _r1(self._display(s["max_internal"])),
            "lowest_angle": _r1(s["lowest"]), "highest_angle": _r1(s["highest"]),
            "max_angle": _r1(s["highest"]),
            "rom_deg": rom_deg,
            "avg_rep_sec": avg_rep_sec,
            "duration_sec": 0 if s["first_t"] is None or t is None else _r1((t - s["first_t"]) / 1000),
            "active_sec": _r1(s["active_ms"] / 1000),
            "pain": s["pain"], "pain_at_sec": rel(s["pain_at"]),
            "completed": s["reps"] >= rx["reps"],
            "rep_details": [{**x, "t": rel(x["t"])} for x in s["rep_log"]],
            "events": [{**e, "t": rel(e["t"])} for e in s["log"]],
        }

        if "seq" in s:
            seq = s["seq"]
            total_att = seq["correct_touches"] + seq["missed_touches"]
            acc = round((seq["correct_touches"] / total_att) * 100, 1) if total_att else 0.0
            durs = seq["touch_durations"]
            avg_t = round(sum(durs) / len(durs), 2) if durs else None
            cons = _compute_consistency(durs) or 0.0

            hardest = None
            hardest_score = (2.0, -1.0)
            for fname, st in seq["per_finger"].items():
                if st["attempts"] > 0:
                    hit_rate = st["hits"] / st["attempts"]
                    f_avg = sum(st["durations_sec"]) / len(st["durations_sec"]) if st["durations_sec"] else 999.0
                    score = (hit_rate, -f_avg)
                    if score < hardest_score:
                        hardest_score = score
                        hardest = fname

            summary["finger_metrics"] = {
                "accuracy_pct": acc,
                "avg_touch_sec": avg_t,
                "consistency_pct": cons,
                "missed_touches": seq["missed_touches"],
                "hardest_finger": hardest,
                "per_finger": seq["per_finger"],
            }

        return summary