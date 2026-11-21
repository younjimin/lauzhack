"""
test_rehab_modes.py — tests for dual-task mode, fatigue detection, shoulder tension and their Flask APIs.

    python test_rehab_modes.py
"""
import math
import os
import random
import sys
import tempfile

from rehab_modes import DualTaskSession, FatigueMonitor, HeadSelector, make_questions, shoulder_ratio

W, H, FPS = 640, 480, 30
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def lm(x, y, vis=0.95):
    return {"x_norm": x / W, "y_norm": y / H, "x_px": int(x), "y_px": int(y), "visibility": vis}


def face(roll_deg=0.0, yaw=0.0, cx=320, cy=110):
    """Eyes + nose (+ ears) with the head tilted by roll_deg (+ = towards image right) and turned by yaw."""
    r = math.radians(roll_deg)
    dx, dy = 20 * math.cos(r), 20 * math.sin(r)
    return {"left_eye": lm(cx + dx, cy + dy), "right_eye": lm(cx - dx, cy - dy),   # mirrored labels: left_eye on image right
            "nose": lm(cx + yaw * 40 - 25 * math.sin(r), cy + 25 * math.cos(r)),
            "left_ear": lm(cx + 45, cy + 5), "right_ear": lm(cx - 45, cy + 5)}


def curl_arm(elbow_deg, label="left"):
    """Mirrored webcam: the patient's real RIGHT arm carries MediaPipe's 'left_*' labels."""
    t = math.radians(elbow_deg)
    s, e = (420, 200), (420, 320)
    w = (e[0] - 110 * math.sin(t), e[1] - 110 * math.cos(t))
    other = "right" if label == "left" else "left"
    return {f"{label}_shoulder": lm(*s), f"{label}_elbow": lm(*e), f"{label}_wrist": lm(*w),
            f"{other}_shoulder": lm(220, 200, 0.3), f"{other}_elbow": lm(220, 320, 0.3), f"{other}_wrist": lm(220, 420, 0.3)}


def pose(elbow_deg, roll=0.0, yaw=0.0, shrug=0.0):
    p = {**curl_arm(elbow_deg), **face(roll, yaw)}
    p["left_shoulder"] = lm(420, 200 - shrug)
    p["right_shoulder"] = lm(220, 200 - shrug)
    return p


# --------------------------------------------------
# 1. Head selector
# --------------------------------------------------
def run_head(script, fps=FPS):
    hs, confirmed, t = HeadSelector(hold_ms=1200), [], 0.0
    for dur, roll, yaw in script:
        for _ in range(int(dur * fps)):
            r = hs.update(face(roll, yaw), t, W, H)
            if r["confirmed"]:
                confirmed.append((round(t / 1000, 2), r["confirmed"]))
            t += 1000 / fps
    return confirmed


c = run_head([(0.6, 0, 0), (2.5, 15, 0)])
check("1. Head: tilt right and hold 1.2 s → one 'right' (holding longer adds nothing)",
      [d for _, d in c] == ["right"], str(c))
c = run_head([(0.6, 0, 0), (2.0, -15, 0), (0.6, 0, 0), (2.0, 15, 0)])
check("1b. Head: left, back to centre, then right → left, right", [d for _, d in c] == ["left", "right"], str(c))
c = run_head([(0.6, 0, 0), (0.6, 15, 0), (0.6, 0, 0), (0.5, -15, 0), (1.0, 0, 0)])
check("1c. Head: short tilts (< 1.2 s) are ignored", c == [], str(c))
c = run_head([(0.6, 0, 0), (2.0, 0, -0.35)])
check("1d. Head: turning (not only tilting) also works", [d for _, d in c] == ["left"], str(c))
c = run_head([(0.6, 4, 0), (2.0, 4 + 3, 0)])
check("1e. Head: small wobble around a tilted resting head is not a choice", c == [], str(c))

# --------------------------------------------------
# 2. Questions
# --------------------------------------------------
qs = make_questions(40, random.Random(1))
ok = all(len(q["options"]) == 2 and q["answer"] in (0, 1) and q["options"][0] != q["options"][1] for q in qs)
balance = sum(q["answer"] for q in qs) / len(qs)
check("2. Questions: two different options, valid answer, left/right answers balanced",
      ok and 0.25 < balance < 0.75 and len({q["kind"] for q in qs}) == 5, f"right-answer share={balance:.2f}")


