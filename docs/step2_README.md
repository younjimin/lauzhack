# Step 2 — Exercise logic (`analyzer.py`)

Takes Step 1's tracking data (`PoseDetector.process_frame()` output) and returns the angle, rep count, safety warnings, a feedback message and, at the end, a session summary. `main.py` (Flask) calls it on every camera frame; the patient screen reads the results from `/api/tracking`.

## Files
| File | What it is |
|---|---|
| `analyzer.py` | Step 2 logic. Standard library only |
| `main.py` | Flask app: Step 1 → **Step 2** → patient screen. Saves each session to `sessions/*.json` |
| `main_with_step2.py` | Debug runner in an OpenCV window (no web server). Use it to tune thresholds or check accuracy on test videos |
| `test_step2_exercises.py` | Tests: curl, finger tap, mirroring, validation, and the Flask API. `python test_step2_exercises.py` |

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
