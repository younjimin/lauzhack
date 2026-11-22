ability+

Home rehabilitation with a laptop webcam, supervised remotely by a physiotherapist. Camera-guided upper-limb exercises, cognitive training, dual-task training and guided breathing breaks, plus a physiotherapist dashboard.

Built by team GEMGEM for the IMChange Tech for Good challenge at LauzHack.

Note: this is a training aid based on webcam estimates. It is not a medical device, and its angles are not clinical measurements.

Why

In many developing countries, people who need rehabilitation can't reach a clinic, and the few NGO physiotherapists there have far more patients than they can see in person. Patients are sent home with a sheet of exercises and nobody checks whether they do them, or do them safely.

ability+ turns any laptop webcam into a home rehab assistant. Patients train at home, and their physiotherapist follows every session remotely, so one therapist can safely support many more people. Anyone else who wants to keep body and mind active can use it too.

Demo

Not yet available.

What it does

For patients, three training modes

Mode	What happens
Movement	Arm curls and finger opposition. Pose tracking counts each repetition, gives live voice and on-screen feedback, and warns before the patient goes past their safe limit.
Thinking	Odd-one-out puzzles and memory sequences, answered hands-free by tilting the head, or with the mouse.
Both at once (dual-task)	Hold a position while answering questions. Compares control with and without thinking, which matters for everyday tasks.

There are also a pain stop button, an automatic breathing break when movement quality drops, and a history of all sessions.

For physiotherapists

A list of patients, with sessions that need review (pain or unsafe movement) at the top
A per-session report: repetitions, angles, accuracy, breaks and dual-task results
Prescriptions: start angle, target, safe limit, repetitions and side, used from the patient's next session
Notes on sessions and messages in both directions
Each patient's full data as a JSON download
Safety and privacy
The app never diagnoses or prescribes. It only checks movement against limits a physiotherapist sets, and it rejects unsafe prescriptions.
When the body is not clearly visible, feedback pauses instead of guessing.
Video is processed on the user's computer and never uploaded. Only numbers (angles, repetitions, events) are saved.
Run it locally

Requires Python 3.10+ and a webcam.

bash
git clone https://github.com/younjimin/lauzhack.git
cd lauzhack
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install flask opencv-python mediapipe
python main.py

Open http://127.0.0.1:5000 in your browser.

The pose and hand models live in models/. If they are missing, download them into that folder: pose_landmarker_full.task, hand_landmarker.task.

Demo accounts

The database and both accounts are created on first start. The two accounts are already linked.

Role	Email	Password
Patient	patient@abilityplus.demo	demo1234
Physiotherapist	doctor@abilityplus.demo	demo1234

To show both sides at once, open the patient in a normal window and the physiotherapist in a private window.

Without a webcam

Run with a recorded video instead:

bash
REHAB_VIDEO=path/to/video.mp4 python main.py               # macOS / Linux
$env:REHAB_VIDEO="path\to\video.mp4"; python main.py       # Windows PowerShell

Other options: GEM_DB=path.db uses a different database file, and GEM_DEMO=0 skips the demo accounts.

Tests
bash
python test_step2_exercises.py
python test_hand_side.py
python test_rehab_modes.py

The tests use simulated pose data, so they need no webcam. They cover repetition counting, safety limits, left/right detection, dual-task scoring, fatigue detection and the full API (login, prescriptions, sessions, review notes, messages, permissions).

Tech
Backend: Python, Flask, MediaPipe (pose and hand landmarks), OpenCV
Storage: SQLite with plain SQL, so it can move to PostgreSQL later
Frontend: HTML, CSS and JavaScript with no build step. The thinking games use MediaPipe Face Mesh in the browser.
Auth: hashed passwords (Werkzeug) and session cookies, with separate patient and physiotherapist roles
Project structure
main.py              Flask app: camera thread, exercise sessions, dual-task, thinking-game results
auth_db.py           Login, SQLite database, physiotherapist and patient APIs, messages
analyzer.py          Exercise logic: angles, smoothing, repetition counting, safe-range checks
rehab_modes.py       Dual-task sessions, fatigue detection, head-tilt answers, shoulder tension
pose_detector.py     MediaPipe pose and hand detection
main_with_step2.py   Debug runner in an OpenCV window, for tuning thresholds on test videos
frontend/
  login.html         Sign in and registration
  gem.html           Patient app: overview, movement exercises, progress, settings
  cognitive.js       Training-type chooser and thinking games
  rehab-modes.js     Dual-task training and breathing break
  account-bar.js     Patient account panel: prescription, physiotherapist notes, messages
  doctor.html        Physiotherapist dashboard
test_*.py            Tests
Troubleshooting
The camera does not open (macOS): allow camera access for Terminal or VS Code in System Settings → Privacy & Security → Camera.
The camera does not open (Windows): close other apps that use the webcam (Zoom, Teams, another browser tab).
Port 5000 is already in use (macOS): turn off AirPlay Receiver in System Settings.
The demo accounts don't work: an old database may still exist. Delete instance/ and restart.
Limitations

This is a hackathon prototype:

Angles are 2D estimates from one camera.
There is one camera per server, so the patient and the server run on the same computer.
There is no verification of physiotherapist accounts, no password reset and no HTTPS. A real deployment would also need consent flows and medical-device review.
Fatigue and dual-task thresholds are demo heuristics, not clinical cut-offs.
Team
Aly
Ana
Jimin
Jeongha
