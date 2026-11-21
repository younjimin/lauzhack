/**
 * cognitive.js — ability+ thinking games
 *
 *  1. Training-type chooser shown after sign-in: movement, thinking, or both at once (dual-task).
 *  2. Thinking games: odd one out (logic) or memory sequence, answered with head movements
 *     (tilt or nod and hold 5 s, browser camera) or the mouse.
 *  Results are saved to the patient's account (/api/cognitive/result) so the physiotherapist sees them.
 */
(() => {
  // --------------------------------------------------
  // GAME 1: LOGICAL REASONING DATASET (10 ROUNDS)
  // --------------------------------------------------
  const LOGICAL_QUESTIONS = [
    {
      id: 1,
      skill: "Categorisation",
      prompt: "Identify the item that does not belong to the group:",
      options: [
        { icon: "🍎", label: "Apple", sub: "Fruit" },
        { icon: "🍌", label: "Banana", sub: "Fruit" },
        { icon: "🥕", label: "Carrot", sub: "Root vegetable" },
        { icon: "🍊", label: "Orange", sub: "Fruit" }
      ],
      answerIdx: 2,
      explanation: "Carrot is a root vegetable, while Apple, Banana, and Orange are fruits."
    },
    {
      id: 2,
      skill: "Categorisation",
      prompt: "Which item does not belong with the others?",
      options: [
        { icon: "🎻", label: "Violin", sub: "String instrument" },
        { icon: "🎸", label: "Guitar", sub: "String instrument" },
        { icon: "🥁", label: "Drum", sub: "Percussion" },
        { icon: "🎹", label: "Harp", sub: "String instrument" }
      ],
      answerIdx: 2,
      explanation: "Drum is a percussion instrument, whereas Violin, Guitar, and Harp are string instruments."
    },
    {
      id: 3,
      skill: "Analytical Thinking",
      prompt: "Find the number that breaks the pattern:",
      options: [
        { icon: "2️⃣", label: "2", sub: "Even number" },
        { icon: "4️⃣", label: "4", sub: "Even number" },
        { icon: "7️⃣", label: "7", sub: "Odd number" },
        { icon: "8️⃣", label: "8", sub: "Even number" }
      ],
      answerIdx: 2,
      explanation: "7 is an odd number; 2, 4, and 8 are all even numbers."
    },
    {
      id: 4,
      skill: "Categorisation",
      prompt: "Which vehicle does not belong in this category?",
      options: [
        { icon: "🚗", label: "Car", sub: "Land transport" },
        { icon: "🚌", label: "Bus", sub: "Land transport" },
        { icon: "⛵", label: "Sailboat", sub: "Water transport" },
        { icon: "🚲", label: "Bicycle", sub: "Land transport" }
      ],
      answerIdx: 2,
      explanation: "Sailboat travels on water, while Car, Bus, and Bicycle travel on land."
    },
    {
      id: 5,
      skill: "Analytical Thinking",
      prompt: "Spot the geometric shape that differs from the rest:",
      options: [
        { icon: "🔺", label: "Triangle", sub: "3 straight sides" },
        { icon: "⬜", label: "Square", sub: "4 straight sides" },
        { icon: "⭕", label: "Circle", sub: "Curved boundary" },
        { icon: "⬟", label: "Pentagon", sub: "5 straight sides" }
      ],
      answerIdx: 2,
      explanation: "Circle has no straight edges or corners, unlike Triangle, Square, and Pentagon."
    },
    {
      id: 6,
      skill: "Problem-Solving",
      prompt: "Which number does not fit the mathematical sequence?",
      options: [
        { icon: "🔢", label: "9", sub: "3 × 3" },
        { icon: "🔢", label: "16", sub: "4 × 4" },
        { icon: "🔢", label: "20", sub: "4 × 5" },
        { icon: "🔢", label: "25", sub: "5 × 5" }
      ],
      answerIdx: 2,
      explanation: "20 is not a perfect square, whereas 9 (3²), 16 (4²), and 25 (5²) are square numbers."
    },
    {
      id: 7,
      skill: "Categorisation",
      prompt: "Identify the object that does not belong:",
      options: [
        { icon: "🌡️", label: "Thermometer", sub: "Measures temperature" },
        { icon: "🧭", label: "Compass", sub: "Shows direction" },
        { icon: "⚖️", label: "Scale", sub: "Measures weight" },
        { icon: "🔨", label: "Hammer", sub: "Construction tool" }
      ],
      answerIdx: 3,
      explanation: "Hammer is a striking tool, while Thermometer, Compass, and Scale are measuring instruments."
    },
    {
      id: 8,
      skill: "Analytical Thinking",
      prompt: "Which word does not share the same logical relationship?",
      options: [
        { icon: "📖", label: "Chapter", sub: "Part of a book" },
        { icon: "📄", label: "Page", sub: "Part of a book" },
        { icon: "📚", label: "Library", sub: "Collection of books" },
        { icon: "🔖", label: "Index", sub: "Part of a book" }
      ],
      answerIdx: 2,
      explanation: "A Library contains many books, whereas Chapter, Page, and Index are parts inside a single book."
    },
    {
      id: 9,
      skill: "Problem-Solving",
      prompt: "Find the outlier in this sequence:",
      options: [
        { icon: "❄️", label: "Ice", sub: "Solid water" },
        { icon: "💧", label: "Rain", sub: "Liquid water" },
        { icon: "☁️", label: "Steam", sub: "Water vapor" },
        { icon: "🪨", label: "Granite", sub: "Igneous rock" }
      ],
      answerIdx: 3,
      explanation: "Granite is a rock, whereas Ice, Rain, and Steam are all physical states of water."
    },
    {
      id: 10,
      skill: "Problem-Solving",
      prompt: "Which item breaks the rule of this group?",
      options: [
        { icon: "🌍", label: "Earth", sub: "Planet" },
        { icon: "🪐", label: "Saturn", sub: "Planet" },
        { icon: "☀️", label: "Sun", sub: "Star" },
        { icon: "🔴", label: "Mars", sub: "Planet" }
      ],
      answerIdx: 2,
      explanation: "The Sun is a star at the center of our solar system, while Earth, Saturn, and Mars are planets."
    }
  ];

  // --------------------------------------------------
  // GAME 2: WORKING MEMORY & PATTERN RECALL TILES
  // --------------------------------------------------
  const MEMORY_TILES = [
    { icon: "🌿", label: "Forest", sub: "Top-Left" },
    { icon: "🌊", label: "Ocean", sub: "Top-Right" },
    { icon: "☀️", label: "Sun", sub: "Bottom-Left" },
    { icon: "⛰️", label: "Mountain", sub: "Bottom-Right" }
  ];
  const MEMORY_TOTAL_ROUNDS = 6;

  // Head-tracking tuning
  const HOLD_CONFIRM_MS = 5000;
  const ROLL_THRESHOLD_DEG = 7.0;
  const YAW_THRESHOLD_NORM = 0.085;
  const PITCH_THRESHOLD_NORM = 0.032;

  // --------------------------------------------------
  // STYLES
  // --------------------------------------------------
  const style = document.createElement("style");
  style.textContent = `
    #mode-gate {
      position: fixed;
      inset: 0;
      z-index: 9999;
      background: #f4f7f6;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    #mode-gate[hidden] { display: none !important; }
    .mode-box {
      max-width: 920px;
      width: 100%;
      background: #fff;
      border: 1px solid #e1eae6;
      border-radius: 12px;
      padding: 36px;
    }
    .mode-cards {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 20px;
      margin-top: 24px;
    }
    .mode-card {
      border: 2px solid #e1eae6;
      border-radius: 16px;
      padding: 24px;
      text-align: left;
      background: #FFFFFF;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 16px;
    }
    .mode-card:hover { border-color: #167b69; }
    .mode-card h3 { margin: 12px 0 4px; font-size: 22px; color: #19332f; }
    .mode-card p { margin: 0; }
    .mode-icon { width: 52px; height: 52px; border-radius: 12px; background: #e8f4ef;
      display: grid; place-items: center; font-size: 28px; }
    .cog-layout {
      display: grid;
      grid-template-columns: 1.55fr 1fr;
      gap: 18px;
      margin-top: 16px;
    }
    .cog-layout.mouse-only {
      grid-template-columns: 1fr;
    }
    .cog-options {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin: 18px 0;
    }
    .cog-option {
      border: 2px solid #e1eae6;
      border-radius: 14px;
      padding: 18px;
      background: #fff;
      text-align: left;
      display: flex;
      flex-direction: column;
      gap: 10px;
      position: relative;
      overflow: hidden;
      transition: all .15s ease;
    }
    .cog-option-row {
      display: flex;
      align-items: center;
      gap: 14px;
      width: 100%;
    }
    .cog-option.camera-locked {
      cursor: default;
    }
    .cog-option.focused {
      border-color: #167b69;
      background: #e8f4ef;
      box-shadow: 0 0 0 3px rgba(22, 123, 105, 0.22);
      transform: scale(1.01);
    }
    .cog-option.holding {
      border-color: #E08A1E;
      box-shadow: 0 0 0 3px rgba(224, 138, 30, 0.28);
    }
    .cog-option.flash-seq {
      border-color: #167b69;
      background: #e8f4ef;
      box-shadow: 0 0 0 4px rgba(22, 123, 105, 0.35);
      transform: scale(1.03);
    }
    .cog-option.correct {
      border-color: #1F7A4D;
      background: #E5F3EC;
    }
    .cog-option.wrong {
      border-color: #C2362F;
      background: #FBEDEC;
    }
    .cog-hold-track {
      width: 100%;
      height: 6px;
      border-radius: 999px;
      background: rgba(25, 51, 47, 0.12);
      overflow: hidden;
      display: none;
    }
    .cog-option.focused .cog-hold-track.visible {
      display: block;
    }
    .cog-hold-fill {
      height: 100%;
      width: 0%;
      background: #E08A1E;
      transition: width 0.08s linear;
    }
    .cog-opt-icon {
      font-size: 28px;
      width: 48px;
      height: 48px;
      border-radius: 12px;
      background: #f4f7f6;
      display: grid;
      place-items: center;
      flex-shrink: 0;
    }
    .cog-cam-wrap {
      background: #172a2a;
      border-radius: 12px;
      overflow: hidden;
      position: relative;
      aspect-ratio: 4 / 3;
      display: grid;
      place-items: center;
      color: #e1eae6;
    }
    .cog-cam-wrap video, .cog-cam-wrap canvas {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      transform: scaleX(-1);
    }
    .gesture-meter {
      margin-top: 10px;
      font-size: 12px;
    }
    .meter-bar {
      height: 8px;
      border-radius: 999px;
      background: #e1eae6;
      overflow: hidden;
      margin-top: 4px;
    }
    .meter-fill {
      height: 100%;
      background: #167b69;
      width: 50%;
      transition: width .08s linear;
    }
    .skill-pills { margin: 8px 0; font-size: 14px; }
    .cog-toolbar-row {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      margin-top: 12px;
    }
    /* Dropdown Picker (shows ONLY the currently chosen item until clicked) */
    .cog-dropdown {
      position: relative;
      display: inline-block;
    }
    .cog-dropdown-trigger {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 9px 14px;
      border-radius: 10px;
      background: #fff;
      border: 1.5px solid #167b69;
      color: #19332f;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
    }
    .cog-dropdown-trigger small {
      color: #5f6f6a;
      font-weight: 600;
    }
    .cog-dropdown-menu {
      position: absolute;
      top: calc(100% + 6px);
      left: 0;
      min-width: 240px;
      background: #fff;
      border: 1px solid #e1eae6;
      border-radius: 12px;
      padding: 6px;
      box-shadow: 0 12px 28px rgba(25, 51, 47, 0.14);
      z-index: 50;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .cog-dropdown-menu[hidden] {
      display: none !important;
    }
    .cog-dropdown-item {
      width: 100%;
      text-align: left;
      padding: 9px 12px;
      border-radius: 8px;
      background: transparent;
      color: #19332f;
      font-size: 13px;
      font-weight: 600;
    }
    .cog-dropdown-item:hover {
      background: #f4f7f6;
    }
    .cog-dropdown-item.selected {
      background: #e8f4ef;
      color: #167b69;
    }
    @media (max-width: 850px) {
      .mode-cards, .cog-layout, .cog-options { grid-template-columns: 1fr; }
    }
  `;
  document.head.appendChild(style);

  // --------------------------------------------------
  // 1. INJECT MODE SELECTION GATE (CLEAN TWO-CARD CHOICE)
  // --------------------------------------------------
  const modeGate = document.createElement("div");
  modeGate.id = "mode-gate";
  modeGate.innerHTML = `
    <div class="mode-box">
      <h1 style="margin:0 0 6px">What do you want to train today?</h1>
      <p class="muted" style="margin:0">You can switch any time from the menu.</p>

      <div class="mode-cards">
        <div class="mode-card">
          <div>
            <div class="mode-icon" aria-hidden="true">💪</div>
            <h3>Movement</h3>
            <p class="muted">Arm and finger exercises, counted by the camera.</p>
          </div>
          <button class="primary" id="choose-physical" aria-label="Start movement exercises">Start</button>
        </div>

        <div class="mode-card">
          <div>
            <div class="mode-icon" aria-hidden="true">🧠</div>
            <h3>Thinking</h3>
            <p class="muted">Puzzles and memory games, hands-free.</p>
          </div>
          <button class="primary" id="choose-cognitive" aria-label="Start thinking games">Start</button>
        </div>

        <div class="mode-card">
          <div>
            <div class="mode-icon" aria-hidden="true">🤹</div>
            <h3>Both at once</h3>
            <p class="muted">Hold a position while answering questions.</p>
          </div>
          <button class="primary" id="choose-dual" aria-label="Start dual-task training">Start</button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(modeGate);

  // --------------------------------------------------
  // 2. INJECT SIDEBAR SWITCHER & COGNITIVE WORKSPACE PAGE
  // --------------------------------------------------
  const sidebar = document.querySelector(".sidebar");
  const main = document.querySelector("main");

  if (sidebar && main) {
    // The "Thinking" menu item is in gem.html; create it only if it is missing.
    const firstNav = sidebar.querySelector("nav");
    if (!sidebar.querySelector('[data-page="cognitive"]') && firstNav) {
      const cogNavBtn = document.createElement("button");
      cogNavBtn.dataset.page = "cognitive";
      cogNavBtn.textContent = "🧠 Thinking";
      firstNav.appendChild(cogNavBtn);
    }

    const cogSection = document.createElement("section");
    cogSection.className = "page";
    cogSection.id = "cognitive";
    cogSection.innerHTML = `
      <div class="hero">
        <div>
          <h2 id="cog-hero-title">Odd one out</h2>
          <div class="muted" id="cog-hero-desc">
            Four items appear. Pick the one that does not belong with the others.
          </div>
          <div class="skill-pills muted" id="cog-skill-pills">Practises categorisation, analytical thinking and problem-solving.</div>

          <!-- Compact Dropdowns: Only show the active chosen game & control -->
          <div class="cog-toolbar-row">
            <div class="cog-dropdown" id="game-dropdown">
              <button type="button" class="cog-dropdown-trigger" id="game-dropdown-btn" aria-expanded="false">
                <small>Game</small>
                <span id="game-current-label">Odd one out</span>
                <span>▾</span>
              </button>
              <div class="cog-dropdown-menu" id="game-dropdown-menu" hidden>
                <button type="button" class="cog-dropdown-item selected" data-game-choice="logic">
                  Odd one out
                </button>
                <button type="button" class="cog-dropdown-item" data-game-choice="memory">
                  Memory sequence
                </button>
              </div>
            </div>

            <div class="cog-dropdown" id="control-dropdown">
              <button type="button" class="cog-dropdown-trigger" id="control-dropdown-btn" aria-expanded="false">
                <small>Answer with</small>
                <span id="control-current-label">Head movements</span>
                <span>▾</span>
              </button>
              <div class="cog-dropdown-menu" id="control-dropdown-menu" hidden>
                <button type="button" class="cog-dropdown-item selected" data-control-choice="camera">
                  Head movements (tilt and hold 5 s)
                </button>
                <button type="button" class="cog-dropdown-item" data-control-choice="mouse">
                  Mouse
                </button>
              </div>
            </div>
          </div>
        </div>

        <div class="controls">
          <button class="primary" id="cog-start-cam">Turn on camera</button>
          <button id="cog-recenter-btn" style="display:none">Reset centre</button>
          <button id="cog-start-session">Start</button>
        </div>
      </div>

      <div class="grid">
        <div class="card">
          <div class="metric-label">Round</div>
          <div class="metric" id="cog-progress">0 / 10</div>
          <small class="muted" id="cog-skill-tag">Skill: Categorisation</small>
        </div>
        <div class="card">
          <div class="metric-label">Correct</div>
          <div class="metric" id="cog-accuracy">—</div>
          <small class="muted" id="cog-acc-sub">Share of answers</small>
        </div>
        <div class="card">
          <div class="metric-label">Time per answer</div>
          <div class="metric" id="cog-speed">—</div>
          <small class="muted">Average</small>
        </div>
        <div class="card">
          <div class="metric-label">Selection</div>
          <div class="metric" id="cog-gesture-state">Waiting</div>
          <small class="muted" id="cog-gesture-sub">Tilt your head and hold for 5 s</small>
        </div>
      </div>

      <div class="cog-layout" id="cog-layout">
        <div class="card">
          <div class="session-header">
            <div>
              <div class="muted" id="cog-q-eyebrow"></div>
              <h2 id="cog-q-prompt" style="margin-top:4px">Press "Start" to begin</h2>
            </div>
            <span class="tag" id="cog-focus-badge">Highlighted: first item</span>
          </div>

          <div class="cog-options" id="cog-options"></div>

          <div class="feedback" id="cog-feedback" aria-live="polite">
            Tilt or nod your head up, down, left or right to move the highlight. Keep it there for 5 seconds to choose.
          </div>

          <div class="summary-card" id="cog-summary-card">
            <div class="session-header">
              <div>
                <h2 style="margin:4px 0 0" id="cog-summary-title">Done</h2>
              </div>
              <span class="tag" id="cog-saved-tag">Saving…</span>
            </div>
            <div class="summary-grid" id="cog-summary-grid"></div>
          </div>
        </div>

        <div class="card" id="cog-camera-panel">
          <h2>Head control</h2>
          <div class="muted" style="font-size:14px;margin-bottom:10px">
            Move your head to move the highlight. Hold still for 5 seconds to choose.
          </div>

          <div class="cog-cam-wrap">
            <video id="cog-video" autoplay playsinline muted></video>
            <canvas id="cog-canvas"></canvas>
            <div id="cog-cam-placeholder" style="text-align:center;padding:16px">
              <b>Camera off</b>
              <div class="muted" style="font-size:13px">Press "Turn on camera" to answer with head movements</div>
            </div>
          </div>

          <div class="gesture-meter">
            <div style="display:flex;justify-content:space-between">
              <span>Left or right</span>
              <span id="cog-tilt-val">Center</span>
            </div>
            <div class="meter-bar"><div class="meter-fill" id="cog-tilt-bar"></div></div>
          </div>

          <div class="gesture-meter">
            <div style="display:flex;justify-content:space-between">
              <span>Up or down</span>
              <span id="cog-pitch-val">Center</span>
            </div>
            <div class="meter-bar"><div class="meter-fill" id="cog-pitch-bar"></div></div>
          </div>

          <div class="gesture-meter">
            <div style="display:flex;justify-content:space-between">
              <span>Hold to choose</span>
              <span id="cog-hold-val">0.0 of 5 s</span>
            </div>
            <div class="meter-bar"><div class="meter-fill" id="cog-hold-bar" style="width:0%;background:#E08A1E"></div></div>
          </div>
        </div>
      </div>
    `;
    main.insertBefore(cogSection, main.querySelector("footer"));
  }

  // --------------------------------------------------
  // 3. COGNITIVE STATE (SUPPORTS BOTH GAMES + CAMERA/MOUSE)
  // --------------------------------------------------
  let cogGame = "logic";       // "logic" | "memory"
  let cogInputMode = "camera"; // "camera" | "mouse"
  let cogActive = false;
  let cogIndex = 0;
  let cogFocusIdx = 0;
  let cogCorrect = 0;
  let cogAnswered = false;
  let cogQuestionStart = 0;
  let cogDecisionTimes = [];
  let cogSkillStats = {};

  // Working Memory Game 2 state
  let memSequence = [];
  let memUserStep = 0;
  let memShowingPattern = false;

  // Smoothed Head-tilt hold tracking
  let holdStartedAt = null;
  let activeTiltDir = null;
  let neutralRoll = null;
  let neutralYaw = null;
  let neutralPitch = null;
  let smoothRoll = null;
  let smoothYaw = null;
  let smoothPitch = null;

  const $c = id => document.getElementById(id);

  function closeAllDropdowns() {
    const gm = $c("game-dropdown-menu");
    const cm = $c("control-dropdown-menu");
    const gb = $c("game-dropdown-btn");
    const cb = $c("control-dropdown-btn");
    if (gm) gm.hidden = true;
    if (cm) cm.hidden = true;
    if (gb) gb.setAttribute("aria-expanded", "false");
    if (cb) cb.setAttribute("aria-expanded", "false");
  }

  function stopFaceSensor() {
    if (faceRaf) {
      cancelAnimationFrame(faceRaf);
      faceRaf = null;
    }
    if (faceStream) {
      faceStream.getTracks().forEach(t => t.stop());
      faceStream = null;
    }
    const video = $c("cog-video");
    if (video) video.srcObject = null;
    const placeholder = $c("cog-cam-placeholder");
    if (placeholder) placeholder.style.display = "block";
    const startCamBtn = $c("cog-start-cam");
    if (startCamBtn) {
      startCamBtn.disabled = false;
      startCamBtn.textContent = "Turn on camera";
    }
    const recenterBtn = $c("cog-recenter-btn");
    if (recenterBtn) recenterBtn.style.display = "none";
    resetHoldTimer();
  }

  function setCogGame(game) {
    cogGame = game;
    cogActive = false;
    memShowingPattern = false;
    resetHoldTimer();
    closeAllDropdowns();

    // Update dropdown button label (shows ONLY the chosen game)
    const labelEl = $c("game-current-label");
    if (labelEl) {
      labelEl.textContent = game === "logic" ? "Odd one out" : "Memory sequence";
    }
    document.querySelectorAll("[data-game-choice]").forEach(item => {
      item.classList.toggle("selected", item.dataset.gameChoice === game);
    });

    $c("cog-summary-card").classList.remove("visible");

    if (game === "logic") {
      $c("cog-hero-title").textContent = "Odd one out";
      $c("cog-hero-desc").textContent = "Four items appear. Pick the one that does not belong with the others.";
      $c("cog-skill-pills").textContent = "Practises categorisation, analytical thinking and problem-solving.";
      $c("cog-progress").textContent = `0 / ${LOGICAL_QUESTIONS.length}`;
      $c("cog-skill-tag").textContent = "Skill: Categorisation";
      $c("cog-acc-sub").textContent = "Share of answers";
      $c("cog-q-prompt").textContent = 'Press "Start" to begin';
    } else {
      $c("cog-hero-title").textContent = "Memory sequence";
      $c("cog-hero-desc").textContent = "Tiles light up one after another. Repeat them in the same order.";
      $c("cog-skill-pills").textContent = "Practises working memory and attention.";
      $c("cog-progress").textContent = `0 / ${MEMORY_TOTAL_ROUNDS}`;
      $c("cog-skill-tag").textContent = "Skill: Working Memory";
      $c("cog-acc-sub").textContent = "Sequences repeated correctly";
      $c("cog-q-prompt").textContent = 'Press "Start" to begin';
    }

    $c("cog-options").innerHTML = "";
    $c("cog-accuracy").textContent = "—";
    $c("cog-speed").textContent = "—";
    updateCogFeedbackInstructions();
  }

  function setCogInputMode(mode) {
    cogInputMode = mode;
    resetHoldTimer();
    closeAllDropdowns();

    // Update dropdown button label (shows ONLY the chosen control)
    const labelEl = $c("control-current-label");
    if (labelEl) {
      labelEl.textContent = mode === "camera" ? "Head movements" : "Mouse";
    }
    document.querySelectorAll("[data-control-choice]").forEach(item => {
      item.classList.toggle("selected", item.dataset.controlChoice === mode);
    });

    const startCamBtn = $c("cog-start-cam");
    const camPanel = $c("cog-camera-panel");
    const layout = $c("cog-layout");
    const gestureSub = $c("cog-gesture-sub");
    const gestureState = $c("cog-gesture-state");
    const focusBadge = $c("cog-focus-badge");

    if (mode === "mouse") {
      stopFaceSensor();
      if (startCamBtn) startCamBtn.style.display = "none";
      if (camPanel) camPanel.style.display = "none";
      if (layout) layout.classList.add("mouse-only");
      if (gestureState) gestureState.textContent = "Mouse";
      if (gestureSub) gestureSub.textContent = "Click an item to choose it";
      if (focusBadge) focusBadge.style.display = "none";
    } else {
      if (startCamBtn) startCamBtn.style.display = "inline-block";
      if (camPanel) camPanel.style.display = "block";
      if (layout) layout.classList.remove("mouse-only");
      if (gestureState) gestureState.textContent = faceStream ? "Ready" : "Waiting";
      if (gestureSub) gestureSub.textContent = "Tilt your head and hold for 5 s";
      if (focusBadge) focusBadge.style.display = "inline-flex";
    }

    if (cogActive && !cogAnswered && !memShowingPattern) {
      if (cogGame === "logic") renderLogicQuestion();
      else renderMemoryTiles();
    } else {
      updateCogFeedbackInstructions();
    }
  }

  function updateCogFeedbackInstructions() {
    const fb = $c("cog-feedback");
    if (!fb) return;
    if (cogInputMode === "mouse") {
      fb.className = "feedback";
      fb.innerHTML = cogGame === "logic"
        ? `Click the item that does not belong with the others.`
        : `Watch the tiles light up, then click them in the same order.`;
    } else {
      fb.className = "feedback";
      fb.innerHTML = `Tilt or nod your head up, down, left or right to move the highlight. Keep it there for 5 seconds to choose.`;
    }
  }

  function resetHoldTimer() {
    holdStartedAt = null;
    activeTiltDir = null;
    const holdBar = $c("cog-hold-bar");
    const holdVal = $c("cog-hold-val");
    if (holdBar) holdBar.style.width = "0%";
    if (holdVal) holdVal.textContent = "0.0 of 5 s";

    document.querySelectorAll(".cog-option").forEach(el => {
      el.classList.remove("holding");
      const fill = el.querySelector(".cog-hold-fill");
      if (fill) fill.style.width = "0%";
    });
  }

  function activateCognitivePage() {
    document.querySelectorAll(".page").forEach(p => p.classList.toggle("active", p.id === "cognitive"));
    document.querySelectorAll("[data-page]").forEach(b => b.classList.toggle("active", b.dataset.page === "cognitive"));
    const eyebrow = $c("eyebrow");
    const title = $c("title");
    const subtitle = $c("subtitle");
    if (eyebrow) eyebrow.textContent = "";
    if (title) title.textContent = "Thinking games";
    if (subtitle) subtitle.textContent = "Answer with head movements or the mouse.";
  }

  // --------------------------------------------------
  // GAME 1 RENDER & SUBMISSION (LOGICAL REASONING)
  // --------------------------------------------------
  function renderLogicQuestion() {
    const q = LOGICAL_QUESTIONS[cogIndex];
    if (!q) return;

    cogAnswered = false;
    cogFocusIdx = 0;
    cogQuestionStart = Date.now();
    resetHoldTimer();

    const isCamera = cogInputMode === "camera";
    $c("cog-progress").textContent = `${cogIndex + 1} / ${LOGICAL_QUESTIONS.length}`;
    $c("cog-skill-tag").textContent = `Skill: ${q.skill}`;
    $c("cog-q-eyebrow").textContent = `Question ${cogIndex + 1} of ${LOGICAL_QUESTIONS.length}: ${q.skill.toLowerCase()}`;
    $c("cog-q-prompt").textContent = q.prompt;
    updateCogFeedbackInstructions();

    const box = $c("cog-options");
    box.innerHTML = q.options.map((opt, idx) => `
      <button type="button"
              class="cog-option ${isCamera && idx === cogFocusIdx ? "focused" : ""} ${isCamera ? "camera-locked" : ""}"
              data-opt-idx="${idx}">
        <div class="cog-option-row">
          <div class="cog-opt-icon">${opt.icon}</div>
          <div>
            <b style="font-size:17px">${opt.label}</b>
            <div class="muted" style="font-size:13px">${opt.sub}</div>
          </div>
        </div>
        <div class="cog-hold-track ${isCamera ? "visible" : ""}">
          <div class="cog-hold-fill"></div>
        </div>
      </button>
    `).join("");

    if (isCamera) updateCogFocus(0);
  }

  function submitLogicAnswer(selectedIdx) {
    if (!cogActive || cogAnswered) return;
    const q = LOGICAL_QUESTIONS[cogIndex];
    if (!q) return;

    cogAnswered = true;
    resetHoldTimer();

    const elapsed = Math.max(0.3, (Date.now() - cogQuestionStart) / 1000);
    cogDecisionTimes.push(elapsed);

    const isCorrect = selectedIdx === q.answerIdx;
    cogSkillStats[q.skill].total += 1;
    if (isCorrect) {
      cogCorrect += 1;
      cogSkillStats[q.skill].correct += 1;
    }

    const answeredCount = cogIndex + 1;
    const accPct = Math.round((cogCorrect / answeredCount) * 100);
    const avgSec = (cogDecisionTimes.reduce((a, b) => a + b, 0) / cogDecisionTimes.length).toFixed(1);

    $c("cog-accuracy").textContent = `${accPct}%`;
    $c("cog-speed").textContent = `${avgSec}s`;

    document.querySelectorAll(".cog-option").forEach((el, i) => {
      el.classList.remove("focused", "holding");
      if (i === q.answerIdx) el.classList.add("correct");
      else if (i === selectedIdx && !isCorrect) el.classList.add("wrong");
    });

    const fb = $c("cog-feedback");
    fb.className = isCorrect ? "feedback" : "feedback warn";
    fb.innerHTML = isCorrect
      ? `<b>Correct.</b> ${q.explanation}`
      : `<b>Not quite.</b> ${q.explanation}`;

    setTimeout(() => {
      cogIndex += 1;
      if (cogIndex < LOGICAL_QUESTIONS.length) {
        renderLogicQuestion();
      } else {
        finishCogSession();
      }
    }, 2200);
  }

  // --------------------------------------------------
  // GAME 2 RENDER & SUBMISSION (WORKING MEMORY SEQUENCE)
  // --------------------------------------------------
  function renderMemoryTiles(interactive = true) {
    const isCamera = cogInputMode === "camera" && interactive;
    const box = $c("cog-options");
    box.innerHTML = MEMORY_TILES.map((tile, idx) => `
      <button type="button"
              class="cog-option ${isCamera && idx === cogFocusIdx ? "focused" : ""} ${cogInputMode === "camera" ? "camera-locked" : ""}"
              data-opt-idx="${idx}">
        <div class="cog-option-row">
          <div class="cog-opt-icon">${tile.icon}</div>
          <div>
            <b style="font-size:17px">${tile.label}</b>
            <div class="muted" style="font-size:13px">${tile.sub}</div>
          </div>
        </div>
        <div class="cog-hold-track ${isCamera ? "visible" : ""}">
          <div class="cog-hold-fill"></div>
        </div>
      </button>
    `).join("");

    if (isCamera) updateCogFocus(cogFocusIdx);
  }

  function startMemoryRound() {
    cogAnswered = false;
    memShowingPattern = true;
    memUserStep = 0;
    cogFocusIdx = 0;
    resetHoldTimer();

    const seqLen = Math.min(5, 2 + Math.floor(cogIndex / 2));
    memSequence = Array.from({ length: seqLen }, () => Math.floor(Math.random() * 4));

    $c("cog-progress").textContent = `${cogIndex + 1} / ${MEMORY_TOTAL_ROUNDS}`;
    $c("cog-skill-tag").textContent = `${seqLen} tiles to remember`;
    $c("cog-q-eyebrow").textContent = `Round ${cogIndex + 1} of ${MEMORY_TOTAL_ROUNDS}`;
    $c("cog-q-prompt").textContent = `Watch the ${seqLen} tiles light up`;
    $c("cog-feedback").className = "feedback";
    $c("cog-feedback").textContent = "Just watch for now. You choose after the tiles stop.";

    renderMemoryTiles(false);

    memSequence.forEach((tileIdx, step) => {
      setTimeout(() => {
        const cards = document.querySelectorAll(".cog-option");
        cards.forEach(c => c.classList.remove("flash-seq"));
        if (cards[tileIdx]) cards[tileIdx].classList.add("flash-seq");
      }, 650 + step * 950);

      setTimeout(() => {
        const cards = document.querySelectorAll(".cog-option");
        if (cards[tileIdx]) cards[tileIdx].classList.remove("flash-seq");
      }, 650 + step * 950 + 620);
    });

    setTimeout(() => {
      if (!cogActive) return;
      memShowingPattern = false;
      cogQuestionStart = Date.now();
      $c("cog-q-prompt").textContent = `Your turn: tile 1 of ${memSequence.length}`;
      renderMemoryTiles(true);
      updateCogFeedbackInstructions();
    }, 650 + memSequence.length * 950 + 200);
  }

  function submitMemoryStep(selectedIdx) {
    if (!cogActive || cogAnswered || memShowingPattern) return;
    resetHoldTimer();

    const expectedIdx = memSequence[memUserStep];
    const cards = document.querySelectorAll(".cog-option");

    if (selectedIdx === expectedIdx) {
      const elapsed = Math.max(0.3, (Date.now() - cogQuestionStart) / 1000);
      cogDecisionTimes.push(elapsed);
      cogQuestionStart = Date.now();

      if (cards[selectedIdx]) {
        cards[selectedIdx].classList.add("correct");
        setTimeout(() => cards[selectedIdx]?.classList.remove("correct"), 450);
      }

      memUserStep += 1;
      if (memUserStep >= memSequence.length) {
        cogAnswered = true;
        cogCorrect += 1;
        const accPct = Math.round((cogCorrect / (cogIndex + 1)) * 100);
        const avgSec = (cogDecisionTimes.reduce((a, b) => a + b, 0) / cogDecisionTimes.length).toFixed(1);
        $c("cog-accuracy").textContent = `${accPct}%`;
        $c("cog-speed").textContent = `${avgSec}s`;

        $c("cog-feedback").className = "feedback";
        $c("cog-feedback").textContent = "Correct. The next round is coming.";

        setTimeout(() => {
          cogIndex += 1;
          if (cogIndex < MEMORY_TOTAL_ROUNDS) startMemoryRound();
          else finishCogSession();
        }, 1600);
      } else {
        $c("cog-q-prompt").textContent = `Good. Tile ${memUserStep + 1} of ${memSequence.length}`;
        $c("cog-feedback").className = "feedback";
        $c("cog-feedback").textContent = `${memUserStep} of ${memSequence.length} correct so far.`;
      }
    } else {
      cogAnswered = true;
      const accPct = Math.round((cogCorrect / (cogIndex + 1)) * 100);
      $c("cog-accuracy").textContent = `${accPct}%`;

      if (cards[selectedIdx]) cards[selectedIdx].classList.add("wrong");
      if (cards[expectedIdx]) cards[expectedIdx].classList.add("correct");

      $c("cog-feedback").className = "feedback warn";
      $c("cog-feedback").innerHTML = `<b>Not quite.</b> The next tile was ${MEMORY_TILES[expectedIdx].label}.`;

      setTimeout(() => {
        cogIndex += 1;
        if (cogIndex < MEMORY_TOTAL_ROUNDS) startMemoryRound();
        else finishCogSession();
      }, 2000);
    }
  }

  function handleOptionChosen(idx) {
    if (cogGame === "logic") submitLogicAnswer(idx);
    else submitMemoryStep(idx);
  }

  // --------------------------------------------------
  // SHARED FOCUS, SUMMARY & SESSION START
  // --------------------------------------------------
  function updateCogFocus(newIdx) {
    if (cogAnswered || memShowingPattern || cogInputMode !== "camera") return;
    cogFocusIdx = ((newIdx % 4) + 4) % 4;
    document.querySelectorAll(".cog-option").forEach((el, i) => {
      el.classList.toggle("focused", i === cogFocusIdx);
    });
    const badge = $c("cog-focus-badge");
    const items = cogGame === "logic" ? LOGICAL_QUESTIONS[cogIndex]?.options : MEMORY_TILES;
    if (badge && items && items[cogFocusIdx]) {
      badge.textContent = `Highlighted: ${items[cogFocusIdx].label}`;
    }
  }

  function moveFocusDirection(dir) {
    const row = Math.floor(cogFocusIdx / 2);
    const col = cogFocusIdx % 2;
    let nextRow = row;
    let nextCol = col;

    if (dir === "left" || dir === "right") nextCol = (col + 1) % 2;
    else if (dir === "up" || dir === "down") nextRow = (row + 1) % 2;

    updateCogFocus(nextRow * 2 + nextCol);
  }

  function finishCogSession() {
    cogActive = false;
    resetHoldTimer();
    const totalRounds = cogGame === "logic" ? LOGICAL_QUESTIONS.length : MEMORY_TOTAL_ROUNDS;
    const accPct = Math.round((cogCorrect / totalRounds) * 100);
    const avgSec = cogDecisionTimes.length
      ? (cogDecisionTimes.reduce((a, b) => a + b, 0) / cogDecisionTimes.length).toFixed(1)
      : "—";
    const totalSec = Math.round(cogDecisionTimes.reduce((a, b) => a + b, 0));

    const card = $c("cog-summary-card");
    const grid = $c("cog-summary-grid");
    $c("cog-summary-title").textContent = cogGame === "logic" ? "Odd one out: done" : "Memory sequence: done";

    grid.innerHTML = `
      <div class="summary-item"><span class="metric-label">Score</span><b>${cogCorrect} of ${totalRounds}</b></div>
      <div class="summary-item"><span class="metric-label">Correct</span><b>${accPct}%</b></div>
      <div class="summary-item"><span class="metric-label">Time per answer</span><b>${avgSec === "—" ? "–" : avgSec + " s"}</b></div>
      <div class="summary-item"><span class="metric-label">Answered with</span><b>${cogInputMode === "camera" ? "Head movements" : "Mouse"}</b></div>
    `;
    card.classList.add("visible");
    $c("cog-q-prompt").textContent = "Done. Your results are below.";
    $c("cog-feedback").className = "feedback";
    if (cogGame === "logic") {
      const skillSummary = Object.entries(cogSkillStats)
        .map(([k, v]) => `${k.toLowerCase()} ${v.correct} of ${v.total}`)
        .join(", ");
      $c("cog-feedback").textContent = `By skill: ${skillSummary}.`;
    } else {
      $c("cog-feedback").textContent = `You repeated ${cogCorrect} of ${totalRounds} sequences correctly.`;
    }

    const savedTag = $c("cog-saved-tag");
    savedTag.textContent = "Saving…";
    fetch("/api/cognitive/result", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        game: cogGame, correct: cogCorrect, total: totalRounds, seconds: totalSec,
        avg_sec: avgSec === "—" ? null : Number(avgSec), input: cogInputMode,
        skills: cogGame === "logic" ? cogSkillStats : null
      })
    }).then(r => { savedTag.textContent = r.ok ? "Saved" : "Not saved"; })
      .catch(() => { savedTag.textContent = "Not saved"; });
  }

  function startCogSession() {
    cogActive = true;
    cogIndex = 0;
    cogCorrect = 0;
    cogDecisionTimes = [];
    cogSkillStats = {
      Categorisation: { total: 0, correct: 0 },
      "Analytical Thinking": { total: 0, correct: 0 },
      "Problem-Solving": { total: 0, correct: 0 }
    };
    $c("cog-summary-card").classList.remove("visible");
    $c("cog-accuracy").textContent = "—";
    $c("cog-speed").textContent = "—";

    if (cogGame === "logic") renderLogicQuestion();
    else startMemoryRound();
  }

  // --------------------------------------------------
  // 4. RESPONSIVE 4-WAY HEAD-TILT/NOD & 5-SECOND HOLD ENGINE
  // --------------------------------------------------
  let faceLandmarker = null;
  let faceStream = null;
  let faceRaf = null;

  function resetHeadCalibration() {
    neutralRoll = null;
    neutralYaw = null;
    neutralPitch = null;
    smoothRoll = null;
    smoothYaw = null;
    smoothPitch = null;
    resetHoldTimer();
  }

  async function enableFaceControl() {
    if (cogInputMode !== "camera") {
      setCogInputMode("camera");
    }
    const btn = $c("cog-start-cam");
    btn.disabled = true;
    btn.textContent = "Loading…";

    try {
      // The exercise server may be using the webcam; free it for the browser first.
      await fetch("/api/camera/stop", { method: "POST" }).catch(() => {});
      window.dispatchEvent(new Event("ability:camera-released"));

      if (!faceLandmarker) {
        const vision = await import("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs");
        const fileset = await vision.FilesetResolver.forVisionTasks(
          "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm"
        );

        faceLandmarker = await vision.FaceLandmarker.createFromOptions(fileset, {
          baseOptions: {
            modelAssetPath:
              "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
          },
          runningMode: "VIDEO",
          numFaces: 1
        });
      }

      faceStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
      const video = $c("cog-video");
      video.srcObject = faceStream;
      await video.play();

      resetHeadCalibration();
      $c("cog-cam-placeholder").style.display = "none";
      $c("cog-gesture-state").textContent = "Active";
      $c("cog-recenter-btn").style.display = "inline-block";
      btn.textContent = "Camera on";

      if (!cogActive) startCogSession();
      detectFaceLoop();
    } catch (err) {
      console.error("Facial tracking init failed:", err);
      btn.disabled = false;
      btn.textContent = "Try camera again";
      $c("cog-feedback").textContent =
        "Could not start the camera (" + err.message + "). You can answer with the mouse instead.";
    }
  }

  function detectFaceLoop() {
    if (cogInputMode !== "camera" || !faceStream) return;

    const video = $c("cog-video");
    const canvas = $c("cog-canvas");
    if (!faceLandmarker || !video || video.readyState < 2) {
      faceRaf = requestAnimationFrame(detectFaceLoop);
      return;
    }

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const now = performance.now();
    const res = faceLandmarker.detectForVideo(video, now);

    if (res.faceLandmarks && res.faceLandmarks.length > 0) {
      const lm = res.faceLandmarks[0];

      const nose = lm[1];
      const forehead = lm[10];
      const chin = lm[152];
      const leftEye = lm[33];
      const rightEye = lm[263];
      const leftCheek = lm[234];
      const rightCheek = lm[454];

      ctx.strokeStyle = "rgba(0, 255, 204, 0.55)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(forehead.x * canvas.width, forehead.y * canvas.height);
      ctx.lineTo(chin.x * canvas.width, chin.y * canvas.height);
      ctx.moveTo(leftCheek.x * canvas.width, leftCheek.y * canvas.height);
      ctx.lineTo(rightCheek.x * canvas.width, rightCheek.y * canvas.height);
      ctx.stroke();

      ctx.fillStyle = "#00ffcc";
      ctx.beginPath();
      ctx.arc(nose.x * canvas.width, nose.y * canvas.height, 6, 0, Math.PI * 2);
      ctx.fill();

      const dx = rightEye.x - leftEye.x;
      const dy = rightEye.y - leftEye.y;
      const rawRoll = (Math.atan2(dy, dx) * 180) / Math.PI;

      const faceWidth = Math.hypot(rightCheek.x - leftCheek.x, rightCheek.y - leftCheek.y) || 0.2;
      const cheekMidX = (leftCheek.x + rightCheek.x) / 2;
      const rawYaw = (cheekMidX - nose.x) / faceWidth;

      const faceHeight = Math.hypot(chin.x - forehead.x, chin.y - forehead.y) || 0.2;
      const rawPitch = (nose.y - forehead.y) / faceHeight;

      smoothRoll = smoothRoll === null ? rawRoll : smoothRoll + 0.35 * (rawRoll - smoothRoll);
      smoothYaw = smoothYaw === null ? rawYaw : smoothYaw + 0.35 * (rawYaw - smoothYaw);
      smoothPitch = smoothPitch === null ? rawPitch : smoothPitch + 0.35 * (rawPitch - smoothPitch);

      if (neutralRoll === null) neutralRoll = smoothRoll;
      if (neutralYaw === null) neutralYaw = smoothYaw;
      if (neutralPitch === null) neutralPitch = smoothPitch;

      const relRoll = smoothRoll - neutralRoll;
      const relYaw = smoothYaw - neutralYaw;
      const relPitch = smoothPitch - neutralPitch;

      const horizScore = Math.max(
        Math.abs(relRoll) / ROLL_THRESHOLD_DEG,
        Math.abs(relYaw) / YAW_THRESHOLD_NORM
      );
      const horizSign = Math.abs(relRoll) / ROLL_THRESHOLD_DEG >= Math.abs(relYaw) / YAW_THRESHOLD_NORM
        ? Math.sign(relRoll)
        : Math.sign(relYaw);

      const vertScore = Math.abs(relPitch) / PITCH_THRESHOLD_NORM;
      const vertSign = Math.sign(relPitch);

      const horizPct = Math.max(0, Math.min(100, 50 + horizSign * horizScore * 28));
      $c("cog-tilt-bar").style.width = `${horizPct}%`;

      const pitchPct = Math.max(0, Math.min(100, 50 + vertSign * vertScore * 28));
      $c("cog-pitch-bar").style.width = `${pitchPct}%`;

      let detectedDir = null;
      if (horizScore > 1.0 || vertScore > 1.0) {
        if (vertScore > horizScore) {
          detectedDir = vertSign > 0 ? "down" : "up";
        } else {
          detectedDir = horizSign > 0 ? "right" : "left";
        }
      }

      if (detectedDir === "left" || detectedDir === "right") {
        $c("cog-tilt-val").textContent = detectedDir === "right" ? "Right" : "Left";
        $c("cog-pitch-val").textContent = "Centre";
      } else if (detectedDir === "up" || detectedDir === "down") {
        $c("cog-pitch-val").textContent = detectedDir === "up" ? "Up" : "Down";
        $c("cog-tilt-val").textContent = "Centre";
      } else {
        $c("cog-tilt-val").textContent = "Centre";
        $c("cog-pitch-val").textContent = "Centre";
      }

      if (detectedDir) {
        if (activeTiltDir !== detectedDir) {
          activeTiltDir = detectedDir;
          holdStartedAt = now;
          moveFocusDirection(detectedDir);
        }

        if (cogActive && !cogAnswered && !memShowingPattern && holdStartedAt !== null) {
          const heldMs = now - holdStartedAt;
          const holdSec = Math.min(HOLD_CONFIRM_MS / 1000, heldMs / 1000);
          const holdPct = Math.min(100, (heldMs / HOLD_CONFIRM_MS) * 100);

          $c("cog-hold-bar").style.width = `${holdPct}%`;
          $c("cog-hold-val").textContent = `${holdSec.toFixed(1)} of 5 s`;
          $c("cog-gesture-state").textContent = `${holdSec.toFixed(1)} s`;

          const cards = document.querySelectorAll(".cog-option");
          cards.forEach((card, i) => {
            const isFocused = i === cogFocusIdx;
            card.classList.toggle("holding", isFocused);
            const fill = card.querySelector(".cog-hold-fill");
            if (fill) fill.style.width = isFocused ? `${holdPct}%` : "0%";
          });

          if (heldMs >= HOLD_CONFIRM_MS) {
            handleOptionChosen(cogFocusIdx);
          }
        }
      } else {
        if (cogActive && !cogAnswered && !memShowingPattern) {
          $c("cog-gesture-state").textContent = "Tilt and hold";
        }
        resetHoldTimer();
      }
    }

    faceRaf = requestAnimationFrame(detectFaceLoop);
  }

  // --------------------------------------------------
  // 5. EVENT WIRING
  // --------------------------------------------------
  document.addEventListener("click", e => {
    const gameBtn = e.target.closest("#game-dropdown-btn");
    const ctrlBtn = e.target.closest("#control-dropdown-btn");
    const gameChoice = e.target.closest("[data-game-choice]");
    const ctrlChoice = e.target.closest("[data-control-choice]");

    if (gameBtn) {
      const menu = $c("game-dropdown-menu");
      const willOpen = menu.hidden;
      closeAllDropdowns();
      menu.hidden = !willOpen;
      gameBtn.setAttribute("aria-expanded", String(willOpen));
      return;
    }

    if (ctrlBtn) {
      const menu = $c("control-dropdown-menu");
      const willOpen = menu.hidden;
      closeAllDropdowns();
      menu.hidden = !willOpen;
      ctrlBtn.setAttribute("aria-expanded", String(willOpen));
      return;
    }

    if (gameChoice) {
      setCogGame(gameChoice.dataset.gameChoice);
      return;
    }

    if (ctrlChoice) {
      setCogInputMode(ctrlChoice.dataset.controlChoice);
      return;
    }

    if (!e.target.closest(".cog-dropdown")) {
      closeAllDropdowns();
    }

    if (e.target.id === "choose-physical") {
      stopFaceSensor();
      modeGate.hidden = true;
      const overviewBtn = document.querySelector('[data-page="overview"]');
      if (overviewBtn) overviewBtn.click();
    } else if (e.target.id === "choose-cognitive") {
      modeGate.hidden = true;
      activateCognitivePage();
      setCogInputMode(cogInputMode);
    } else if (e.target.dataset && e.target.dataset.page === "cognitive") {
      activateCognitivePage();
    } else if (e.target.id === "cog-start-cam") {
      enableFaceControl();
    } else if (e.target.id === "cog-recenter-btn") {
      resetHeadCalibration();
    } else if (e.target.id === "cog-start-session") {
      startCogSession();
    } else {
      const optBtn = e.target.closest(".cog-option");
      if (optBtn && cogInputMode === "mouse" && cogActive && !cogAnswered && !memShowingPattern) {
        const idx = Number(optBtn.dataset.optIdx);
        handleOptionChosen(idx);
      }
    }
  });
})();