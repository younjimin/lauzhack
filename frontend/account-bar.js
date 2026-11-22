/*
 * account-bar.js — ability+ account bar for the patient screen.
 * main.py adds this file to gem.html automatically, so gem.html itself does not need to change.
 *
 * Adds: the patient's name, a "My physiotherapist" panel (current prescription, notes on sessions,
 * messages in both directions) and Log out.
 */
(() => {
  const css = `
  @import url("https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&display=swap");
  #ab-bar, #ab-panel { --ink: #19332f; --ink-2: #5f6f6a; --rule: #e1eae6; --paper: #f4f7f6; --brand: #167b69; --focus: #F2A93B;
    font-family: "Atkinson Hyperlegible", system-ui, sans-serif; color: var(--ink); }
  #ab-bar { position: fixed; bottom: 18px; right: 18px; z-index: 50; display: flex; align-items: stretch;
    background: #fff; border: 1.5px solid var(--rule); border-radius: 8px; overflow: hidden; font-size: 15px; }
  #ab-bar > * { border: 0; background: none; padding: 9px 14px; font: inherit; color: inherit; }
  #ab-bar > * + * { border-left: 1.5px solid var(--rule); }
  #ab-bar .name { font-weight: 700; display: flex; align-items: center; gap: 3px; }
  #ab-bar .name .plus { display: inline-grid; place-items: center; width: 16px; height: 16px; border-radius: 4px; background: var(--brand);
    color: #fff; font-size: 13px; line-height: 1; margin-right: 6px; }
  #ab-bar button { cursor: pointer; }
  #ab-bar button.physio { background: none; color: inherit; font-weight: 400; }
  #ab-bar button:hover { text-decoration: underline; }
  #ab-bar .count { background: var(--brand); color: #fff; border-radius: 9px; padding: 0 6px; margin-left: 6px; font-size: 13px; }
  #ab-bar button:focus-visible, #ab-panel button:focus-visible, #ab-panel textarea:focus-visible { outline: 3px solid var(--focus); outline-offset: -3px; }
  #ab-panel { position: fixed; top: 0; right: 0; bottom: 0; width: min(430px, 100vw); background: #fff; z-index: 60;
    border-left: 1.5px solid var(--rule); display: flex; flex-direction: column; font-size: 16px; line-height: 1.5;
    transform: translateX(105%); visibility: hidden; transition: transform .22s ease, visibility 0s linear .22s; }
  #ab-panel.open { transform: none; visibility: visible; transition: transform .22s ease; }
  @media (prefers-reduced-motion: reduce) { #ab-panel, #ab-panel.open { transition: none; } }
  body.reduce #ab-panel { transition: none; }
  #ab-panel header { padding: 18px 22px 14px; border-bottom: 1px solid var(--rule); display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
  #ab-panel header h2 { font-size: 22px; letter-spacing: -0.01em; margin: 0; line-height: 1.2; }
  #ab-panel header p { margin: 2px 0 0; color: var(--ink-2); font-size: 14px; }
  #ab-panel .close { border: 1.5px solid var(--rule); background: #fff; border-radius: 6px; padding: 5px 10px; cursor: pointer; font: inherit; font-size: 14px; }
  #ab-panel .body { flex: 1; overflow: auto; padding: 4px 22px 18px; }
  #ab-panel h3 { font-size: 16px; margin: 20px 0 8px; }
  #ab-panel .rx { padding: 10px 0; border-bottom: 1px solid var(--rule); }
  #ab-panel .rx:last-of-type { border-bottom: 0; }
  #ab-panel .rx b { display: block; }
  #ab-panel .muted { color: var(--ink-2); font-size: 14px; }
  #ab-panel blockquote { margin: 0 0 10px; padding: 8px 12px; border-left: 4px solid var(--brand); background: var(--paper); border-radius: 0 6px 6px 0; }
  #ab-panel blockquote .muted { display: block; margin-top: 2px; }
  #ab-panel .msgs { display: flex; flex-direction: column; gap: 8px; }
  #ab-panel .msg { max-width: 85%; padding: 9px 12px; border-radius: 10px; font-size: 15px; white-space: pre-wrap; overflow-wrap: anywhere; }
  #ab-panel .msg.them { background: var(--paper); align-self: flex-start; border-bottom-left-radius: 3px; }
  #ab-panel .msg.mine { background: var(--brand); color: #fff; align-self: flex-end; border-bottom-right-radius: 3px; }
  #ab-panel .msg time { display: block; font-size: 12px; opacity: .75; margin-top: 2px; }
  #ab-panel footer { border-top: 1px solid var(--rule); padding: 12px 22px; display: flex; gap: 8px; }
  #ab-panel textarea { flex: 1; resize: none; height: 46px; border: 1.5px solid var(--rule); border-radius: 6px; padding: 10px; font: inherit; font-size: 15px; }
  #ab-panel textarea:focus { border-color: var(--brand); }
  #ab-panel footer button { border: 0; background: var(--brand); color: #fff; border-radius: 6px; padding: 0 18px; font: inherit; font-weight: 700; cursor: pointer; }
  #ab-panel footer button:disabled { opacity: .5; cursor: not-allowed; }
  #ab-bar.in-sidebar { position: static; flex-direction: column; margin-top: 18px; }
  #ab-bar.in-sidebar > * { text-align: left; }
  #ab-bar.in-sidebar > * + * { border-left: 0; border-top: 1.5px solid var(--rule); }
  @media (max-width: 800px) { #ab-bar.in-sidebar { flex-direction: row; flex-wrap: wrap; } #ab-bar.in-sidebar > * + * { border-top: 0; border-left: 1.5px solid var(--rule); } }
  @media (max-width: 600px) { #ab-bar:not(.in-sidebar) { left: 10px; right: 10px; bottom: 10px; } #ab-bar .name { flex: 1; } }
  `;
  document.head.append(Object.assign(document.createElement('style'), { textContent: css }));

  const el = (tag, props = {}, kids = []) => {
    const n = Object.assign(document.createElement(tag), props);
    [].concat(kids).forEach(k => k != null && n.append(k));
    return n;
  };
  const fmt = iso => iso ? new Date(iso).toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
  const api = async (url, opts = {}) => {
    const r = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...opts });
    if (r.status === 401) { window.location.href = '/login'; throw new Error('Logged out'); }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || `Server error (${r.status})`);
    return d;
  };

  // ---- bar ----
  const physioBtn = el('button', { type: 'button', className: 'physio', textContent: 'My physiotherapist' });
  const badge = el('span', { className: 'count', hidden: true });
  physioBtn.append(badge);
  const nameText = el('span', { textContent: '' });
  const nameBox = el('span', { className: 'name' }, [el('span', { className: 'plus', ariaHidden: 'true', textContent: '+' }), nameText]);
  const outBtn = el('button', { type: 'button', textContent: 'Log out' });
  const bar = el('div', { id: 'ab-bar', role: 'region', ariaLabel: 'Your ability+ account' }, [nameBox, physioBtn, outBtn]);
  const sidebar = document.querySelector('.sidebar');       // patient app: sit in the sidebar, never over the content
  if (sidebar) { bar.classList.add('in-sidebar'); sidebar.append(bar); } else { document.body.append(bar); }

  // ---- panel ----
  const content = el('div', { className: 'body' });
  const input = el('textarea', { placeholder: 'Write to your physiotherapist', maxLength: 2000, ariaLabel: 'Message to your physiotherapist' });
  const send = el('button', { type: 'button', textContent: 'Send' });
  const close = el('button', { type: 'button', className: 'close', textContent: 'Close' });
  const title = el('h2', { textContent: 'My physiotherapist' });
  const subtitle = el('p', { textContent: '' });
  const panel = el('aside', { id: 'ab-panel', ariaLabel: 'My physiotherapist' }, [
    el('header', {}, [el('div', {}, [title, subtitle]), close]), content, el('footer', {}, [input, send]),
  ]);
  document.body.append(panel);

  let doctor = null;
  let open = false;

  function prescriptionText(key, rx) {
    if (rx.exercise === 'elbow_curl') return ['Arm curl', `${rx.reps} repetitions. Bend from ${rx.rest_angle}° to ${rx.target_angle}°, never past ${rx.safe_limit}°.`];
    if (rx.exercise === 'finger_opposition') return ['Finger opposition', `${rx.reps} touches, thumb to each finger in turn.`];
    return [key, `${rx.reps} repetitions.`];
  }

  async function render() {
    const ov = await api('/api/patient/overview');
    nameText.textContent = ov.user.name;
    doctor = ov.doctors[0] || null;
    content.innerHTML = '';
    input.disabled = send.disabled = !doctor;

    if (!doctor) {
      content.append(el('div', { className: 'box', textContent:
        `No physiotherapist is connected yet. Ask your physiotherapist to add you with your email (${ov.user.email}).` }));
      return;
    }
    title.textContent = doctor.name;
    subtitle.textContent = ov.stats.total
      ? `Sees all ${ov.stats.total} of your sessions, ${ov.stats.week} from this week.`
      : 'Sees each session as soon as you finish it.';

    content.append(el('h3', { textContent: 'Your exercises' }));
    for (const [key, rx] of Object.entries(ov.prescriptions)) {
      const [name, detail] = prescriptionText(key, rx);
      content.append(el('div', { className: 'rx' }, [
        el('b', { textContent: name }), detail,
        el('div', { className: 'muted', textContent: rx.updated_at ? `Updated by your physiotherapist on ${fmt(rx.updated_at)}` : 'Standard plan' }),
      ]));
    }

    const notes = ov.sessions.filter(s => s.doctor_note);
    if (notes.length) {
      content.append(el('h3', { textContent: 'Notes on your sessions' }));
      notes.slice(0, 5).forEach(s => content.append(el('blockquote', {}, [
        s.doctor_note,
        el('span', { className: 'muted', textContent: `About your session on ${fmt(s.created_at)}` }),
      ])));
    }

    content.append(el('h3', { textContent: 'Messages' }));
    const box = el('div', { className: 'msgs' });
    content.append(box);
    const { messages } = await api(`/api/messages/${doctor.id}`);
    if (!messages.length) box.append(el('p', { className: 'muted', textContent: 'No messages yet. Ask a question or tell them how the exercises feel.' }));
    messages.forEach(m => box.append(el('div', { className: 'msg ' + (m.mine ? 'mine' : 'them') }, [
      m.body, el('time', { textContent: fmt(m.created_at) }),
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

  api('/api/auth/me').then(d => { if (d.user) nameText.textContent = d.user.name; });
  refreshBadge();
  setInterval(() => (open ? render() : refreshBadge()).catch(() => {}), 15000);
})();