# --------------------------------------------------
# 3. Dual-task session (closed loop: a simulated patient)
# --------------------------------------------------
def simulate(answer_plan, base_noise=2.0, dual_wobble=0.0, posture="curl_hold", seconds=90, seed=5, start_angle=160):
    """answer_plan[i] = 'right_answer' | 'wrong' | 'none' | 'click'. Returns (summary, frames_in_position)."""
    rng = random.Random(seed)
    ds = DualTaskSession(posture, {"target_angle": 100, "rest_angle": 160, "safe_limit": 85},
                         n_questions=len(answer_plan), baseline_sec=4, question_sec=6, mirrored=True, seed=seed)
    t, angle, plan_t = 0.0, start_angle, None
    pos_frames = 0
    for i in range(int(seconds * FPS)):
        st = ds.state()
        if st["phase"] in ("done", "stopped"):
            break
        target = 100
        angle += (target - angle) * 0.15                                  # move into position
        a = angle + rng.gauss(0, base_noise)
        if st["phase"] == "dual" and dual_wobble:
            a += dual_wobble * math.sin(i / 7)                            # thinking makes the arm drift
        roll = 0.0
        q = st["question"]
        if q and not q["answered"]:
            plan = answer_plan[q["number"] - 1]
            if plan_t is None or plan_t[0] != q["number"]:
                plan_t = (q["number"], t)
            if t - plan_t[1] > 800:                                       # think for 0.8 s, then answer
                ans = ds.questions[q["number"] - 1]["answer"]
                if plan == "right_answer":
                    roll = 15 if ans == 1 else -15
                elif plan == "wrong":
                    roll = -15 if ans == 1 else 15
                elif plan == "click" and t - plan_t[1] > 1500:
                    ds.answer("right" if ans == 1 else "left", t)
        pos_frames += st["phase"] == "position"
        ds.update({"pose": pose(a, roll), "hands": {}}, t, W, H)
        t += 1000 / FPS
    return ds.finish("manual"), pos_frames


s, pos = simulate(["right_answer"] * 4 + ["wrong", "none"], dual_wobble=22)
d, cog = s["dual_task"], s["dual_task"]["cognitive"]
check("3. Dual-task: 6 questions — 4 right, 1 wrong, 1 timeout; answered by head tilt",
      s["completed"] and cog["correct"] == 4 and cog["timeouts"] == 1 and cog["via_head"] == 5 and s["reps"] == 4,
      f"correct={cog['correct']} timeouts={cog['timeouts']} via_head={cog['via_head']} rt={cog['mean_rt_sec']}")
check("3b. Dual-task cost: steady alone, drifting with questions → positive cost, SD up",
      d["baseline"]["in_zone_pct"] > 90 and d["dual"]["in_zone_pct"] < d["baseline"]["in_zone_pct"]
      and d["dual_task_cost_pct"] > 10 and d["steadiness_change_pct"] > 50,
      f"alone={d['baseline']['in_zone_pct']}% with Qs={d['dual']['in_zone_pct']}% cost={d['dual_task_cost_pct']}% "
      f"SD change={d['steadiness_change_pct']}%")
s2, _ = simulate(["right_answer"] * 4, dual_wobble=0)
check("3c. No drift with questions → cost about 0", abs(s2["dual_task"]["dual_task_cost_pct"]) < 5,
      f"cost={s2['dual_task']['dual_task_cost_pct']}%")
check("3d. Baseline only starts once the arm is at the target (position phase first)",
      pos > 10 and s["dual_task"]["baseline"]["seconds"] >= 3.9, f"position frames={pos}")
s3, _ = simulate(["click", "click", "click"])
check("3e. Click answers work and are recorded as clicks", s3["dual_task"]["cognitive"]["correct"] == 3
      and all(a["via"] == "click" for a in s3["dual_task"]["answers"]), str([a["via"] for a in s3["dual_task"]["answers"]]))

ds = DualTaskSession("curl_hold", {"target_angle": 100}, n_questions=2, baseline_sec=0, question_sec=6, seed=1)
t = 0
for i in range(60):
    ds.update({"pose": pose(100), "hands": {}}, t, W, H); t += 33
first = ds.answer("left", t)
second = ds.answer("right", t + 10)
summ = ds.finish("pain")
check("3f. Only one answer per question; pain stop is recorded", first and not second and summ["pain"]
      and summ["ended_by"] == "pain" and not summ["completed"], f"first={first} second={second}")

ds = DualTaskSession("hand_open", {}, n_questions=1, baseline_sec=1, seed=2)
hand = lambda op: {"Right": {"wrist": lm(300, 400), "middle_finger_mcp": lm(300, 300),
                             "thumb_tip": lm(260, 260), "index_finger_tip": lm(260 + op / 180 * 100, 260)}}
t = 0
for i in range(90):
    ds.update({"pose": face(), "hands": hand(110 if i < 75 else 40)}, t, W, H); t += 33
