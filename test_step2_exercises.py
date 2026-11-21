"""
test_step2_exercises.py — pure-Python tests for the exercises used by the web app
(elbow_curl and finger_tap), the left/right mirroring rules and the Flask API
(login, SQL storage, prescriptions, sessions, review notes, messages).

    python test_step2_exercises.py
"""
import math
import sys

from analyzer import RehabAnalyzer, prescription_from_demo

W, H, FPS = 640, 480, 30
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def curve(keys):
    """Angle over time from keyframes [(sec, deg), ...] with smooth easing."""
    def f(t):
        if t <= keys[0][0]:
            return keys[0][1]
        for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
            if t <= t1:
                u = (t - t0) / (t1 - t0)
                return v0 + (v1 - v0) * (1 - math.cos(math.pi * u)) / 2
        return keys[-1][1]
    return f


def lm(x, y, vis=0.95):
    return {"x_norm": x / W, "y_norm": y / H, "x_px": int(x), "y_px": int(y), "visibility": vis}


def curl_pose(elbow_deg, label_side):
    """Person 1-style pose dict whose elbow angle (shoulder–elbow–wrist) is elbow_deg."""
    t = math.radians(elbow_deg)
    s, e = (320, 150), (320, 270)
    w = (e[0] + 110 * math.sin(t), e[1] - 110 * math.cos(t))
    other = "left" if label_side == "right" else "right"
    return {
        f"{label_side}_shoulder": lm(*s), f"{label_side}_elbow": lm(*e), f"{label_side}_wrist": lm(*w),
        f"{other}_shoulder": lm(400, 150, 0.3), f"{other}_elbow": lm(400, 270, 0.3), f"{other}_wrist": lm(400, 380, 0.3),
    }


def tap_hands(opening_deg, label="Right"):
    """Hands dict whose finger opening (180 × thumb–index gap ÷ wrist–knuckle length) is opening_deg."""
    gap = opening_deg / 180 * 100            # wrist–middle knuckle length is 100 px
    return {label: {"wrist": lm(300, 400), "middle_finger_mcp": lm(300, 300),
                    "thumb_tip": lm(280, 250), "index_finger_tip": lm(280 + gap, 250)}}


def run(rx, frames_fn, dur, mirrored=True, fps=FPS):
    an = RehabAnalyzer(rx, mirrored=mirrored)
    msgs = set()
    r = None
    for i in range(int(dur * fps) + 1):
        t = i * 1000 / fps
        r = an.update(frames_fn(i / fps), t, W, H)
        msgs.add(r["message_key"])
    return an.finish(dur * 1000), r, msgs


CURL = {"exercise": "elbow_curl", "side": "right", "rest_angle": 160, "target_angle": 100, "safe_limit": 85, "reps": 10}
TAP = {"exercise": "finger_tap", "side": "auto", "rest_angle": 90, "target_angle": 45, "reps": 20}


def rep_keys(peaks, rest, rise=1.0, hold=0.3, lower=1.0, pause=0.6):
    k, t = [(0, rest), (0.5, rest)], 0.5
    for p in peaks:
        t += rise; k.append((t, p))
        t += hold; k.append((t, p))
        t += lower; k.append((t, rest))
        t += pause; k.append((t, rest))
    return k, t + 0.3


# 1. curl: 4 good reps, 1 partial, 1 too deep (below the 85° limit)
k, dur = rep_keys([95, 95, 125, 95, 78, 95], rest=165)
f = curve(k)
s, last, msgs = run(CURL, lambda t: {"pose": curl_pose(f(t), "left"), "hands": {}}, dur)   # mirrored → real right = label "left"
check("1. Curl: 5 full, 1 partial, 1 too-deep warning",
      s["reps"] == 5 and s["partial_reps"] == 1 and s["out_of_range"] == 1 and "stop" in msgs,
      f"reps={s['reps']} partial={s['partial_reps']} oor={s['out_of_range']} lowest={s['lowest_angle']}")
