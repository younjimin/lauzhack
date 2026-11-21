/*
 * rehab-modes.js — Dual-task mode + Guided breathing & fatigue recovery.
 * main.py adds this file to gem.html automatically (after cognitive.js and gem-auth.js).
 *
 * 1. Dual-task training: hold a posture (arm curl at the prescribed angle, or an open hand)
 *    first alone, then while answering two-choice questions by tilting the head (or clicking).
 *    Backend: /api/dual/start | state | answer | stop  (rehab_modes.DualTaskSession)
 * 2. Guided breathing break (60 s): opens after a Pain stop, when the backend reports a sharp drop
 *    in movement quality (tracking.fatigue_alert), or from the "Breathing break" button.
 *    The physical session is paused meanwhile (/api/session/pause, /api/session/resume).
 */
(() => {
  const $ = id => document.getElementById(id);
  const el = (tag, props = {}, kids = []) => {
    const n = Object.assign(document.createElement(tag), props);
    [].concat(kids).forEach(k => k != null && n.append(k));
    return n;
  };
  const api = async (url, opts = {}) => {
    const r = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...opts });
    if (r.status === 401) { location.href = '/login'; throw new Error('Logged out'); }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || `Server error (${r.status})`);
    return d;
  };
  const post = (url, body = {}) => api(url, { method: 'POST', body: JSON.stringify(body) });
  const reduced = () => document.body.classList.contains('reduce') ||
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

  // Uses gem.html's prioritised voice (speak(text, level)) when present.
  function talk(text, level = 'info') {
    if (!text) return;
    try { if (typeof speak === 'function') { speak(text, level); return; } } catch (_) {}
    try {
      if ($('audio') && !$('audio').checked) return;
      speechSynthesis.cancel();
      speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    } catch (_) {}
  }

  // --------------------------------------------------
  // STYLES
  // --------------------------------------------------
  document.head.append(el('style', { textContent: `
    #rm-breath { position: fixed; inset: 0; z-index: 10000; background: rgba(15, 40, 36, .55);
      display: grid; place-items: center; padding: 20px; }
    #rm-breath[hidden] { display: none !important; }
    #rm-breath .card { width: min(520px, 100%); text-align: center; }
    .rm-circle-wrap { height: 230px; display: grid; place-items: center; margin: 10px 0; }
    .rm-circle { width: 200px; height: 200px; border-radius: 50%; display: grid; place-items: center;
      background: radial-gradient(circle at 40% 35%, #d1f2e6, #8fd3bd); color: #0f5132; font-weight: 800; font-size: 20px;
      transform: scale(.55); transition-property: transform; transition-timing-function: ease-in-out; }
    .rm-circle.in { transform: scale(1); transition-duration: 4s; }
    .rm-circle.out { transform: scale(.55); transition-duration: 6s; }
    body.reduce .rm-circle, .rm-still .rm-circle { transform: none !important; transition: none !important; }
    .rm-bar { height: 8px; border-radius: 99px; background: #e1eae6; overflow: hidden; margin: 12px 0 4px; }
    .rm-bar i { display: block; height: 100%; width: 0; background: #167b69; }
    .rm-posture { min-height: 22px; font-size: 13px; margin-top: 8px; }
    .rm-posture.warn { color: #8a5a1c; font-weight: 700; }
    .rm-row { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; margin-top: 16px; }
    .rm-break-btn { background: #e8f4ef; color: #167b69; }

    .rm-layout { display: grid; grid-template-columns: 1.25fr 1fr; gap: 14px; margin-top: 14px; }
    .rm-video { background: #172a2a; border-radius: 12px; aspect-ratio: 4 / 3; overflow: hidden; display: grid;
      place-items: center; color: #d9e8e2; position: relative; }
    .rm-video img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; display: none; }
    .rm-gauge { position: relative; height: 16px; border-radius: 8px; background: #f1d5d4; margin: 12px 0 4px; overflow: hidden; }
    .rm-gauge .zone { position: absolute; top: 0; bottom: 0; background: #b7e0d2; }
    .rm-gauge .needle { position: absolute; top: -2px; bottom: -2px; width: 4px; background: #19332f; left: 0; }
    .rm-motor { font-weight: 700; min-height: 22px; }
    .rm-motor.bad { color: #b03a35; }
    .rm-phase { font-size: 12px; letter-spacing: 1px; font-weight: 800; color: #71817d; }
    .rm-question { font-size: 24px; font-weight: 800; margin: 8px 0 14px; min-height: 64px; }
    .rm-options { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .rm-opt { border: 2px solid #e1eae6; border-radius: 14px; padding: 18px 12px; background: #fff; font-size: 20px;
      font-weight: 800; position: relative; overflow: hidden; min-height: 86px; }
    .rm-opt small { display: block; font-size: 11px; color: #71817d; font-weight: 700; letter-spacing: .5px; }
    .rm-opt .fill { position: absolute; left: 0; bottom: 0; height: 6px; width: 0; background: #e67e22; }
    .rm-opt.lean { border-color: #e67e22; }
    .rm-opt.correct { border-color: #0f5132; background: #d1f2e6; }
    .rm-opt.wrong { border-color: #d9534f; background: #fbe3e1; }
    .rm-opt:disabled { opacity: 1; cursor: default; }
    .rm-stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }
    .rm-stats .card { padding: 12px; }
    .rm-stats b { display: block; font-size: 22px; }
    .rm-why { font-size: 13px; }
    @media (max-width: 900px) { .rm-layout, .rm-stats { grid-template-columns: 1fr 1fr; } .rm-layout { grid-template-columns: 1fr; } }
  ` }));

  // ==================================================
  // 1. GUIDED BREATHING & FATIGUE RECOVERY (60 s)
  // ==================================================
  const BREATH_SEC = 60, IN_SEC = 4, OUT_SEC = 6;           // 6 slow breaths per minute
  const TIPS = ['Let your shoulders drop away from your ears', 'Unclench your jaw and soften your hands',
                'Sit tall and let your back rest', 'Notice your feet on the floor'];

  const circle = el('div', { className: 'rm-circle', textContent: 'Ready' });
  const bTitle = el('h2', { textContent: 'Breathing break' });
  const bReason = el('div', { className: 'muted' });
  const bCount = el('div', { className: 'muted', style: 'font-weight:700' });
  const bBar = el('i');
  const bTip = el('div', { className: 'muted', style: 'margin-top:6px' });
  const bPosture = el('div', { className: 'rm-posture muted' });
  const bButtons = el('div', { className: 'rm-row' });
  const breath = el('div', { id: 'rm-breath', hidden: true, role: 'dialog', ariaModal: 'true', ariaLabel: 'Breathing break' }, [
    el('div', { className: 'card' }, [
      el('div', { className: 'eyebrow', textContent: 'GUIDED RECOVERY' }), bTitle, bReason,
      el('div', { className: 'rm-circle-wrap' }, circle), bCount, el('div', { className: 'rm-bar' }, bBar), bTip, bPosture, bButtons,
    ]),
  ]);
  document.body.append(breath);

  let bTimer = null, bPostureTimer = null, bState = null;

  function breathButtons(list) {
    bButtons.innerHTML = '';
    list.forEach(([label, fn, primary]) => {
      const b = el('button', { type: 'button', textContent: label, className: primary ? 'primary' : '' });
      b.onclick = fn;
      bButtons.append(b);
    });
    bButtons.querySelector('button')?.focus();
  }

  async function checkPosture() {
    if (!bState) return;
    try {
      const d = await api('/api/tracking');
      const r = d.shoulder_ratio;
      if (!d.camera_connected) { bPosture.textContent = ''; return; }
      if (r == null) { bPosture.className = 'rm-posture muted'; bPosture.textContent = 'Posture check: keep your face and shoulders in view'; return; }
      bState.maxRatio = Math.max(bState.maxRatio || 0, r);
      const tense = r < 0.85 * bState.maxRatio;
      bState.tenseHits = tense ? bState.tenseHits + 1 : 0;
      if (bState.tenseHits >= 2) {
        bPosture.className = 'rm-posture warn';
        bPosture.textContent = '↓ Your shoulders look raised — let them drop';
        if (Date.now() - (bState.lastTensionSpoken || 0) > 10000) {
          bState.lastTensionSpoken = Date.now();
          bState.tensionReminders += 1;
          talk('Your shoulders look raised. Let them drop.', 'caution');
        }
      } else if (!tense) {
        bPosture.className = 'rm-posture muted';
        bPosture.textContent = '✓ Shoulders relaxed';
      }
    } catch (_) {}
  }

  function finishBreathing(completed) {
    clearInterval(bTimer); clearInterval(bPostureTimer);
    bTimer = bPostureTimer = null;
    const st = bState;
    const seconds = Math.round((Date.now() - st.start) / 1000);
    circle.className = 'rm-circle';
    circle.textContent = completed ? 'Well done' : 'Paused';
    bBar.style.width = '100%';
    bCount.textContent = completed ? 'Break complete' : `Stopped after ${seconds}s`;
    if (completed) talk('Well done. Your break is complete.', 'info');
    const result = { completed, seconds, tensionReminders: st.tensionReminders };
    const close = () => { breath.hidden = true; bState = null; };
    if (st.opts.trigger === 'pain') {
      bTip.textContent = 'If the pain continues, rest and let your physiotherapist know.';
      const msgBtn = document.querySelector('#gem-acct button:nth-child(2)');
      breathButtons([
        ...(msgBtn ? [['💬 Message my physiotherapist', () => { close(); msgBtn.click(); st.opts.onEnd?.(result); }, true]] : []),
        ['Close', () => { close(); st.opts.onEnd?.(result); }, !msgBtn],
      ]);
    } else {
      bTip.textContent = 'How do you feel? Continue only if you are comfortable.';
      breathButtons([
        ['▶ Continue exercise', () => { close(); st.opts.onContinue?.(result); }, true],
        ['■ End session', () => { close(); st.opts.onEnd?.(result); }],
      ]);
    }
  }

  function openBreathing(opts = {}) {
    if (bState) return;                                    // already open
    bState = { opts, start: Date.now(), phase: null, tenseHits: 0, tensionReminders: 0, maxRatio: 0 };
    breath.hidden = false;
    breath.classList.toggle('rm-still', reduced());
    bTitle.textContent = opts.trigger === 'pain' ? 'Let’s rest for a minute' : 'Time for a short breathing break';
    bReason.textContent = opts.trigger === 'pain' ? 'You stopped because of pain. Slow breathing can help you settle.'
      : opts.trigger === 'fatigue' ? `${opts.reason || 'Your movement quality dropped'} — a short rest usually helps.`
      : 'Take a minute to breathe and reset your posture.';
    bPosture.textContent = '';
    bTip.textContent = TIPS[0];
    breathButtons([['Skip', () => finishBreathing(false)]]);
    talk(opts.trigger === 'pain' ? 'Let’s rest for a minute. Follow the circle and breathe slowly.'
      : 'Let’s take a short break. Follow the circle and breathe slowly.', 'info');

    const tick = () => {
      if (!bState) return;
      const el_ = (Date.now() - bState.start) / 1000;
      if (el_ >= BREATH_SEC) { finishBreathing(true); return; }
      const inCycle = el_ % (IN_SEC + OUT_SEC);
      const cycle = Math.floor(el_ / (IN_SEC + OUT_SEC));
      const phase = inCycle < IN_SEC ? 'in' : 'out';
      if (phase !== bState.phase) {
        bState.phase = phase;
        circle.className = 'rm-circle ' + phase;
        circle.textContent = phase === 'in' ? 'Breathe in' : 'Breathe out';
        if (phase === 'in') {
          bTip.textContent = TIPS[cycle % TIPS.length];
          if (cycle > 0 && cycle % 2 === 0) talk(TIPS[cycle % TIPS.length], 'info');
          else talk('Breathe in', 'info');
        } else {
          talk('and slowly out', 'info');
        }
      }
      const left = Math.ceil(phase === 'in' ? IN_SEC - inCycle : IN_SEC + OUT_SEC - inCycle);
      bCount.textContent = `${circle.textContent} · ${left} · ${Math.ceil(BREATH_SEC - el_)}s left`;
      bBar.style.width = `${(el_ / BREATH_SEC) * 100}%`;
    };
    tick();
    bTimer = setInterval(tick, 200);
    bPostureTimer = setInterval(checkPosture, 700);
  }

  document.addEventListener('keydown', e => { if (e.key === 'Escape' && bState && bTimer) finishBreathing(false); });
  window.GEMBreathing = { open: openBreathing };

  // ---- hooks into the physical exercise screen (gem.html) ----
  const painBtn = $('pain');
  if (painBtn) painBtn.addEventListener('click', () => setTimeout(() => openBreathing({ trigger: 'pain' }), 1500));

  let pausedHere = false;
  async function pauseAndBreathe(trigger, reason) {
    try { await post('/api/session/pause', { trigger }); pausedHere = true; } catch (_) { pausedHere = false; }
    openBreathing({
      trigger, reason,
      onContinue: async r => { if (pausedHere) await post('/api/session/resume', r).catch(() => {}); pausedHere = false; },
      onEnd: async r => {
        if (pausedHere) await post('/api/session/resume', r).catch(() => {});
        pausedHere = false;
        if ($('finish') && !$('finish').disabled) $('finish').click();
      },
    });
  }

  // Manual "Breathing break" button next to the pain button
  if (painBtn) {
    const breakBtn = el('button', { type: 'button', className: 'rm-break-btn', textContent: '☕ Breathing break' });
    painBtn.after(breakBtn);
    breakBtn.onclick = async () => {
      let running = false;
      try { running = (await api('/api/tracking')).running; } catch (_) {}
      if (running) pauseAndBreathe('manual');
      else openBreathing({ trigger: 'manual', onContinue: () => {}, onEnd: () => {} });
    };
  }

  // Automatic break when movement quality drops sharply (backend FatigueMonitor)
  let lastAlert = null;
  setInterval(async () => {
    if (bState || !$('session')?.classList.contains('active')) return;
    try {
      const d = await api('/api/tracking');
      const a = d.fatigue_alert;
      if (d.running && !d.paused && a && a.id !== lastAlert) {
        lastAlert = a.id;
        pauseAndBreathe('fatigue', a.message);
      }
    } catch (_) {}
  }, 1000);

  // ==================================================
  // 2. DUAL-TASK TRAINING PAGE
  // ==================================================
  const sidebar = document.querySelector('.sidebar');
  const main = document.querySelector('main');
  if (!sidebar || !main) return;

  const navBtn = el('button', { textContent: '🧠💪 Dual-task training' });
  navBtn.dataset.page = 'dual';
  sidebar.querySelector('nav')?.append(navBtn);

  const page = el('section', { className: 'page', id: 'dual' });
  page.innerHTML = `
    <div class="hero">
      <div>
        <div class="eyebrow">DUAL-TASK TRAINING · BODY + MIND</div>
        <h2>Hold steady while you think</h2>
        <div class="muted">First hold the position on its own, then keep holding while you answer questions.
          Tilt or turn your head towards your answer and hold for a moment — or click it.</div>
        <div class="muted rm-why" style="margin-top:8px">💡 Everyday life asks us to move and think at the same time.
          Practising both together trains the control you need for real situations.</div>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <div class="controls">
        <div class="toolbar-group">
          <select id="rm-posture" aria-label="Posture">
            <option value="curl_hold">💪 Arm curl hold (your target angle)</option>
            <option value="hand_open">🖐️ Open hand hold</option>
          </select>
          <select id="rm-answer" aria-label="How to answer">
            <option value="head">🙂 Head tilt or click</option>
            <option value="click">🖱️ Click / arrow keys only</option>
          </select>
          <select id="rm-count" aria-label="Number of questions">
            <option value="4">4 questions</option><option value="6" selected>6 questions</option><option value="8">8 questions</option>
          </select>
        </div>
        <div class="toolbar-group">
          <button class="primary" id="rm-connect">📷 Connect camera</button>
          <button class="primary" id="rm-start" disabled>▶ Start</button>
          <button id="rm-stop" disabled>■ Stop &amp; save</button>
          <button class="danger" id="rm-pain" disabled>⚠ Pain — stop now</button>
        </div>
      </div>
    </div>

    <div class="rm-layout">
      <div class="card">
        <div class="rm-video"><img id="rm-video" alt="Live camera with pose tracking">
          <div id="rm-video-ph" style="text-align:center"><div style="font-size:32px">📷</div><b>Camera off</b></div></div>
        <div class="rm-gauge" aria-hidden="true"><div class="zone" id="rm-zone"></div><div class="needle" id="rm-needle"></div></div>
        <div style="display:flex;justify-content:space-between;font-size:11px" class="muted"><span>0°</span><span id="rm-gauge-label">target zone</span><span>180°</span></div>
        <div class="rm-motor" id="rm-motor" aria-live="polite" style="margin-top:8px">Connect the camera to begin.</div>
      </div>
      <div class="card">
        <div class="rm-phase" id="rm-phase">NOT STARTED</div>
        <div class="rm-question" id="rm-question">Press Start, then get into position.</div>
        <div class="rm-options">
          <button class="rm-opt" id="rm-opt-left" disabled><small>← LEFT</small><span>—</span><i class="fill"></i></button>
          <button class="rm-opt" id="rm-opt-right" disabled><small>RIGHT →</small><span>—</span><i class="fill"></i></button>
        </div>
        <div class="feedback" id="rm-feedback" aria-live="polite" style="margin-top:12px">
          Tip: before answering, look back to the centre — each answer starts from a straight head.</div>
      </div>
    </div>

    <div class="rm-stats">
      <div class="card"><span class="metric-label">ON TARGET · ALONE</span><b id="rm-s-base">—</b></div>
      <div class="card"><span class="metric-label">ON TARGET · WITH QUESTIONS</span><b id="rm-s-dual">—</b></div>
      <div class="card"><span class="metric-label">ANSWERS</span><b id="rm-s-ans">—</b></div>
      <div class="card"><span class="metric-label">AVG ANSWER TIME</span><b id="rm-s-rt">—</b></div>
    </div>

    <div class="summary-card" id="rm-summary">
      <div class="session-header"><div><div class="eyebrow">DUAL-TASK REPORT</div><h2 style="margin:4px 0 0">Session summary</h2></div>
        <span class="tag" id="rm-summary-tag">Saved</span></div>
      <div class="summary-grid" id="rm-summary-grid"></div>
      <div class="feedback" id="rm-summary-text"></div>
      <div class="muted" style="font-size:12px;margin-top:8px">Training feedback from a webcam estimate — not a clinical assessment.</div>
    </div>`;
  main.append(page);

  function activateDual() {
    document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === 'dual'));
    document.querySelectorAll('[data-page]').forEach(b => b.classList.toggle('active', b.dataset.page === 'dual'));
    if ($('eyebrow')) $('eyebrow').textContent = 'TRAINING WORKSPACE / DUAL-TASK';
    if ($('title')) $('title').textContent = 'Dual-task training';
    if ($('subtitle')) $('subtitle').textContent = 'Body and mind together — hold steady while you answer.';
  }
  navBtn.addEventListener('click', activateDual);

  // Third card on the "Choose your training model" screen (cognitive.js)
  const cards = document.querySelector('#mode-gate .mode-cards');
  if (cards) {
    cards.style.gridTemplateColumns = 'repeat(auto-fit, minmax(240px, 1fr))';
    const card = el('div', { className: 'mode-card' });
    card.innerHTML = `<div><div class="mode-icon" style="width:auto;padding:0 10px;white-space:nowrap">🧠💪</div><h3>Dual-Task Training</h3>
      <p class="muted">Hold a <b>physical posture</b> while answering <b>thinking questions</b> hands-free with head tilts —
      the way everyday life asks you to move and think at once.</p></div>`;
    const go = el('button', { className: 'primary', id: 'choose-dual', textContent: 'Enter Dual-Task Mode →' });
    go.onclick = () => {
      const v = $('cog-video');                              // free the browser camera used by cognitive.js
      v?.srcObject?.getTracks?.().forEach(t => t.stop());
      $('mode-gate').hidden = true;
      activateDual();
    };
    card.append(go);
    cards.append(card);
  }

  // ---- dual-task flow ----
  let dualPoll = null, dualRunning = false, camOn = false;
  let spoken = { phase: null, q: null, fb: null };

  function setButtons() {
    $('rm-start').disabled = !camOn || dualRunning;
    $('rm-stop').disabled = !dualRunning;
    $('rm-pain').disabled = !dualRunning;
    ['rm-posture', 'rm-answer', 'rm-count'].forEach(id => { $(id).disabled = dualRunning; });
  }

  $('rm-connect').onclick = async () => {
    $('rm-connect').disabled = true;
    try {
      await post('/api/camera/start');
      camOn = true;
      $('rm-video').src = '/video_feed?time=' + Date.now();
      $('rm-video').style.display = 'block';
      $('rm-video-ph').style.display = 'none';
      $('rm-connect').textContent = '✓ Camera connected';
      $('rm-motor').textContent = 'Camera connected. Press Start.';
    } catch (e) {
      $('rm-motor').textContent = 'Could not connect the camera: ' + e.message;
      $('rm-connect').disabled = false;
    }
    setButtons();
  };

  $('rm-start').onclick = async () => {
    $('rm-summary').classList.remove('visible');
    try {
      const r = await post('/api/dual/start', {
        posture: $('rm-posture').value, questions: Number($('rm-count').value),
        hold_ms: $('rm-answer').value === 'click' ? 3600000 : 1200, baseline_sec: 10, question_sec: 8,
      });
      dualRunning = true;
      spoken = { phase: null, q: null, fb: null };
      setButtons();
      render(r.state);
      clearInterval(dualPoll);
      dualPoll = setInterval(pollDual, 200);
    } catch (e) {
      $('rm-motor').textContent = 'Could not start: ' + e.message;
      talk('Could not start. ' + e.message, 'alert');
    }
  };

  async function pollDual() {
    try {
      const { state } = await api('/api/dual/state');
      if (!state) return;
      render(state);
      if (state.phase === 'done') stopDual('completed');
    } catch (_) {}
  }

  async function answer(choice) {
    if (!dualRunning) return;
    try { const r = await post('/api/dual/answer', { choice }); if (r.state) render(r.state); } catch (_) {}
  }
  $('rm-opt-left').onclick = () => answer('left');
  $('rm-opt-right').onclick = () => answer('right');
  document.addEventListener('keydown', e => {
    if (!page.classList.contains('active') || !dualRunning || bState) return;
    if (e.key === 'ArrowLeft') { e.preventDefault(); answer('left'); }
    if (e.key === 'ArrowRight') { e.preventDefault(); answer('right'); }
  });

  const PHASE_TEXT = { position: 'GET INTO POSITION', baseline: 'STEP 1 · HOLD ONLY', dual: 'STEP 2 · HOLD + ANSWER',
                       done: 'FINISHED', stopped: 'STOPPED' };

  function render(s) {
    // motor gauge
    const [z0, z1] = s.zone;
    $('rm-zone').style.left = `${(z0 / 180) * 100}%`;
    $('rm-zone').style.width = `${((Math.min(z1, 180) - z0) / 180) * 100}%`;
    $('rm-gauge-label').textContent = s.posture === 'curl_hold' ? `target ${Math.round(z0)}–${Math.round(z1)}°` : `open ≥ ${Math.round(z0)}`;
    if (s.angle != null) $('rm-needle').style.left = `calc(${Math.max(0, Math.min(100, (s.angle / 180) * 100))}% - 2px)`;
    const motorBad = !s.in_zone && s.phase !== 'position';
    $('rm-motor').className = 'rm-motor' + (motorBad ? ' bad' : '');
    $('rm-motor').textContent = s.phase === 'position'
      ? `${s.get_in_message}${s.angle != null ? ` (now ${Math.round(s.angle)}${s.posture === 'curl_hold' ? '°' : ''})` : ''}`
      : `${s.motor_message}${s.angle != null ? ` · ${Math.round(s.angle)}${s.posture === 'curl_hold' ? '°' : ''}` : ''}`;

    // phase + voice for phase changes
    $('rm-phase').textContent = PHASE_TEXT[s.phase] + (s.phase_left_sec != null ? ` · ${Math.ceil(s.phase_left_sec)}s` : '');
    if (spoken.phase !== s.phase) {
      spoken.phase = s.phase;
      if (s.phase === 'position') talk(s.get_in_message, 'info');
      if (s.phase === 'baseline') talk('Good. Now just hold this position. No questions yet.', 'info');
      if (s.phase === 'dual') talk($('rm-answer').value === 'click'
        ? 'Keep holding. Now answer each question by clicking.'
        : 'Keep holding. Now tilt your head towards your answer and hold it there.', 'info');
    }
    // keep correcting the posture while it is off target (repeats every few seconds)
    if (motorBad && s.out_of_zone_sec != null && s.out_of_zone_sec >= 1 && s.motor_message) talk(s.motor_message, 'alert');

    // question
    const L = $('rm-opt-left'), R = $('rm-opt-right');
    [L, R].forEach(b => { b.classList.remove('lean', 'correct', 'wrong'); b.querySelector('.fill').style.width = '0'; });
    if (s.phase === 'dual' && s.question) {
      const q = s.question;
      $('rm-question').textContent = q.text;
      L.querySelector('span').textContent = q.options[0];
      R.querySelector('span').textContent = q.options[1];
      L.disabled = R.disabled = q.answered;
      if (spoken.q !== q.number) {
        spoken.q = q.number;
        talk(`${q.text} Left: ${q.options[0]}. Right: ${q.options[1]}.`, 'info');
      }
      const h = s.head;
      if (h.direction && !q.answered) {
        const b = h.direction === 'left' ? L : R;
        b.classList.add('lean');
        b.querySelector('.fill').style.width = `${Math.round(h.progress * 100)}%`;
      }
      if (s.feedback) {
        const fb = s.feedback;
        [L, R][fb.answer].classList.add('correct');
        if (fb.chosen != null && !fb.correct) [L, R][fb.chosen].classList.add('wrong');
        $('rm-feedback').className = 'feedback' + (fb.correct ? '' : ' warn');
        $('rm-feedback').textContent = fb.timeout ? '⏱ Time is up — the next question is coming.'
          : fb.correct ? '✅ Correct! Look back to the centre.' : '❌ Not quite. Look back to the centre.';
        if (spoken.fb !== q.number) { spoken.fb = q.number; talk(fb.timeout ? 'Time is up.' : fb.correct ? 'Correct.' : 'Not quite.', 'info'); }
      } else {
        $('rm-feedback').className = 'feedback';
        $('rm-feedback').textContent = !s.head.visible && $('rm-answer').value === 'head'
          ? 'Keep your face in view to answer with head tilts.'
          : `Question ${q.number} of ${q.of} · ${q.time_left != null ? Math.ceil(q.time_left) + 's left' : ''}`;
      }
    } else if (s.phase === 'baseline') {
      $('rm-question').textContent = 'Just hold the position…';
      L.disabled = R.disabled = true;
    } else if (s.phase === 'position') {
      $('rm-question').textContent = 'Get into position — questions start after a short hold.';
      L.disabled = R.disabled = true;
    }

    // live stats
    const pct = v => (v == null ? '—' : `${Math.round(v)}%`);
    $('rm-s-base').textContent = pct(s.baseline.in_zone_pct);
    $('rm-s-dual').textContent = pct(s.dual.in_zone_pct);
    $('rm-s-ans').textContent = s.cognitive.answered || s.cognitive.timeouts
      ? `${s.cognitive.correct} / ${s.cognitive.answered + s.cognitive.timeouts}` : '—';
    $('rm-s-rt').textContent = s.cognitive.mean_rt_sec == null ? '—' : `${s.cognitive.mean_rt_sec}s`;
  }

  async function stopDual(reason) {
    if (!dualRunning) return;
    dualRunning = false;
    clearInterval(dualPoll);
    dualPoll = null;
    setButtons();
    let res = {};
    try { res = await post('/api/dual/stop', { reason }); } catch (e) { console.error(e); }
    const s = res.summary;
    $('rm-phase').textContent = reason === 'pain' ? 'STOPPED — PAIN' : PHASE_TEXT[reason === 'completed' ? 'done' : 'stopped'];
    $('rm-opt-left').disabled = $('rm-opt-right').disabled = true;
    if (s) showSummary(s, reason);
    if (reason === 'pain') {
      talk('Stopped because of pain.', 'alert');
      openBreathing({ trigger: 'pain' });
    }
  }
  $('rm-stop').onclick = () => stopDual('manual');
  $('rm-pain').onclick = () => stopDual('pain');

  function showSummary(s, reason) {
    const d = s.dual_task, c = d.cognitive, pct = v => (v == null ? '—' : `${v}%`);
    $('rm-summary-tag').textContent = { completed: '✓ Completed', manual: '■ Stopped & saved', pain: '⚠ Pain stop' }[reason] || 'Saved';
    const items = [
      ['ON TARGET · ALONE', pct(d.baseline.in_zone_pct)],
      ['ON TARGET · WITH QUESTIONS', pct(d.dual.in_zone_pct)],
      ['DUAL-TASK COST', d.dual_task_cost_pct == null ? '—' : `${d.dual_task_cost_pct}%`],
      ['STEADINESS (SD) ALONE → WITH Qs', `${d.baseline.angle_sd ?? '—'} → ${d.dual.angle_sd ?? '—'}`],
      ['ANSWERS CORRECT', `${c.correct} / ${c.questions}`],
      ['AVG ANSWER TIME', c.mean_rt_sec == null ? '—' : `${c.mean_rt_sec}s`],
      ['ANSWERED BY HEAD', `${c.via_head}`],
      ['SLIPS OFF TARGET', `${d.baseline.drops} alone · ${d.dual.drops} with Qs`],
    ];
    $('rm-summary-grid').innerHTML = items.map(([k, v]) =>
      `<div class="summary-item"><span class="metric-label">${k}</span><b>${v}</b></div>`).join('');
    const cost = d.dual_task_cost_pct;
    let text = d.baseline.in_zone_pct != null && d.dual.in_zone_pct != null
      ? `On its own you stayed on target ${d.baseline.in_zone_pct}% of the time; while answering questions ${d.dual.in_zone_pct}%. `
      : 'Not enough data to compare holding alone and with questions. ';
    if (cost != null) text += cost > 20 ? 'Thinking made holding noticeably harder — that is common, and exactly what this training works on.'
      : cost > 10 ? 'Thinking made holding a little harder.' : 'Thinking hardly affected your control — great work.';
    $('rm-summary-text').textContent = text;
    $('rm-summary').classList.add('visible');
    if (reason !== 'pain') talk('Session saved. ' + text, 'info');
    try {                                                   // also list it under "My progress" on this device
      const list = JSON.parse(localStorage.getItem('gem_sessions') || '[]');
      list.push({ date: new Date().toISOString(), exercise: 'Dual-task training', side: s.side, reps: c.correct,
                  target: c.questions, seconds: Math.round(s.duration_sec || 0), activeSeconds: Math.round(s.duration_sec || 0),
                  endedBy: reason });
      localStorage.setItem('gem_sessions', JSON.stringify(list));
    } catch (_) {}
  }
})();
