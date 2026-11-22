# GEM — Adaptive AI Rehabilitation Assistant

Camera-guided upper-limb rehab, cognitive training, dual-task training and guided breathing breaks,
with a physiotherapist dashboard. Built for the IMChange Tech for Good hackathon.

> ⚠️ Training aid from a webcam estimate — **not a medical device and not a clinical measurement.**

## Demo
NOT YET

## Run it locally
Requirements: Python 3.10+ and a webcam.

```bash
git clone https://github.com/<team>/<repo>.git    
cd <repo>
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install flask opencv-python mediapipe
python main.py
```

Open **http://127.0.0.1:5000** in your browser.

### Demo accounts
| Role | Email | Password |
|---|---|---|
| Patient | patient@demo.gem | demo1234 |
| Physiotherapist | doctor@demo.gem | demo1234 |

### Without a webcam
Run with a recorded video instead:
```bash
REHAB_VIDEO=path/to/video.mp4 python main.py
```

### Tests
```bash
python test_step2_exercises.py
python test_hand_side.py
python test_rehab_modes.py
```

## Troubleshooting
- **Camera does not open (macOS):** allow camera access for Terminal / VS Code in
  System Settings → Privacy & Security → Camera.
- **Port 5000 already in use (macOS):** turn off AirPlay Receiver in System Settings.

## Team
- Aly
- Ana
- Jimin
- Jeongha
