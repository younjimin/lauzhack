# Step 2 — Exercise logic (`analyzer.js`)

Pure logic module: pose landmarks in → angle, reps, feedback, session result out. No camera, no DOM, so it can be tested without Step 1.

## Files
| File | What it is |
|---|---|
| `analyzer.js` | The module (browser: `window.RehabAnalyzer`, Node: `require('./analyzer.js')`) |
| `test_analyzer.js` | 18 fake-data tests. `node test_analyzer.js` (add `--csv` to write per-frame CSVs to `out/`) |
| `run_frames.js` | Run the analyzer on frames recorded from a real test video: `node run_frames.js frames.json prescription.json [expectedReps]` |

## Use in the browser (Step 1 / Step 3)
```html
<script src="analyzer.js"></script>
<script>
const an = RehabAnalyzer.createAnalyzer({
  exercise: 'side_arm_raise',   // or 'seated_knee_extension'
  side: 'auto',                 // 'left' | 'right' | 'auto'
  minAngle: 15, targetAngle: 90, safeMax: 120, reps: 10
});

// every MediaPipe result:
const r = an.update({ t: performance.now(), landmarks: results.poseLandmarks,
                      width: video.videoWidth, height: video.videoHeight });
// r.angle, r.progress (0–1 for the gauge), r.state, r.reps, r.partialReps,
// r.outOfRange, r.inDanger, r.message, r.status ('ok' | 'hidden' | 'stopped' | 'waiting'), r.events

painButton.onclick = () => an.reportPain(performance.now());
const session = an.finish(performance.now());   // → save / send to dashboard
</script>
```

## Session result (`finish()`)
`exercise, side, prescription, reps, partialReps, outOfRange, maxAngle, durationSec, activeSec, pain, painAtSec, completed, repDetails[], events[]`

## Events (`r.events`, per frame)
`side_selected, rep_start, target_reached, rep, partial_rep, rep_ignored (too_short | too_small), set_complete, out_of_range, back_in_range, hidden, visible, pain, resumed`

## How it decides
- **Angle**: at the middle joint (arm: hip–shoulder–elbow, knee: hip–knee–ankle), in pixels (normalised x/y × width/height).
- **Smoothing**: EMA (α = 0.4 at 30 fps, adjusted for other frame rates). Single-frame jumps over 35° are rejected.
- **Visibility**: all 3 joints ≥ 0.5; joints missing for over 0.3 s → pause ("Please make sure your whole arm is visible"). The count is kept.
- **Reps**: REST → RAISING (above `start` = min + 20% of the range) → TOP (≥ target − 3°) → back below `end` (= start − 5°) = 1 rep. If the patient comes down before reaching TOP, it counts as a partial rep (only if it rose 10° above `start`). Movements under 0.5 s are ignored.
- **Safety**: above `safeMax` for 3 frames → one `out_of_range` event + "Stop" message, cleared below `safeMax − 3°`.
- **Messages**: priority pain > stop > hidden > state message; each stays at least 1 s.

All thresholds are in `DEFAULTS` and can be overridden: `createAnalyzer(rx, { hysteresisDeg: 7 })`.

## For Step 5 (therapist demo recording)
`RehabAnalyzer.computeAngle`, `createSmoother` and `prescriptionFromDemo(exercise, angles)` (5th/95th percentile, safeMax = 95th + 10°) are exported for reuse.

## Notes
- MediaPipe labels left/right from the **person's** view. If the image is mirrored before pose detection, the sides swap; use `side: 'auto'` if unsure.
- A 3-point angle can't exceed 180°, so for knee extension `safeMax: 180` means the safety check never fires (knee hyperextension needs a different measure).

## Python version (plugs into Person 1's `lauz` project)
Person 1's Step 1 is Python (OpenCV + MediaPipe Tasks), so the same logic also exists as `analyzer.py`. Both versions give identical results, checked on the same test frames.

| File (put in `lauz/`) | What it is |
|---|---|
| `analyzer.py` | Same logic as `analyzer.js`. Takes `tracking_data["pose"]` from `PoseDetector.process_frame()` directly |
| `main_with_step2.py` | Person 1's `main.py` loop + Step 2: angle, reps, gauge and message drawn on the window; saves `session_*.json` |
| `test_analyzer_py.py` | Runs the JS test frames (`node test_analyzer.js --dump`) through `analyzer.py` and checks the results match |

```bash
python main_with_step2.py                                    # webcam
python main_with_step2.py --exercise seated_knee_extension --side left
python main_with_step2.py --video test.mp4 --expected 10     # accuracy check on a test video
python main_with_step2.py --video test.mp4 --dump frames.json  # save frames (also usable with run_frames.js)
```
Keys: `q` finish & save · `p` pain · `c` continue · `r` reset.

- **Mirroring:** `main.py` flips the webcam image before detection, which swaps MediaPipe's left/right labels (verified on a real photo). `main_with_step2.py` passes `mirrored=True` for the webcam (not for video files), so `side` always means the patient's real side.
- **Keys:** Python uses snake_case (`min_angle`, `partial_reps`); `analyzer.py` also accepts the camelCase prescription keys (`minAngle`). The team should pick one style for the saved session format.
- **Starting mid-movement:** reps are counted only after the patient has been at rest once ("Start from the resting position").