st = ds.state()
check("3g. Open-hand posture: open = on target, closing = off target", st["phase"] == "dual" and not st["in_zone"]
      and ds.base.summary()["in_zone_pct"] == 100.0, f"phase={st['phase']} in_zone={st['in_zone']}")


# --------------------------------------------------
# 4. Fatigue monitor
# --------------------------------------------------
def feed(mon, events):
    out = [mon.feed(e) for e in events]
    return [a for a in out if a]


rx = {"rest_angle": 160}
rep = lambda peak, dur: {"type": "rep", "peak": peak, "duration_sec": dur}
normal = [rep(98, 2.0), rep(100, 2.1), rep(97, 2.0), rep(99, 2.2), rep(101, 2.1), rep(98, 2.0)]
check("4. Fatigue: steady reps → no alert", feed(FatigueMonitor(rx), normal) == [])
smaller = [rep(98, 2.0), rep(100, 2.0), rep(110, 2.0), rep(125, 2.1), rep(128, 2.2)]
a = feed(FatigueMonitor(rx), smaller)
check("4b. Fatigue: range shrinks (62°→33°) → one 'range' alert", len(a) == 1 and a[0]["reason"] == "range", str(a))
slower = [rep(98, 2.0), rep(100, 2.0), rep(99, 2.5), rep(99, 3.8), rep(98, 4.1)]
a = feed(FatigueMonitor(rx), slower)
check("4c. Fatigue: reps get much slower → 'slow' alert", len(a) == 1 and a[0]["reason"] == "slow", str(a))
a = feed(FatigueMonitor(rx), [rep(98, 2), {"type": "partial_rep"}, {"type": "partial_rep"}])
check("4d. Fatigue: two partial reps in a row → alert", len(a) == 1 and a[0]["reason"] == "partial", str(a))
seq = [{"type": "rep", "duration_sec": 0.8}, {"type": "missed_touch"}, {"type": "rep", "duration_sec": 0.9},
       {"type": "missed_touch"}, {"type": "missed_touch"}]
a = feed(FatigueMonitor({}, sequence=True), seq)
check("4e. Fatigue (finger opposition): 3 misses in 5 attempts → alert", len(a) == 1 and a[0]["reason"] == "misses", str(a))
mon = FatigueMonitor(rx)
a1 = feed(mon, smaller)
a2 = feed(mon, [rep(126, 2.2)])
check("4f. Fatigue: after an alert, it needs fresh reps before alerting again", len(a1) == 1 and a2 == [], f"{a1} {a2}")

# --------------------------------------------------
# 5. Shoulder tension
# --------------------------------------------------
relaxed, shrugged = shoulder_ratio(pose(100), W, H), shoulder_ratio(pose(100, shrug=40), W, H)
check("5. Shoulder ratio drops when the shoulders are raised", relaxed and shrugged and shrugged < 0.85 * relaxed,
      f"relaxed={relaxed} shrugged={shrugged}")
check("5b. Shoulder ratio is None without shoulders/ears", shoulder_ratio({"nose": lm(1, 1)}, W, H) is None)

