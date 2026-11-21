# ability+ 마지막 정리

## 이름과 문구
- GEM → **ability+** (로고, 페이지 제목, 서버 출력, 데모 계정 `doctor@abilityplus.demo` / `patient@abilityplus.demo`, DB 파일 `instance/abilityplus.db`, 내려받는 파일 이름)
- 로그인 문구: **"Rehab that reaches every home."** + 한 문장 "For people who can't get to a clinic: guided exercises with any webcam, followed remotely by a physiotherapist." (소셜 굿: 병원에 가기 어려운 사람)
- 로그인 화면의 각도계 그림 삭제, 가운데 정렬 한 단
- "Prototype · video is processed on this computer and never uploaded" 삭제
- "GEM ADAPTIVE REHABILITATION PLATFORM / Choose Your Training Model" → **"What do you want to train today?"**, 카드 3개 (💪 Movement / 🧠 Thinking / 🤹 Both at once), 설명은 한 줄씩
- 메뉴: "Change training type" 버튼 삭제, 한 메뉴에 이모지 하나씩: 🏠 Overview, 💪 Movement, 🧠 Thinking, 🤹 Both at once, 📈 My progress, ⚙️ Settings
- 대문자 라벨(eyebrow), 버튼 안 이모지, 버튼의 "→", "AI-assisted" 같은 문구 제거 (이모지는 메뉴와 모드 카드에만). 상태 표시도 "● SESSION RUNNING" → "Running"처럼 평범하게

## 디자인
- 색: 예전 초록(#167b69) 유지. 빨강은 pain과 한계 초과에만 사용
- 글꼴: Atkinson Hyperlegible (저시력 사용자를 위해 만든 글꼴, Google Fonts에서 불러옴)
- 카드 hover 시 떠오르는 효과, 큰 그림자 제거
- 계정 바(이름 / My physiotherapist / Log out)를 화면 위에 떠 있던 위치에서 사이드바 안으로 옮김 (내용 가리지 않음)

## 말이 안 되던 것 / 안 쓰이던 것
| 전 | 후 |
|---|---|
| 환자 화면에 "Physiotherapist" 페이지: 가짜 환자 24명, Alex Morgan 등 | 삭제 (치료사는 /doctor에서 실제 데이터를 봄) |
| "Weekly consistency · sample", "Illustrative weekly performance" 가짜 차트 | DB의 실제 기록으로 그림 |
| 환자 기록이 브라우저 localStorage에만 있음 (기기 바꾸면 사라짐, DB와 따로 놂) | 계정의 DB 기록을 보여줌 |
| **인지 훈련 결과가 DB에 저장 안 됨** → 치료사가 못 봄 | `/api/cognitive/result`로 저장, 치료사 화면과 환자 기록에 표시 |
| 운동 화면 숫자 하드코딩 (160° / 100° / 85°, 5회, 10회) → 치료사가 처방을 바꿔도 화면은 그대로 | 치료사 처방 값에서 자동으로 채움 (설명, 단계 표시, 게이지 구간, 목표 횟수) |
| 게이지 빨간 구간이 "90° limit"로 고정 | 처방의 한계/목표로 계산 |
| 경고 음성 "do not bend past 90 degrees" (실제 한계 85°) | 처방의 한계 값을 그대로 말함 |
| 인지 훈련(브라우저 카메라)과 운동(서버 카메라)이 같은 웹캠을 동시에 잡으려 함 → Windows에서 실패 | 인지 훈련 카메라를 켤 때 서버 카메라를 먼저 끄고 화면 상태도 맞춤 |
| Connect 직후 Start → 400 에러, 카메라 실패해도 "connected" | 카메라가 실제로 켜질 때까지 기다리고, 실패하면 이유 표시 |
| `/login`, `/doctor`, `/gem-auth.js`가 main.py와 auth_db.py에 중복 정의 (main.py 쪽은 실행 안 됨) | main.py 쪽 삭제 |
| 세션을 DB와 `sessions/*.json` 두 곳에 저장 | DB만 |
| finger opposition에서 놓친 터치의 최소 거리가 항상 180으로 기록 | 실제 값 기록 |
| "Clear saved sessions" (환자가 치료사 기록까지 지울 수 있는 구조가 됨) | 삭제, "Download my history"만 남김 |
| 치료사 대시보드에 dual-task, 호흡 휴식, 인지 결과 표시가 디자인 버전에 없음 | 모두 표시 |

## 파일
- 새 파일: `frontend/account-bar.js` (예전 `gem-auth.js` 대체) → **`frontend/gem-auth.js`는 지우기**
- 수정: `main.py`, `auth_db.py`, `analyzer.py`, `main_with_step2.py`, `frontend/gem.html`, `cognitive.js`, `rehab-modes.js`, `login.html`, `doctor.html`, 테스트 2개
- 그대로: `pose_detector.py`, `rehab_modes.py`, `test_hand_side.py`

## 테스트
- `test_step2_exercises.py` 15/15, `test_rehab_modes.py` 25/25 (인지 결과 저장 테스트 추가), `test_hand_side.py` ALL PASS
- 브라우저로 로그인 → 모드 선택 → 개요 / 운동 / 기록 / 인지 게임 10문제 끝까지 → 듀얼태스크 → 치료사 화면까지 클릭해서 JS 에러 없음 확인
- **실제 웹캠으로는 확인 못 함** (여기엔 카메라가 없음). 데모 전에 한 번 돌려볼 것

## 처음 실행할 때
- DB 파일 이름이 바뀌어서 `instance/abilityplus.db`가 새로 생기고 데모 계정도 새로 만들어짐. 예전 `instance/gem.db`는 지워도 됨
