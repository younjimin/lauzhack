/*
 * gem-auth.js — account bar for the patient screen.
 * main.py adds this file to gem.html automatically, so gem.html itself does not need to change.
 *
 * Adds: the patient's name, a "My physiotherapist" panel (current prescription, notes on sessions,
 * messages in both directions) and Log out.
 */
(() => {
  const css = `
  #gem-acct { position: fixed; bottom: 18px; right: 18px; z-index: 50; display: flex; gap: 8px; align-items: center;
    font: 13px/1.4 Inter, system-ui, Arial, sans-serif; }
  #gem-acct button { border: 1px solid #e1eae6; background: #fff; color: #19332f; border-radius: 30px; padding: 7px 12px;
    font: inherit; font-weight: 650; cursor: pointer; box-shadow: 0 1px 4px rgba(0,0,0,.05); }
  #gem-acct button:focus-visible, #gem-panel button:focus-visible, #gem-panel textarea:focus-visible { outline: 3px solid #f4a261; outline-offset: 2px; }
  #gem-acct .badge { background: #d9534f; color: #fff; border-radius: 10px; padding: 0 6px; margin-left: 4px; font-size: 11px; }
  #gem-panel { position: fixed; top: 0; right: 0; bottom: 0; width: min(420px, 100vw); background: #fff; z-index: 60;
    border-left: 1px solid #e1eae6; box-shadow: -8px 0 30px rgba(0,0,0,.08); display: flex; flex-direction: column;
    font: 14px/1.5 Inter, system-ui, Arial, sans-serif; color: #19332f; transform: translateX(105%); transition: transform .2s; }
  #gem-panel.open { transform: none; }
  body.reduce #gem-panel { transition: none; }
  #gem-panel header { padding: 18px 20px; border-bottom: 1px solid #e1eae6; display: flex; justify-content: space-between; align-items: center; }
  #gem-panel header b { font-size: 16px; }
  #gem-panel .x { border: 0; background: #edf3f0; border-radius: 8px; padding: 6px 10px; cursor: pointer; font: inherit; }
  #gem-panel .body { flex: 1; overflow: auto; padding: 16px 20px; }
  #gem-panel h4 { font-size: 11px; letter-spacing: 1px; color: #6b7b77; margin: 18px 0 8px; }
  #gem-panel h4:first-child { margin-top: 0; }
  #gem-panel .box { background: #f4f7f6; border-radius: 10px; padding: 10px 12px; margin-bottom: 8px; font-size: 13px; }
  #gem-panel .muted { color: #6b7b77; font-size: 12px; }
  #gem-panel .note { border-left: 3px solid #167b69; }
  #gem-panel .msgs { display: flex; flex-direction: column; gap: 6px; }
  #gem-panel .msg { max-width: 85%; padding: 8px 11px; border-radius: 12px; font-size: 13px; white-space: pre-wrap; word-wrap: break-word; }
  #gem-panel .msg.them { background: #f0f5f2; align-self: flex-start; }
  #gem-panel .msg.mine { background: #167b69; color: #fff; align-self: flex-end; }
  #gem-panel .msg small { display: block; opacity: .7; font-size: 10px; margin-top: 2px; }
  #gem-panel footer { border-top: 1px solid #e1eae6; padding: 12px 20px; display: flex; gap: 8px; }
  #gem-panel textarea { flex: 1; resize: none; height: 44px; border: 1px solid #e1eae6; border-radius: 9px; padding: 10px; font: inherit; }
  #gem-panel footer button { border: 0; background: #167b69; color: #fff; border-radius: 9px; padding: 0 16px; font: inherit; font-weight: 700; cursor: pointer; }
  @media (max-width: 600px) { #gem-acct { left: 10px; right: 10px; bottom: 10px; flex-wrap: wrap; justify-content: flex-end; } }
  `;
  document.head.append(Object.assign(document.createElement('style'), { textContent: css }));

  const el = (tag, props = {}, kids = []) => {
    const n = Object.assign(document.createElement(tag), props);
    [].concat(kids).forEach(k => k != null && n.append(k));
    return n;
  };
  const fmt = iso => iso ? new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
  const api = async (url, opts = {}) => {
    const r = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...opts });
    if (r.status === 401) { window.location.href = '/login'; throw new Error('Logged out'); }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || `Server error (${r.status})`);
    return d;
  };

  // ---- bar ----
  const physioBtn = el('button', { type: 'button', textContent: '💬 My physiotherapist' });
  const badge = el('span', { className: 'badge', hidden: true });
  physioBtn.append(badge);
  const nameBtn = el('button', { type: 'button', disabled: true, textContent: '👤 …' });
  nameBtn.style.cursor = 'default';
  const outBtn = el('button', { type: 'button', textContent: 'Log out' });
  document.body.append(el('div', { id: 'gem-acct' }, [nameBtn, physioBtn, outBtn]));

  // ---- panel ----
  const content = el('div', { className: 'body' });
  const input = el('textarea', { placeholder: 'Write to your physiotherapist…', maxLength: 2000 });
  const send = el('button', { type: 'button', textContent: 'Send' });
  const close = el('button', { type: 'button', className: 'x', textContent: '✕', ariaLabel: 'Close' });
  const title = el('b', { textContent: 'My physiotherapist' });
  const panel = el('aside', { id: 'gem-panel', ariaLabel: 'My physiotherapist' }, [
    el('header', {}, [title, close]), content, el('footer', {}, [input, send]),
  ]);
  document.body.append(panel);

  let doctor = null;
  let open = false;

  function prescriptionText(key, rx) {
    if (rx.exercise === 'elbow_curl') return `Arm curl · ${rx.reps} reps · ${rx.rest_angle}° → ${rx.target_angle}° · never past ${rx.safe_limit}°`;
    if (rx.exercise === 'finger_opposition') return `Finger opposition · ${rx.reps} touches`;
    return `${key} · ${rx.reps} reps`;
  }

  async function render() {
    const ov = await api('/api/patient/overview');
    nameBtn.textContent = '👤 ' + ov.user.name;
    doctor = ov.doctors[0] || null;
    content.innerHTML = '';
    input.disabled = send.disabled = !doctor;

    if (!doctor) {
      content.append(el('div', { className: 'box', textContent:
        `No physiotherapist is connected yet. Ask your physiotherapist to add you with your email (${ov.user.email}).` }));
      return;
    }
    title.textContent = doctor.name;

    content.append(el('h4', { textContent: 'YOUR PRESCRIPTION' }));
    for (const [key, rx] of Object.entries(ov.prescriptions)) {
      content.append(el('div', { className: 'box' }, [
        prescriptionText(key, rx),
        el('div', { className: 'muted', textContent: rx.updated_at ? `Set by your physiotherapist · ${fmt(rx.updated_at)}` : 'Standard plan' }),
      ]));
    }

    const notes = ov.sessions.filter(s => s.doctor_note);
    if (notes.length) {
      content.append(el('h4', { textContent: 'NOTES ON YOUR SESSIONS' }));
      notes.slice(0, 5).forEach(s => content.append(el('div', { className: 'box note' }, [
        s.doctor_note,
        el('div', { className: 'muted', textContent: `${s.exercise_key || s.exercise} · ${s.reps} reps · ${fmt(s.created_at)}` }),
      ])));
    }

    content.append(el('h4', { textContent: `SAVED SESSIONS (${ov.stats.total})` }));
    content.append(el('div', { className: 'muted', textContent: ov.stats.total
      ? `${ov.stats.week} this week · ${ov.stats.active_days} active days · your physiotherapist can see every session.`
      : 'Finish an exercise and it is shared with your physiotherapist automatically.' }));

    content.append(el('h4', { textContent: 'MESSAGES' }));
    const box = el('div', { className: 'msgs' });
    content.append(box);
    const { messages } = await api(`/api/messages/${doctor.id}`);
    if (!messages.length) box.append(el('div', { className: 'muted', textContent: 'No messages yet.' }));
    messages.forEach(m => box.append(el('div', { className: 'msg ' + (m.mine ? 'mine' : 'them') }, [
      m.body, el('small', { textContent: fmt(m.created_at) }),
    ])));
    content.scrollTop = content.scrollHeight;
    refreshBadge();
  }

  async function refreshBadge() {
    try {
      const u = await api('/api/messages/unread');
      badge.hidden = !u.total;
      badge.textContent = u.total;
    } catch (_) {}
  }

  physioBtn.onclick = () => { open = true; panel.classList.add('open'); render().catch(e => console.error(e)); };
  close.onclick = () => { open = false; panel.classList.remove('open'); };
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && open) close.onclick(); });

  async function sendMessage() {
    const text = input.value.trim();
    if (!text || !doctor) return;
    send.disabled = true;
    try {
      await api(`/api/messages/${doctor.id}`, { method: 'POST', body: JSON.stringify({ body: text }) });
      input.value = '';
      await render();
    } catch (e) { alert(e.message); } finally { send.disabled = false; }
  }
  send.onclick = sendMessage;
  input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } });

  outBtn.onclick = async () => {
    try { await fetch('/api/camera/stop', { method: 'POST' }); } catch (_) {}
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/login';
  };

  api('/api/auth/me').then(d => { if (d.user) nameBtn.textContent = '👤 ' + d.user.name; });
  refreshBadge();
  setInterval(() => (open ? render() : refreshBadge()).catch(() => {}), 15000);
})();