# --------------------------------------------------
# 6. Flask API (login, DB, doctor view)
# --------------------------------------------------
try:
    tmp = tempfile.mkdtemp()
    os.environ["GEM_DB"] = os.path.join(tmp, "test.db")
    os.environ["GEM_DEMO"] = "0"
    import main as app_module
    patient, doctor = app_module.app.test_client(), app_module.app.test_client()
    pid = patient.post("/api/auth/register", json={"role": "patient", "name": "Pat", "email": "p@t.org",
                                                    "password": "secret123"}).get_json()["user"]["id"]
    doctor.post("/api/auth/register", json={"role": "doctor", "name": "Doc", "email": "d@t.org", "password": "secret123"})
    doctor.post("/api/doctor/patients", json={"email": "p@t.org"})
    doctor.post(f"/api/doctor/patients/{pid}/prescriptions/curl", json={"target_angle": 95, "safe_limit": 80})

    no_cam = patient.post("/api/dual/start", json={}).status_code
    with app_module.lock:
        app_module.tracking["camera_connected"] = True
    bad = patient.post("/api/dual/start", json={"posture": "jump"}).status_code
    st = patient.post("/api/dual/start", json={"questions": 2, "baseline_sec": 1, "question_sec": 5}).get_json()["state"]
    blocked = patient.post("/api/session/start", json={"exercise": "curl"}).status_code
    t = 0
    for i in range(150):                                            # 1 s position + 1 s baseline + first question
        app_module.process_tracking({"pose": pose(95), "hands": {}}, t, W, H); t += 33
    live = patient.get("/api/dual/state").get_json()["state"]
    q = live["question"]
    ans_ok = patient.post("/api/dual/answer", json={"choice": "left"}).get_json()["success"]
    stop = patient.post("/api/dual/stop", json={"reason": "manual"}).get_json()
    seen = doctor.get(f"/api/doctor/patients/{pid}").get_json()["sessions"][0]
    check("6. Dual API: needs camera, bad posture 400, uses the physio's target, blocks normal exercise, saved for the doctor",
          no_cam == 400 and bad == 400 and st["target"] == 95 and blocked == 409 and live["phase"] == "dual" and q
          and ans_ok and stop["session_id"] and seen["exercise"] == "dual_task" and seen["dual"]
          and seen["dual"]["baseline_in_zone_pct"] == 100.0 and seen["target_reps"] == 2,
          f"no_cam={no_cam} bad={bad} target={st['target']} blocked={blocked} phase={live['phase']} "
          f"doctor sees={seen['exercise']} dual={seen['dual']}")

    # fatigue → pause → resume → break saved with the session
    patient.post("/api/session/start", json={"exercise": "curl"})
    angles = []
    for peak in (95, 96, 110, 125, 128):                            # reps getting smaller
        angles += [165] * 15 + [165 + (peak - 165) * k / 20 for k in range(21)] + [peak] * 8 + \
                  [peak + (165 - peak) * k / 20 for k in range(21)]
    angles += [165] * 20
    for a in angles:
        app_module.process_tracking({"pose": pose(a), "hands": {}}, t, W, H); t += 33
    tr = patient.get("/api/tracking").get_json()
    alert = tr["fatigue_alert"]
    p1 = patient.post("/api/session/pause", json={"trigger": "fatigue"}).status_code
    reps_before = patient.get("/api/tracking").get_json()["reps"]
    for a in [165] * 10 + [95] * 30 + [165] * 30:                     # movement during the break is not counted
        app_module.process_tracking({"pose": pose(a), "hands": {}}, t, W, H); t += 33
    paused_tr = patient.get("/api/tracking").get_json()
    patient.post("/api/session/resume", json={"completed": True, "seconds": 60})
    stop = patient.post("/api/session/stop", json={"reason": "manual"}).get_json()
    seen = doctor.get(f"/api/doctor/patients/{pid}").get_json()["sessions"][0]
    check("6b. Fatigue alert → pause (reps frozen) → resume; the break is saved and shown to the doctor",
          alert and alert["reason"] in ("range", "partial") and p1 == 200 and paused_tr["paused"] and paused_tr["reps"] == reps_before
          and stop["summary"]["breaks"][0]["trigger"] == "fatigue" and stop["summary"]["breaks"][0]["completed"]
          and seen["breaks"] == 1 and tr["shoulder_ratio"] is not None,
          f"alert={alert} reps frozen={paused_tr['reps']}=={reps_before} breaks={seen['breaks']} shoulder={tr['shoulder_ratio']}")
    bad_game = patient.post("/api/cognitive/result", json={"game": "chess", "correct": 1, "total": 2}).status_code
    bad_num = patient.post("/api/cognitive/result", json={"game": "logic", "correct": 9, "total": 5}).status_code
    doc_post = doctor.post("/api/cognitive/result", json={"game": "logic", "correct": 1, "total": 2}).status_code
    ok = patient.post("/api/cognitive/result", json={"game": "memory", "correct": 4, "total": 6, "seconds": 42,
                                                     "avg_sec": 2.5, "input": "mouse"}).get_json()
    seen = doctor.get(f"/api/doctor/patients/{pid}").get_json()["sessions"][0]
    mine = patient.get("/api/patient/sessions").get_json()["sessions"][0]
    check("6d. Thinking-game result is saved to the account and shown to the doctor; bad input rejected",
          bad_game == 400 and bad_num == 400 and doc_post == 403 and ok["success"] and seen["exercise"] == "cognitive_memory"
          and seen["reps"] == 4 and seen["target_reps"] == 6 and seen["accuracy_pct"] == 66.7 and seen["input"] == "mouse"
          and mine["id"] == seen["id"],
          f"bad={bad_game},{bad_num} doctor={doc_post} doctor sees={seen['exercise']} {seen['reps']}/{seen['target_reps']}")
    page = patient.get("/").get_data(as_text=True)
    js = patient.get("/rehab-modes.js").status_code
    check("6c. Patient page loads rehab-modes.js", "/rehab-modes.js" in page and js == 200, f"js={js}")
except ImportError as e:
    check("6. Flask API (skipped)", True, str(e))

width = max(len(n) for n, _, _ in results)
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
fails = sum(not ok for _, ok, _ in results)
print(f"\n{len(results) - fails}/{len(results)} passed")
sys.exit(1 if fails else 0)
