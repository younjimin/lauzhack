"""
rehab_modes.py — extra rehabilitation modes (logic only, no camera / web code).

1. Dual-task mode (motor + cognitive at the same time)
   The patient holds a posture (arm curl at the prescribed target angle, or an open hand)
   first on its own (single-task baseline), then while answering two-choice questions by
   tilting or turning the head towards the answer (or clicking). The difference in how well
   the posture is held is the "dual-task cost".

2. Fatigue detection (triggers the guided breathing break)
   Watches the rep events of a normal exercise session and raises one alert when movement
   quality drops sharply (smaller range, much slower reps, repeated partial reps or misses).

3. Shoulder tension (used by the breathing break)
   Neck length (shoulders → ears) relative to shoulder width; shrugging makes it smaller.

All thresholds are prototype heuristics for a demo, not clinical cut-offs.

    from rehab_modes import DualTaskSession, FatigueMonitor, HeadSelector, shoulder_ratio
"""
from __future__ import annotations

import math
import random

from analyzer import RehabAnalyzer, Smoother, _point, _r1


# --------------------------------------------------
# HEAD TILT / TURN SELECTION (from pose landmarks: eyes + nose)
# --------------------------------------------------
class HeadSelector:
    """Left/right choice by tilting (ear to shoulder) or turning the head, with dwell-to-confirm.

    Works in IMAGE coordinates of the frame the patient sees. main.py flips the webcam image
    like a mirror, so "towards the option on the screen" is the same direction in the image.

    update() -> {"direction": "left"|"right"|None, "progress": 0..1, "confirmed": "left"|"right"|None,
                 "visible": bool, "score": signed strength (>= 1 means past the threshold)}
    """

    def __init__(self, hold_ms=1200, roll_deg=10.0, yaw_norm=0.22, enter=1.0, release=0.6,
                 calib_frames=8, alpha=0.5, visibility=0.5):
        self.hold_ms, self.roll_deg, self.yaw_norm = hold_ms, roll_deg, yaw_norm
        self.enter, self.release, self.calib_frames, self.visibility = enter, release, calib_frames, visibility
        self.roll_s, self.yaw_s = Smoother(alpha), Smoother(alpha)
        self.recalibrate()

    def recalibrate(self):
        self.neutral = None
        self._calib = []
        self.roll_s.reset()
        self.yaw_s.reset()
        self.direction = None
        self.since = None
        self.armed = False          # must be back at the centre before a new answer counts

    def _measure(self, pose, width, height):
        pts = [_point(pose, n, width, height) for n in ("left_eye", "right_eye", "nose")]
        if any(p is None or p[2] < self.visibility for p in pts):
            return None
        e1, e2, nose = pts
        a, b = sorted((e1, e2), key=lambda p: p[0])          # a = eye on the image left
        eye_dist = math.hypot(b[0] - a[0], b[1] - a[1])
        if eye_dist < 1e-6:
            return None
        roll = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))      # + = tilted towards image right
        yaw = (nose[0] - (a[0] + b[0]) / 2) / eye_dist                  # + = turned towards image right
        return roll, yaw

    def update(self, pose, t, width=1, height=1):
        m = self._measure(pose, width, height)
        if m is None:
            self.direction, self.since = None, None
            return {"direction": None, "progress": 0.0, "confirmed": None, "visible": False, "score": 0.0}
        roll, yaw = self.roll_s.push(m[0]), self.yaw_s.push(m[1])
        if self.neutral is None:                       # calibrate: the first frames are "centre"
            self._calib.append((roll, yaw))
            if len(self._calib) >= self.calib_frames:
                rs, ys = sorted(c[0] for c in self._calib), sorted(c[1] for c in self._calib)
                self.neutral = (rs[len(rs) // 2], ys[len(ys) // 2])
                self.armed = True
            return {"direction": None, "progress": 0.0, "confirmed": None, "visible": True, "score": 0.0}

        r = (roll - self.neutral[0]) / self.roll_deg
        y = (yaw - self.neutral[1]) / self.yaw_norm
        score = r if abs(r) >= abs(y) else y
        mag = abs(score)

        if mag < self.release:
            self.armed = True                          # back at the centre
        current = None
        if mag >= self.enter or (self.direction and mag >= self.release):   # hysteresis
            current = "right" if score > 0 else "left"
        if current != self.direction:
            self.direction, self.since = current, (t if current else None)

        confirmed, progress = None, 0.0
        if self.direction and self.armed:
            progress = min(1.0, (t - self.since) / self.hold_ms)
            if progress >= 1.0:
                confirmed = self.direction
                self.armed = False                     # one answer per tilt; return to centre first
                self.since = t
        return {"direction": self.direction, "progress": round(progress, 3), "confirmed": confirmed,
                "visible": True, "score": round(score, 2)}


# --------------------------------------------------
# TWO-CHOICE QUESTIONS (original items, generated)
# --------------------------------------------------
_CATEGORIES = [
    ("Which one is a fruit?", ["Apple", "Banana", "Pear", "Orange", "Grape"], ["Chair", "Spoon", "Shoe", "Car", "Book"]),
    ("Which one is an animal?", ["Dog", "Horse", "Cat", "Rabbit", "Bird"], ["Table", "Cup", "Lamp", "Door", "Hat"]),
    ("Which one is a colour?", ["Blue", "Green", "Red", "Yellow", "Purple"], ["Bread", "Window", "Pencil", "River", "Clock"]),
    ("Which one can you wear?", ["Coat", "Scarf", "Sock", "Glove", "Shirt"], ["Carrot", "Bus", "Plate", "Tree", "Key"]),
]
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def make_questions(n, rng: random.Random, level=1):
    """n two-choice questions. Each: {"text", "options": [left, right], "answer": 0|1, "kind"}.

    Items are written for this app (not taken from any licensed cognitive test)."""
    hi = 9 if level <= 1 else 20
    kinds = ["sum", "bigger", "category", "parity", "day"]
    rng.shuffle(kinds)
    out = []
    for i in range(n):
        kind = kinds[i] if i < len(kinds) else rng.choice(kinds)   # every kind once, then random
        if kind == "sum":
            a, b = rng.randint(1, hi), rng.randint(1, hi)
            shown = a + b + (0 if rng.random() < 0.5 else rng.choice([-2, -1, 1, 2]))
            text, opts, ans = f"Is {a} + {b} = {shown}?", ["Yes", "No"], 0 if shown == a + b else 1
        elif kind == "bigger":
            a = rng.randint(10, 99)
            b = int(str(a)[::-1]) if str(a)[::-1] != str(a) and a % 10 else a + rng.randint(3, 15)
            pair = [a, b] if rng.random() < 0.5 else [b, a]
            text, opts, ans = "Which number is bigger?", [str(pair[0]), str(pair[1])], 0 if pair[0] > pair[1] else 1
        elif kind == "category":
            q, good, bad = rng.choice(_CATEGORIES)
            g, w = rng.choice(good), rng.choice(bad)
            left_good = rng.random() < 0.5
            text, opts, ans = q, [g, w] if left_good else [w, g], 0 if left_good else 1
        elif kind == "parity":
            n_ = rng.randint(2, 30 if level > 1 else 12)
            text, opts, ans = f"Is {n_} an even number?", ["Yes", "No"], 0 if n_ % 2 == 0 else 1
        else:
            i_ = rng.randrange(7)
            right_ans = _DAYS[(i_ + 1) % 7]
            wrong = _DAYS[(i_ - 1) % 7]
            first = rng.random() < 0.5
            text = f"Which day comes after {_DAYS[i_]}?"
            opts, ans = ([right_ans, wrong], 0) if first else ([wrong, right_ans], 1)
        out.append({"text": text, "options": opts, "answer": ans, "kind": kind})
    return out


# --------------------------------------------------
# MOTOR HOLD STATISTICS
# --------------------------------------------------
class _HoldStats:
    """Time-weighted in-zone %, steadiness (SD) and drops for one phase."""

    def __init__(self):
        self.in_ms = self.out_ms = self.lost_ms = 0.0
        self.n = 0
        self.mean = self.m2 = 0.0           # Welford for SD of the angle
        self.err_sum = 0.0
        self.drops = 0
        self._out_since = None
        self._counted = False

    def add(self, angle, in_zone, dt, t, target, drop_ms=500):
        if angle is None:
            self.lost_ms += dt
            return
        if in_zone:
            self.in_ms += dt
        else:
            self.out_ms += dt
        self.n += 1
        d = angle - self.mean
        self.mean += d / self.n
        self.m2 += d * (angle - self.mean)
        self.err_sum += abs(angle - target)
        if in_zone:
            self._out_since, self._counted = None, False
        else:
            if self._out_since is None:
                self._out_since = t
            if not self._counted and t - self._out_since >= drop_ms:
                self.drops += 1
                self._counted = True

    def summary(self):
        seen = self.in_ms + self.out_ms
        return {
            "in_zone_pct": None if seen <= 0 else round(100 * self.in_ms / seen, 1),
            "angle_sd": None if self.n < 2 else round(math.sqrt(self.m2 / (self.n - 1)), 1),
            "mean_error": None if self.n == 0 else round(self.err_sum / self.n, 1),
            "drops": self.drops,
            "seconds": round(seen / 1000, 1),
            "not_visible_sec": round(self.lost_ms / 1000, 1),
        }


# --------------------------------------------------
# DUAL-TASK SESSION
# --------------------------------------------------
POSTURES = {
    # zone: target ± tolerance in the analyzer's display angle
    "curl_hold": {"exercise": "elbow_curl", "label": "Arm curl hold", "tolerance": 15,
                  "msg_get_in": "Bend your elbow to about {target}° and hold it there",
                  "msg_low": "Straighten a little", "msg_high": "Bend a little more"},
    "hand_open": {"exercise": "finger_tap", "label": "Open hand hold", "tolerance": None,
                  "msg_get_in": "Hold your hand up, fingers spread wide open",
                  "msg_low": "", "msg_high": "Open your fingers wider"},
}


class DualTaskSession:
    """Phases: position → baseline (hold only) → dual (hold + questions) → done."""

    def __init__(self, posture="curl_hold", prescription=None, n_questions=6, baseline_sec=10,
                 question_sec=8, feedback_sec=1.2, hold_ms=1200, settle_ms=1000, level=1,
                 mirrored=True, seed=None):
        if posture not in POSTURES:
            raise ValueError(f"Unknown posture {posture!r}. Known: {', '.join(POSTURES)}")
        if not 1 <= int(n_questions) <= 30:
            raise ValueError("n_questions must be between 1 and 30")
        self.posture, self.p = posture, POSTURES[posture]
        rx = {**(prescription or {}), "exercise": self.p["exercise"]}
        rx.pop("updated_at", None)
        self.analyzer = RehabAnalyzer(rx, mirrored=mirrored)
        rx = self.analyzer.rx
        if posture == "curl_hold":
            self.target = float(rx["target_angle"])
            self.zone = (self.target - self.p["tolerance"], self.target + self.p["tolerance"])
        else:                                   # open hand: opening at or above 80% of the resting opening
            self.target = float(rx["rest_angle"])
            self.zone = (0.8 * self.target, 180.0)
        self.n_questions, self.baseline_ms = int(n_questions), baseline_sec * 1000
        self.question_ms, self.feedback_ms, self.settle_ms = question_sec * 1000, feedback_sec * 1000, settle_ms
        self.rng = random.Random(seed)
        self.questions = make_questions(self.n_questions, self.rng, level)
        self.head = HeadSelector(hold_ms=hold_ms)
        self.base, self.dual = _HoldStats(), _HoldStats()
        self.phase = "position"
        self.phase_t = None
        self.in_zone_since = None
        self.q_idx = -1
        self.q_shown_t = None
        self.feedback_until = None
        self.answers = []                       # {"q", "chosen", "correct", "rt_sec", "via"}
        self.last_t = self.first_t = None
        self.angle = None
        self.in_zone = False
        self.out_since = None
        self.status = "waiting"
        self.last_feedback = None
        self.ended_by = None

    # ---- helpers ----
    def _in_zone(self, a):
        return a is not None and self.zone[0] <= a <= self.zone[1]

    def _start_question(self, t):
        self.q_idx += 1
        if self.q_idx >= self.n_questions:
            self.phase, self.phase_t = "done", t
            return
        self.q_shown_t, self.feedback_until = t, None
        self.head.armed = False                  # look back to the centre before answering

    def answer(self, choice, t=None, via="click"):
        """Record an answer for the current question. choice: 'left'|'right'|0|1."""
        t = self.last_t if t is None else t
        if self.phase != "dual" or self.q_shown_t is None or self.feedback_until is not None:
            return False
        idx = choice if isinstance(choice, int) else (0 if choice == "left" else 1)
        q = self.questions[self.q_idx]
        rec = {"q": self.q_idx + 1, "text": q["text"], "options": q["options"], "chosen": idx,
               "correct": idx == q["answer"], "rt_sec": round((t - self.q_shown_t) / 1000, 2), "via": via}
        self.answers.append(rec)
        self.last_feedback = rec
        self.feedback_until = t + self.feedback_ms
        return True

    # ---- per frame ----
    def update(self, data, t, width=1, height=1):
        if not (isinstance(data, dict) and ("pose" in data or "hands" in data)):
            data = {"pose": data, "hands": {}}
        dt = 0.0 if self.last_t is None else max(0.0, min(250.0, t - self.last_t))
        self.last_t = t
        if self.first_t is None:
            self.first_t = t
        if self.phase in ("done", "stopped"):
            return self.state()

        r = self.analyzer.update(data, t, width, height)
        self.status = r["status"]
        self.angle = r["angle"] if r["status"] == "ok" else None
        self.in_zone = self._in_zone(self.angle)
        if self.in_zone or self.angle is None:
            self.out_since = None
        elif self.out_since is None:
            self.out_since = t

        head = self.head.update(data.get("pose"), t, width, height)
        self.head_state = head

        if self.phase == "position":
            if self.in_zone:
                self.in_zone_since = self.in_zone_since if self.in_zone_since is not None else t
                if t - self.in_zone_since >= self.settle_ms:
                    if self.baseline_ms > 0:
                        self.phase, self.phase_t = "baseline", t
                    else:
                        self.phase, self.phase_t = "dual", t
                        self._start_question(t)
            else:
                self.in_zone_since = None
        elif self.phase == "baseline":
            self.base.add(self.angle, self.in_zone, dt, t, self.target)
            if t - self.phase_t >= self.baseline_ms:
                self.phase, self.phase_t = "dual", t
                self.head.recalibrate()          # centre = how the head is held right now
                self._start_question(t)
        elif self.phase == "dual":
            self.dual.add(self.angle, self.in_zone, dt, t, self.target)
            if self.feedback_until is not None:
                if t >= self.feedback_until:
                    self._start_question(t)
            elif head.get("confirmed"):
                self.answer(head["confirmed"], t, via="head")
            elif t - self.q_shown_t >= self.question_ms:
                q = self.questions[self.q_idx]
                rec = {"q": self.q_idx + 1, "text": q["text"], "options": q["options"], "chosen": None,
                       "correct": False, "rt_sec": None, "via": "timeout"}
                self.answers.append(rec)
                self.last_feedback = rec
                self.feedback_until = t + self.feedback_ms
        return self.state()

    # ---- outputs ----
    def _motor_message(self):
        if self.status in ("hidden", "waiting"):
            return "Make sure your arm and face are visible" if self.posture == "curl_hold" else \
                "Show your hand and face to the camera"
        if self.angle is None:
            return ""
        if self.in_zone:
            return "Good — hold steady"
        if self.posture == "curl_hold":
            return self.p["msg_high"] if self.angle > self.zone[1] else self.p["msg_low"]
        return self.p["msg_high"]

    def cognitive_summary(self):
        answered = [a for a in self.answers if a["chosen"] is not None]
        correct = sum(a["correct"] for a in self.answers)
        rts = [a["rt_sec"] for a in answered]
        return {
            "questions": self.n_questions, "answered": len(answered), "correct": correct,
            "timeouts": sum(a["chosen"] is None for a in self.answers),
            "accuracy_pct": round(100 * correct / len(self.answers), 1) if self.answers else None,
            "mean_rt_sec": round(sum(rts) / len(rts), 2) if rts else None,
            "via_head": sum(a["via"] == "head" for a in self.answers),
        }

    def costs(self):
        b, d = self.base.summary(), self.dual.summary()
        cost = sd_change = None
        if b["in_zone_pct"] and d["in_zone_pct"] is not None:
            cost = round(100 * (b["in_zone_pct"] - d["in_zone_pct"]) / b["in_zone_pct"], 1)
        if b["angle_sd"] and d["angle_sd"] is not None:
            sd_change = round(100 * (d["angle_sd"] - b["angle_sd"]) / b["angle_sd"], 1)
        return cost, sd_change

    def state(self):
        t = self.last_t or 0
        q = None
        if self.phase == "dual" and 0 <= self.q_idx < self.n_questions:
            cur = self.questions[self.q_idx]
            q = {"number": self.q_idx + 1, "of": self.n_questions, "text": cur["text"], "options": cur["options"],
                 "time_left": None if self.feedback_until is not None
                 else max(0.0, round((self.question_ms - (t - self.q_shown_t)) / 1000, 1)),
                 "answered": self.feedback_until is not None}
        fb = None
        if self.last_feedback and self.feedback_until is not None and t < self.feedback_until:
            fb = {"correct": self.last_feedback["correct"], "chosen": self.last_feedback["chosen"],
                  "answer": self.questions[self.last_feedback["q"] - 1]["answer"],
                  "timeout": self.last_feedback["chosen"] is None}
        phase_left = None
        if self.phase == "baseline":
            phase_left = max(0.0, round((self.baseline_ms - (t - self.phase_t)) / 1000, 1))
        cost, _ = self.costs()
        head = getattr(self, "head_state", {}) or {}
        return {
            "active": self.phase not in ("done", "stopped"),
            "phase": self.phase, "phase_left_sec": phase_left,
            "posture": self.posture, "label": self.p["label"],
            "angle": self.angle, "target": self.target, "zone": [round(self.zone[0], 1), round(self.zone[1], 1)],
            "in_zone": self.in_zone,
            "out_of_zone_sec": None if self.out_since is None else round((t - self.out_since) / 1000, 1),
            "motor_message": self._motor_message(),
            "get_in_message": self.p["msg_get_in"].format(target=round(self.target)),
            "question": q, "feedback": fb,
            "head": {"direction": head.get("direction"), "progress": head.get("progress", 0.0),
                     "visible": head.get("visible", False), "calibrated": self.head.neutral is not None},
            "baseline": self.base.summary(), "dual": self.dual.summary(),
            "cognitive": self.cognitive_summary(), "dual_task_cost_pct": cost,
        }

    def finish(self, reason="manual"):
        finished_all = self.phase == "done"
        if not finished_all:
            self.phase = "stopped"
        self.ended_by = "completed" if finished_all and reason != "pain" else reason
        if reason == "pain":
            self.analyzer.report_pain()
        motor = self.analyzer.finish()
        cog = self.cognitive_summary()
        cost, sd_change = self.costs()
        b, d = self.base.summary(), self.dual.summary()
        dual_info = {
            "posture": self.posture, "target": self.target, "zone": [round(z, 1) for z in self.zone],
            "baseline": b, "dual": d, "dual_task_cost_pct": cost, "steadiness_change_pct": sd_change,
            "cognitive": cog, "answers": self.answers,
        }
        return {
            "exercise": "dual_task", "ui_exercise": "dual", "side": motor["side"],
            "prescription": {"reps": self.n_questions, "target_angle": self.target, "posture": self.posture},
            "reps": cog["correct"], "partial_reps": cog["questions"] - cog["correct"],
            "out_of_range": motor["out_of_range"],
            "lowest_angle": motor["lowest_angle"], "highest_angle": motor["highest_angle"],
            "rom_deg": motor["rom_deg"],
            "accuracy_pct": cog["accuracy_pct"],
            "duration_sec": None if self.first_t is None else _r1((self.last_t - self.first_t) / 1000),
            "pain": reason == "pain", "completed": finished_all,
            "ended_by": self.ended_by,
            "dual_task": dual_info,
        }


# --------------------------------------------------
# FATIGUE MONITOR (for normal exercise sessions)
# --------------------------------------------------
class FatigueMonitor:
    """Feed analyzer events; returns one alert when movement quality drops sharply.

    Curl-type exercises: last 2 reps reach < 70% of the early reps' range, take > 1.7× as long,
    or 2 partial reps in a row. Finger opposition: 3 misses in the last 5 attempts, or the last
    2 touches take > 2× as long as the first ones.
    """

    def __init__(self, rx, sequence=False, range_drop=0.70, slow_factor=1.7, min_reps=3):
        self.rest = float(rx.get("rest_angle", 0))
        self.sequence = sequence
        self.range_drop, self.slow_factor, self.min_reps = range_drop, slow_factor, min_reps
        self.reset()
        self.alerts = 0

    def reset(self):
        self.reps = []            # (amplitude, duration)
        self.attempts = []        # True = hit, False = miss (sequence)
        self.partials_in_row = 0

    def feed(self, event):
        k = event.get("type")
        if self.sequence:
            if k == "rep":
                self.attempts.append(True)
                if event.get("duration_sec") is not None:
                    self.reps.append((None, float(event["duration_sec"])))
            elif k in ("missed_touch", "partial_rep"):
                self.attempts.append(False)
            else:
                return None
            return self._check_sequence()
        if k == "rep":
            self.partials_in_row = 0
            amp = abs(self.rest - float(event.get("peak") or self.rest))
            self.reps.append((amp, float(event.get("duration_sec") or 0)))
            return self._check_reps()
        if k == "partial_rep":
            self.partials_in_row += 1
            if self.partials_in_row >= 2 and len(self.reps) >= 1:
                return self._alert("partial", "Your last movements did not reach the target")
        return None

    def _alert(self, code, text):
        self.alerts += 1
        self.reset()
        return {"id": self.alerts, "reason": code, "message": text}

    def _check_reps(self):
        if len(self.reps) < max(self.min_reps, 3) + 1:
            return None
        base = self.reps[:2]
        b_amp = sum(r[0] for r in base) / 2
        b_dur = sum(r[1] for r in base) / 2
        last = self.reps[-2:]
        if b_amp > 0 and all(r[0] < self.range_drop * b_amp for r in last):
            return self._alert("range", "Your movement range is getting smaller")
        if b_dur > 0 and all(r[1] > self.slow_factor * b_dur for r in last):
            return self._alert("slow", "Your movements are slowing down")
        return None

    def _check_sequence(self):
        recent = self.attempts[-5:]
        if len(recent) >= 5 and recent.count(False) >= 3:
            return self._alert("misses", "Several touches were missed in a row")
        durs = [r[1] for r in self.reps]
        if len(durs) >= 4:
            b = sum(durs[:2]) / 2
            if b > 0 and all(d > 2.0 * b for d in durs[-2:]):
                return self._alert("slow", "Your finger touches are slowing down")
        return None


# --------------------------------------------------
# SHOULDER TENSION (breathing break)
# --------------------------------------------------
def shoulder_ratio(pose, width=1, height=1, visibility=0.5):
    """(shoulder height − ear height) ÷ shoulder width. Shrugging the shoulders up makes it smaller.
    Returns None if the shoulders or ears are not visible."""
    pts = [_point(pose, n, width, height) for n in ("left_shoulder", "right_shoulder", "left_ear", "right_ear")]
    if any(p is None or p[2] < visibility for p in pts):
        return None
    ls, rs, le, re = pts
    width_px = math.hypot(ls[0] - rs[0], ls[1] - rs[1])
    if width_px < 1e-6:
        return None
    neck = (ls[1] + rs[1]) / 2 - (le[1] + re[1]) / 2
    return round(neck / width_px, 3)