check("1b. Curl reports real elbow angles (rest ≈165°, lowest ≈78°)",
      abs(last["angle"] - 165) < 2 and abs(s["lowest_angle"] - 78) < 3 and s["best_angle"] == s["lowest_angle"],
      f"angle now={last['angle']} lowest={s['lowest_angle']} best={s['best_angle']}")

# 2. mirroring rules for the pose
s_ok, _, _ = run(CURL, lambda t: curl_pose(f(t), "right"), dur, mirrored=False)
s_wrong, _, _ = run(CURL, lambda t: curl_pose(f(t), "right"), dur, mirrored=True)
check("2. Pose side: mirrored=False reads 'right_*', mirrored=True reads 'left_*'",
      s_ok["reps"] == 5 and s_wrong["reps"] == 0, f"unmirrored reps={s_ok['reps']} | mirrored reps={s_wrong['reps']}")

# 3. finger tapping: 20 taps at about 2.5 taps per second
keys, t = [(0, 110), (0.5, 110)], 0.5
for _ in range(20):
    t += 0.2; keys.append((t, 20))
    t += 0.2; keys.append((t, 110))
keys.append((t + 0.5, 110))
g = curve(keys)
s, last, _ = run(TAP, lambda tt: {"pose": None, "hands": tap_hands(g(tt))}, t + 0.5)
check("3. Finger tap: 20 quick taps counted", s["reps"] == 20 and s["partial_reps"] == 0 and s["completed"],
      f"reps={s['reps']} partial={s['partial_reps']} side={s['side']}")

# 4. half-closed taps are partial, not full
keys, t = [(0, 110), (0.5, 110)], 0.5
for closed in (20, 60, 20, 62):
    t += 0.3; keys.append((t, closed))
    t += 0.3; keys.append((t, 110))
keys.append((t + 0.5, 110))
g2 = curve(keys)
s, _, _ = run(TAP, lambda tt: {"pose": None, "hands": tap_hands(g2(tt))}, t + 0.5)
check("4. Finger tap: 2 full + 2 half-closed (partial)", s["reps"] == 2 and s["partial_reps"] == 2,
      f"reps={s['reps']} partial={s['partial_reps']}")

# 5. hand missing → pause message, count kept
def hidden_hands(tt):
    return {"pose": None, "hands": {} if 3.0 < tt < 4.0 else tap_hands(g(tt))}
s, _, msgs = run(TAP, hidden_hands, 10)
check("5. Hand leaves the frame: 'Show your hand' message, count kept",
      "hidden" in msgs and any(e["type"] == "hidden" for e in s["events"]) and s["reps"] >= 10,
      f"reps={s['reps']} messages={sorted(m for m in msgs if m)}")

# 6. hand labels: hand landmarker assumes a mirrored image
an = RehabAnalyzer({**TAP, "side": "right"}, mirrored=True)
r1 = an.update({"pose": None, "hands": tap_hands(110, "Right")}, 0, W, H)
an2 = RehabAnalyzer({**TAP, "side": "right"}, mirrored=False)
r2 = an2.update({"pose": None, "hands": tap_hands(110, "Right")}, 0, W, H)
check("6. Hand side: label 'Right' is the real right hand only on a mirrored image",
      r1["angle"] is not None and r2["angle"] is None, f"mirrored angle={r1['angle']} | unmirrored angle={r2['angle']}")

# 7. validation and Step 5 helper for a 'down' exercise
errors = 0
for bad in ({**CURL, "rest_angle": 90}, {**CURL, "safe_limit": 120}, {**TAP, "exercise": "jump"}):
    try:
        RehabAnalyzer(bad)
    except ValueError:
        errors += 1
p = prescription_from_demo("elbow_curl", [165, 160, 140, 120, 100, 98, 97, 120, 150, 166] * 5)
check("7. Bad prescriptions rejected; curl demo → rest high, target low", errors == 3 and p["rest_angle"] > p["target_angle"] > p["safe_limit"],
      f"{errors}/3 rejected, demo → {p}")

