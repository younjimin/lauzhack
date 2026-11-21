# Step 2 — Exercise logic (`analyzer.py`)

Takes Step 1's tracking data (`PoseDetector.process_frame()` output) and returns the angle, rep count, safety warnings, a feedback message and, at the end, a session summary. `main.py` (Flask) calls it on every camera frame; the patient screen reads the results from `/api/tracking`.

## Files
| File | What it is |
|---|---|
| `analyzer.py` | Step 2 logic. Standard library only |
| `main.py` | Flask app: Step 1 → **Step 2** → patient screen. Saves each session to `sessions/*.json` |
| `main_with_step2.py` | Debug runner in an OpenCV window (no web server). Use it to tune thresholds or check accuracy on test videos |
| `test_step2_exercises.py` | Tests: curl, finger tap, mirroring, validation, and the Flask API. `python test_step2_exercises.py` |
| `test_hand_side.py` | Tests that the real hand is tracked when MediaPipe's Left/Right hand label is wrong or flickers. `python test_hand_side.py` |

## Run
```bash
python main.py                                   # web app with webcam → http://127.0.0.1:5000
REHAB_VIDEO=test.mp4 python main.py              # web app with a test video instead of the webcam
python main_with_step2.py --exercise elbow_curl --video test.mp4 --expected 10   # accuracy check
python test_step2_exercises.py
```

## Exercises
| Key in the UI | Analyzer exercise | Measured | Direction | Default prescription |
|---|---|---|---|---|
| `curl` | `elbow_curl` | shoulder–elbow–wrist angle | goes down | rest 160°, target 100°, safe limit 85°, 10 reps |
| `tap` | `finger_tap` | finger opening = 180 × thumb–index gap ÷ wrist–knuckle length | goes down | open 90, closed 45, 20 reps |
| — | `side_arm_raise` | hip–shoulder–elbow | goes up | rest 15°, target 90°, safe 120° |
| — | `seated_knee_extension` | hip–knee–ankle | goes up | rest 90°, target 160° |

Prescriptions for the web app are in `PRESCRIPTIONS` at the top of `main.py` (later: from the therapist / database).

## API used by the frontend
- `POST /api/session/start` with `{"exercise": "curl" | "tap"}` → starts a new analyzer
- `GET /api/tracking` → the existing fields (`angle`, `reps`, `feedback`, `pose_detected`, `min_angle` …) plus `partial_reps`, `target_reps`, `out_of_range`, `in_danger`, `state`, `progress` (0 = rest, 1 = target), `message_key`, `status`, `max_angle`
- `POST /api/session/stop` with `{"reason": "manual" | "pain" | "completed"}` → `reps`, `min_angle` and the full `summary`

## How it decides
- **Angle**: in pixels (normalised coordinates × width/height), smoothed (EMA); single-frame jumps are ignored.
- **Visibility**: needed joints below 0.5 visibility for over 0.3 s → "Keep your arm visible" / "Show your hand to the camera". The count is kept.
- **Reps**: rest → moving (20% of the way to the target) → target reached → back towards rest = 1 rep. Coming back before the target = partial rep. Reps only start counting after the patient has been at rest once. Too-short movements are ignored.
- **Safety**: past the safe limit for 3 frames → "Stop" + one `out_of_range` event.
- **Messages**: priority pain > stop > not visible > movement message; each stays at least 1 s, so the spoken feedback doesn't chatter.

## Left / right
`main.py` flips the webcam image before detection, so the analyzer is created with `mirrored=True` and `side: "right"` means the patient's **real** right arm. (MediaPipe pose labels swap on a flipped image; hand labels don't, because the hand model already assumes a selfie image.) With `REHAB_VIDEO` the image is not flipped and `mirrored=False` is used.

**Hands.** MediaPipe guesses "Left"/"Right" for a hand from how it looks, so the guess is often wrong when the back of the hand faces the camera or the hand is small, and it can flicker between frames. The analyzer therefore:
1. matches each hand's wrist to the nearest wrist of the pose skeleton when the body is in view (reliable);
2. keeps tracking the only visible hand when its label flips and no body is in view;
3. in `side: "auto"`, reports the side seen most often, not the first frame's guess.

The raw "Left Hand / Right Hand" text is no longer drawn on the video; the overlay shows `Tracking: RIGHT` (the side the analyzer uses).

## Voice feedback (frontend/gem.html)
On by default (🔊 button on the exercise screen, or Settings → Audio feedback). Mistakes and safety messages (`in_danger`, `finger_metrics.in_error`, pain) are spoken at once, never cut off, and repeated every 4 s while they last; normal coaching waits until the current sentence has finished.

## Dual-task mode (rehab_modes.py + frontend/rehab-modes.js)
The patient holds a posture and answers simple questions at the same time.
- **Postures:** `curl_hold` holds the elbow at the physio's curl target (±15°); `hand_open` keeps the hand open (≥ 80% of the open angle).
- **Phases:**
  1. `position`: get to the target and hold for 1 s.
  2. `baseline`: hold alone for 10 s.
  3. `dual`: hold while answering (6 questions × 8 s).
  4. `done`.
- **Questions:** sums, bigger number, odd/even, category, days of the week. Each has two options (left/right). The questions are self-written; MMSE/MoCA items are not used.
- **Answering:**
  - **Head:** tilt or turn the head towards the answer and hold it for 1.2 s, using the eyes and nose from the same pose camera. The neutral head position is calibrated at the start; the head must return to the centre before the next answer.
  - **Click:** click or use ←/→, as an alternative.
- **Results:**
  - On-target % alone vs. with questions.
  - **Dual-task cost** = (alone − with questions) ÷ alone × 100.
  - Steadiness (SD) change, accuracy and average answer time.
  - Saved like an exercise session, with `exercise: "dual_task"`; the physio page shows it.
- **APIs:**
  - `POST /api/dual/start {posture, questions, baseline_sec, question_sec, hold_ms}`: the camera must be connected; returns 409 while a normal exercise session runs.
  - `GET /api/dual/state`
  - `POST /api/dual/answer {choice: "left"|"right"}`
  - `POST /api/dual/stop {reason}` → `summary`, `session_id`

## Guided breathing & fatigue recovery
- A 60 s breathing break: circle grows for 4 s in, shrinks for 6 s out, with spoken cues and a progress bar.
- **When it starts:**
  1. After **Pain — stop now**.
  2. From the **☕ Breathing break** button.
  3. **Automatically** when the movement quality drops (`FatigueMonitor`).
- **Fatigue triggers (prototype thresholds):**
  - **Arm curl:** the last 2 reps reach < 70% of the first reps' range; or they take > 1.7× as long; or there are 2 partial reps in a row.
  - **Finger opposition:** 3 misses in the last 5 touches; or touches take > 2× as long.
- **During the break:**
  - The exercise session is paused (`/api/session/pause` / `resume`), so reps are not counted.
  - The shoulder check uses the shoulder–ear distance. When the shoulders rise, it says "Your shoulders look raised — let them drop".
- **After the break:**
  - Continue or End session; after pain, "Message my physiotherapist".
  - Breaks are saved in `summary.breaks`; the physio page shows "☕ N break(s)".
- New `/api/tracking` fields: `paused`, `fatigue_alert {id, reason, message}`, `shoulder_ratio`, `dual_active`.

These are training aids from a webcam estimate, **not clinical measurements**. All thresholds are prototype values for the physio to adjust.

## Tests
`python test_rehab_modes.py` (24 checks: head choice, dual-task flow and cost, fatigue triggers, shoulder check, API + database + doctor view), `python test_step2_exercises.py` (15), `python test_hand_side.py`.
