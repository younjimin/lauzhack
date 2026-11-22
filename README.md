# ability+

**Home rehabilitation with a laptop webcam, supervised remotely by a physiotherapist.**

Camera-guided arm and hand exercises, thinking games, dual-task training and guided breathing breaks for patients, plus a dashboard for their physiotherapist.

Built by team **GEMGEM** for the **IMChange Tech for Good** challenge at **LauzHack 2026**.

> [!NOTE]
> ability+ is a training aid based on webcam estimates. It is **not a medical device**, and its angles are **not clinical measurements**.

---

## Contents
- [Why](#why)
- [Demo](#demo)
- [What it does](#what-it-does)
- [Safety and privacy](#safety-and-privacy)
- [Run it locally](#run-it-locally)
- [Tests](#tests)
- [Tech](#tech)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Team](#team)

---

## Why

In many developing countries, people who need rehabilitation can't reach a clinic, and the few NGO physiotherapists there have far more patients than they can see in person. Patients are sent home with a sheet of exercises, and nobody checks whether they do them, or do them safely.

ability+ turns any laptop webcam into a home rehab assistant:

- **Patients** train at home with live guidance.
- **Physiotherapists** follow every session remotely, so one therapist can safely support many more people.
- **Anyone** who wants to keep body and mind active can use it too.

## Demo

Video: *coming soon*

## What it does

### For patients: three training modes

| Mode | What happens |
|---|---|
| **Movement** | Arm curls and sequential finger opposition. Pose tracking counts each repetition, gives live voice and on-screen feedback, and warns before the patient goes past their safe limit. A short animated guide ("Show me how") shows each exercise. |
| **Thinking** | Odd-one-out puzzles and memory sequences, answered hands-free by tilting the head, or by clicking. |
| **Both at once** (dual-task) | Hold a position (arm at the target angle, or an open hand) first on its own, then while answering simple questions with head tilts or clicks. The app compares how steady the hold was with and without thinking, which matters for everyday tasks. |

Also included:

- **Stop button** that ends an exercise at once and starts a calming breathing break.
- **Breathing break**: 60 seconds of paced breathing (4 s in, 6 s out) with a shoulder-tension reminder. It opens after the Stop button, on request, or **automatically when movement quality drops** (smaller range, much slower repetitions, or repeated misses). The exercise is paused meanwhile.
- **Voice feedback**, on by default. It can be turned off in Settings.
- **My progress**: a history of all sessions.
- **Messages** with the physiotherapist and their notes on each session.

### For physiotherapists

- A **patient list**, with sessions that need review at the top: those ended with the Stop button or that went past the safe limit.
- A **report for each session**: repetitions, angles, accuracy, breathing breaks and dual-task results.
- **Prescriptions**: start angle, target, safe limit, repetitions and side. They apply from the patient's next session.
- **Notes** on sessions and **messages** in both directions.
- Each patient's full data as a **JSON download**.

## Safety and privacy

- The app never diagnoses or prescribes. It only checks movement against limits the physiotherapist sets, and it **rejects unsafe prescriptions**.
- When the body is not clearly visible, feedback **pauses instead of guessing**.
- Video is processed **on the user's own computer** and never uploaded. Only numbers (angles, repetitions, events) are saved.

## Run it locally

**Requirements:** Python 3.10+, a webcam, and an internet connection the first time the thinking games load.

```bash
git clone https://github.com/younjimin/lauzhack.git
cd lauzhack
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install flask opencv-python mediapipe
python main.py
```

Then open **http://127.0.0.1:5000** in your browser.

The pose and hand models are in `models/`. If they are missing, download `pose_landmarker_full.task` and `hand_landmarker.task` into that folder.

### Demo accounts

The database and both accounts are created on first start, and the two accounts are already linked.

| Role | Email | Password |
|---|---|---|
| Patient | `patient@abilityplus.demo` | `demo1234` |
| Physiotherapist | `doctor@abilityplus.demo` | `demo1234` |

> [!TIP]
> To show both sides at once, open the patient in a normal browser window and the physiotherapist in a private window.

### Without a webcam

Play a recorded video instead:

```bash
REHAB_VIDEO=path/to/video.mp4 python main.py               # macOS / Linux
$env:REHAB_VIDEO="path\to\video.mp4"; python main.py       # Windows PowerShell
```

### Other options

| Variable | Effect |
|---|---|
| `GEM_DB=path.db` | Use a different database file (default `instance/abilityplus.db`) |
| `GEM_DEMO=0` | Do not create the demo accounts |

## Tests

```bash
python test_step2_exercises.py     # exercises, safety limits and the full API
python test_hand_side.py           # left/right hand detection
python test_rehab_modes.py         # dual-task, fatigue detection, breathing-break API
```

The tests use simulated pose data, so they need no webcam. They cover repetition counting, safety limits, left/right detection, dual-task scoring, fatigue detection and the full API (login, prescriptions, sessions, review notes, messages, permissions). Run them inside the virtual environment so Flask is found.

## Tech

| Part | Used |
|---|---|
| Backend | Python, Flask, OpenCV, MediaPipe pose and hand landmarks |
| Storage | SQLite with plain SQL, so it can move to PostgreSQL later |
| Frontend | HTML, CSS and JavaScript with no build step. The thinking games use the MediaPipe Face Landmarker in the browser. |
| Auth | Hashed passwords (Werkzeug) and session cookies, with separate patient and physiotherapist roles |

## Project structure

```
main.py              Flask app: camera thread, exercise sessions, dual-task, breathing-break pause, thinking-game results
auth_db.py           Login, SQLite database, physiotherapist and patient APIs, messages
analyzer.py          Exercise logic: angles, smoothing, repetition counting, safe-range checks
rehab_modes.py       Dual-task sessions, head-tilt answers, fatigue detection, shoulder tension
pose_detector.py     MediaPipe pose and hand detection
main_with_step2.py   Debug runner in an OpenCV window, for tuning thresholds on test videos
models/              MediaPipe pose and hand models
frontend/
  login.html         Sign in and registration
  gem.html           Patient app: Movement home, exercise screen, progress, settings
  cognitive.js       Training-type chooser and thinking games
  rehab-modes.js     Dual-task training and breathing break
  account-bar.js     Patient account panel: prescription, physiotherapist notes, messages
  doctor.html        Physiotherapist dashboard
docs/                Exercise logic notes (step2_README.md)
test_*.py            Tests
```

## Troubleshooting

| Problem | Fix |
|---|---|
| The camera does not open (macOS) | Allow camera access for Terminal or VS Code in System Settings → Privacy & Security → Camera. |
| The camera does not open (Windows) | Close other apps that use the webcam (Zoom, Teams, another browser tab). |
| The thinking games' camera does not start | They need internet access to load the face model the first time. You can also answer with mouse clicks. |
| Port 5000 is already in use (macOS) | Turn off AirPlay Receiver in System Settings. |
| The demo accounts don't work | An old database may still exist. Delete `instance/` and restart. |
| Tests are skipped or Flask is not found | Activate the virtual environment first (`source .venv/bin/activate`). |

## Limitations

This is a hackathon prototype:

- Angles are 2D estimates from a single camera.
- There is one camera per server, so the patient and the server run on the same computer.
- There is no verification of physiotherapist accounts, no password reset and no HTTPS. A real deployment would also need consent flows and medical-device review.
- Fatigue and dual-task thresholds are demo heuristics, not clinical cut-offs.

## Team

**GemGem**: Aly · Ana · Jimin · Jeongha