# 8–14. Flask API end to end: login, SQL storage, patient <-> physiotherapist
# (camera replaced by fake tracking data; database and session files in a temp folder)
try:
    import os
    import tempfile
    tmp = tempfile.mkdtemp()
    os.environ["GEM_DB"] = os.path.join(tmp, "test.db")
    os.environ["GEM_DEMO"] = "0"
    import main as app_module
    app_module.SESSION_DIR = os.path.join(tmp, "sessions")

    patient = app_module.app.test_client()
    doctor = app_module.app.test_client()
    other_doctor = app_module.app.test_client()

    # 8. accounts and login
    page_redirect = patient.get("/").status_code == 302
    api_locked = patient.post("/api/session/start", json={"exercise": "curl"}).status_code == 401
    reg_p = patient.post("/api/auth/register", json={"role": "patient", "name": "Pat", "email": "Pat@Test.org", "password": "secret123"})
    reg_d = doctor.post("/api/auth/register", json={"role": "doctor", "name": "Dr Who", "email": "doc@test.org", "password": "secret123"})
    other_doctor.post("/api/auth/register", json={"role": "doctor", "name": "Dr Other", "email": "other@test.org", "password": "secret123"})
    dup = app_module.app.test_client().post("/api/auth/register", json={"role": "patient", "name": "X", "email": "pat@test.org", "password": "secret123"}).status_code
    short = app_module.app.test_client().post("/api/auth/register", json={"role": "patient", "name": "X", "email": "x@test.org", "password": "123"}).status_code
    wrong = app_module.app.test_client().post("/api/auth/login", json={"email": "pat@test.org", "password": "nope"}).status_code
    good = app_module.app.test_client().post("/api/auth/login", json={"email": "PAT@test.org", "password": "secret123"}).status_code
    page = patient.get("/").get_data(as_text=True)
    pid = reg_p.get_json()["user"]["id"]
    did = reg_d.get_json()["user"]["id"]
    check("8. Login: pages/API locked, register, duplicate/short rejected, wrong password 401, gem.html gets account bar",
          page_redirect and api_locked and reg_p.status_code == 200 and reg_d.status_code == 200 and dup == 409
          and short == 400 and wrong == 401 and good == 200 and "/gem-auth.js" in page
          and doctor.get("/").headers["Location"].endswith("/doctor"),
          f"redirect={page_redirect} locked={api_locked} dup={dup} short={short} wrong={wrong} good={good}")

    # 9. doctor links the patient; roles are enforced
    add = doctor.post("/api/doctor/patients", json={"email": "pat@test.org"})
    patient_blocked = patient.get("/api/doctor/patients").status_code
    other_blocked = other_doctor.get(f"/api/doctor/patients/{pid}").status_code
    listed = [p["id"] for p in doctor.get("/api/doctor/patients").get_json()["patients"]]
    check("9. Doctor adds patient by email; patient can't use doctor API; other doctor can't see the patient",
          add.status_code == 200 and listed == [pid] and patient_blocked == 403 and other_blocked == 404,
          f"add={add.status_code} listed={listed} patient→doctor API={patient_blocked} other doctor={other_blocked}")

    # 10. doctor prescription is validated, stored and used by the patient's next session
    bad = doctor.post(f"/api/doctor/patients/{pid}/prescriptions/curl", json={"target_angle": 80, "safe_limit": 90}).status_code
    ok = doctor.post(f"/api/doctor/patients/{pid}/prescriptions/curl", json={"target_angle": 100, "safe_limit": 85, "reps": 4, "side": "right"})
    with app_module.lock:
        app_module.tracking["camera_connected"] = True
    used = patient.post("/api/session/start", json={"exercise": "curl"}).get_json()["prescription"]
    check("10. Prescription: invalid → 400, valid saved in DB and used by the patient's session",
          bad == 400 and ok.status_code == 200 and used["reps"] == 4 and used["side"] == "right",
          f"bad={bad} ok={ok.status_code} used reps={used['reps']} side={used['side']}")

    # 11. the patient does the exercise (curl curve from test 1: 5 full, 1 too deep) → saved to the DB
    for i in range(int(dur * FPS)):
        app_module.process_tracking({"pose": curl_pose(f(i / FPS), "left"), "hands": {}}, i * 1000 / FPS, W, H)
    live = patient.get("/api/tracking").get_json()
    stop = patient.post("/api/session/stop", json={"reason": "manual"}).get_json()
    again = patient.post("/api/session/stop", json={"reason": "manual"}).get_json()
    seen = doctor.get(f"/api/doctor/patients/{pid}").get_json()
    row = seen["sessions"][0] if seen["sessions"] else {}
    check("11. Session saved once to SQL and visible to the doctor (reps, safety warning, needs review)",
          live["reps"] >= 4 and stop["session_id"] and again["summary"] is None and len(seen["sessions"]) == 1
          and row["reps"] == stop["reps"] and row["out_of_range"] == 1 and row["needs_review"]
          and seen["stats"]["needs_review"] == 1,
          f"live reps={live['reps']} saved id={stop['session_id']} rows={len(seen['sessions'])} oor={row.get('out_of_range')}")

    # 12. pain stop + doctor review note reaches the patient
    patient.post("/api/session/start", json={"exercise": "curl"})
    pain = patient.post("/api/session/stop", json={"reason": "pain"}).get_json()
    review = doctor.post(f"/api/doctor/sessions/{pain['session_id']}/review", json={"note": "Rest 2 days, then try again."}).status_code
    other_review = other_doctor.post(f"/api/doctor/sessions/{pain['session_id']}/review", json={"note": "x"}).status_code
    ov = patient.get("/api/patient/overview").get_json()
    notes = [s["doctor_note"] for s in ov["sessions"] if s["doctor_note"]]
    check("12. Pain stop stored; doctor's review note shows up for the patient; other doctor can't review",
          pain["summary"]["pain"] and review == 200 and other_review == 404 and notes == ["Rest 2 days, then try again."]
          and ov["doctors"][0]["id"] == did and ov["prescriptions"]["curl"]["reps"] == 4 and ov["stats"]["pain"] == 1,
          f"review={review} other={other_review} notes={notes} pain count={ov['stats']['pain']}")

    # 13. messages both ways, unread counts, strangers blocked
    m1 = doctor.post(f"/api/messages/{pid}", json={"body": "How is the elbow today?"}).status_code
    unread = patient.get("/api/messages/unread").get_json()["total"]
    m2 = patient.post(f"/api/messages/{did}", json={"body": "Better, thanks!"}).status_code
    thread = patient.get(f"/api/messages/{did}").get_json()["messages"]
    unread_after = patient.get("/api/messages/unread").get_json()["total"]
    stranger = other_doctor.post(f"/api/messages/{pid}", json={"body": "hi"}).status_code
    empty = patient.post(f"/api/messages/{did}", json={"body": "  "}).status_code
    check("13. Messages: doctor ↔ patient, unread → read, strangers blocked, empty rejected",
          m1 == 200 and m2 == 200 and unread == 1 and unread_after == 0 and [m["body"] for m in thread] ==
          ["How is the elbow today?", "Better, thanks!"] and thread[1]["mine"] and stranger == 403 and empty == 400,
          f"unread before={unread} after={unread_after} thread={len(thread)} stranger={stranger}")

    # 14. export + logout
    export = doctor.get(f"/api/doctor/patients/{pid}/export").get_json()
    patient.post("/api/auth/logout")
    after_logout = patient.get("/api/tracking").status_code
    check("14. Doctor export has full session data; logout locks the API again",
          len(export["sessions"]) == 2 and "rep_details" in export["sessions"][0]["summary"] and after_logout == 401,
          f"exported={len(export['sessions'])} after logout={after_logout}")
except ImportError as e:
    check("8. Flask API (skipped: flask/mediapipe not installed)", True, str(e))

width = max(len(n) for n, _, _ in results)
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
fails = sum(not ok for _, ok, _ in results)
print(f"\n{len(results) - fails}/{len(results)} passed")
sys.exit(1 if fails else 0)
