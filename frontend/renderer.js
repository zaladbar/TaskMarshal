// frontend/renderer.js  — FULL REWRITE
// Front-end logic for Productivity Boss

document.addEventListener('DOMContentLoaded', async () => {
  /* ---------- helper selectors (declare first to avoid TDZ) ---------- */
  const $ = sel => document.querySelector(sel);
  const _ = sel => $(sel);

  /* ---------- elements ---------- */
  const consentModal       = _('#consent-modal');
  const consentBtn         = _('#consent-accept');
  const settingsModal      = _('#settings-modal');
  const saveKeyBtn         = _('#save-key-btn');
  const apiKeyInput        = _('#api-key-input');
  const setupSection       = _('#setup-section');
  const mainSection        = _('#main-section');
  const reportSection      = _('#report-section');
  const personaSelect      = _('#persona-select');
  const goalsInput         = _('#goals-input');
  const startBtn           = _('#start-btn');
  const endBtn             = _('#end-btn');
  const closeBtn           = _('#close-btn');
  const personaNameElem    = _('#persona-name');
  const goalDisplay        = _('#goal-display');
  const workTimeElem       = _('#work-time');
  const distractTimeElem   = _('#distract-time');
  const idleTimeElem       = _('#idle-time');
  const personaMsgElem     = _('#persona-message');
  const summaryStats       = _('#summary-stats');
  const reportMsg          = _('#report-message');

  /* ---------------- base URL for the Flask backend ---------------- */
  const API_BASE = 'http://127.0.0.1:5000';

  /* ---------- secure key on load ---------- */
  const storedKey = await window.electronAPI.readOpenAIKey();
  if (storedKey) apiKeyInput.value = storedKey;

  saveKeyBtn.addEventListener('click', async () => {
    const ok = await window.electronAPI.saveOpenAIKey(apiKeyInput.value.trim());
    if (ok) settingsModal.classList.add('hidden');
  });

  /* open settings with Ctrl+, */
  document.addEventListener('keydown', e => {
    if (e.ctrlKey && e.key === ',') settingsModal.classList.toggle('hidden');
  });

  /* ---------- persona list ---------- */
  loadPersonas();

  /* ---- consent ---- */
  consentBtn.addEventListener('click', () =>
    fetch(`${API_BASE}/api/consent`, { method: 'POST' })
      .then(() => consentModal.classList.add('hidden'))
  );

  /* ---- start day ---- */
  startBtn.addEventListener('click', () => {
    const payload = { goals: goalsInput.value.trim(), persona: personaSelect.value };
    fetch(`${API_BASE}/api/start_day`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(r => r.json())
      .then(() => {
        setupSection.classList.add('hidden');
        mainSection.classList.remove('hidden');
        personaNameElem.textContent = personaSelect.selectedOptions[0].text;
        goalDisplay.textContent = 'Goal: ' + (payload.goals || '(none)');
        pollStatus();
        statusInterval = setInterval(pollStatus, 60000);
      });
  });

  /* ---- end day ---- */
  endBtn.addEventListener('click', () => {
    if (statusInterval) clearInterval(statusInterval);
    fetch(`${API_BASE}/api/end_day`)
      .then(r => r.json())
      .then(res => {
        summaryStats.innerHTML = `
          <p>Work: ${format(res.work_time)}</p>
          <p>Distractions: ${format(res.distraction_time)}</p>
          <p>Idle: ${format(res.idle_time)}</p>`;
        reportMsg.textContent = res.persona_report;
        mainSection.classList.add('hidden');
        reportSection.classList.remove('hidden');
      });
  });

  closeBtn.addEventListener('click', () => window.close());

  /* ---------- helpers ---------- */
  let statusInterval = null;
  function format(sec) {
    const m = Math.floor(sec / 60);
    const h = Math.floor(m / 60);
    return h ? `${h}h ${m % 60}m` : `${m}m`;
  }
  function pollStatus() {
    fetch(`${API_BASE}/api/status`)
      .then(r => r.json())
      .then(s => {
        workTimeElem.textContent      = 'Work: '         + format(s.work_time);
        distractTimeElem.textContent  = 'Distractions: ' + format(s.distraction_time);
        idleTimeElem.textContent      = 'Idle: '         + format(s.idle_time);
        if (s.message) personaMsgElem.textContent = s.message;
      });
  }
  function loadPersonas() {
    fetch(`${API_BASE}/api/personas`)
      .then(r => r.json())
      .then(list => {
        personaSelect.innerHTML = '';
        list.forEach(p => {
          const o = document.createElement('option');
          o.value = p.id;
          o.textContent = p.name;
          personaSelect.appendChild(o);
        });
        fetch(`${API_BASE}/api/prefs`)
          .then(r => r.json())
          .then(prefs => {
            if (!prefs.consent_given) consentModal.classList.remove('hidden');
            if (prefs.last_persona) personaSelect.value = prefs.last_persona;
          });
      });
  }
});
