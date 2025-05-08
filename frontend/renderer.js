// Frontend Renderer Script
document.addEventListener('DOMContentLoaded', () => {
  // Get UI elements
  const consentModal = document.getElementById('consent-modal');
  const consentBtn = document.getElementById('consent-accept');
  const setupSection = document.getElementById('setup-section');
  const mainSection = document.getElementById('main-section');
  const reportSection = document.getElementById('report-section');
  const personaSelect = document.getElementById('persona-select');
  const goalsInput = document.getElementById('goals-input');
  const startBtn = document.getElementById('start-btn');
  const endBtn = document.getElementById('end-btn');
  const closeBtn = document.getElementById('close-btn');
  const personaNameElem = document.getElementById('persona-name');
  const goalDisplay = document.getElementById('goal-display');
  const workTimeElem = document.getElementById('work-time');
  const distractTimeElem = document.getElementById('distract-time');
  const idleTimeElem = document.getElementById('idle-time');
  const personaMsgElem = document.getElementById('persona-message');
  const summaryStatsElem = document.getElementById('summary-stats');
  const reportMsgElem = document.getElementById('report-message');

  let currentGoal = "";
  let statusInterval = null;
  let personasData = {};

  // Helper function to format seconds into "Xh Ym" string
  function formatTime(seconds) {
    seconds = Math.floor(seconds);
    if (seconds <= 0) return '0m';
    const m = Math.floor(seconds / 60);
    const h = Math.floor(m / 60);
    const remM = m % 60;
    if (h > 0) {
      return h + 'h ' + (remM) + 'm';
    } else {
      return (remM > 0 ? remM : '<1') + 'm';
    }
  }

  // Function to fetch persona list from backend
  function loadPersonas() {
    fetch('http://localhost:5000/api/personas')
      .then(response => {
        if (!response.ok) {
          throw new Error('Failed to load personas');
        }
        return response.json();
      })
      .then(data => {
        personasData = {};
        personaSelect.innerHTML = '';
        // Populate select options
        data.forEach(persona => {
          personasData[persona.id] = persona;
          const opt = document.createElement('option');
          opt.value = persona.id;
          opt.textContent = persona.name;
          personaSelect.appendChild(opt);
        });
        // After personas, load preferences
        loadPreferences();
      })
      .catch(err => {
        console.error('Error fetching personas:', err);
        // Retry once after a short delay
        setTimeout(() => {
          fetch('http://localhost:5000/api/personas')
            .then(resp => resp.ok ? resp.json() : Promise.reject())
            .then(data => {
              personasData = {};
              personaSelect.innerHTML = '';
              data.forEach(persona => {
                personasData[persona.id] = persona;
                const opt = document.createElement('option');
                opt.value = persona.id;
                opt.textContent = persona.name;
                personaSelect.appendChild(opt);
              });
              loadPreferences();
            })
            .catch(err2 => {
              console.error('Failed to load personas on retry:', err2);
              alert('Error: Could not connect to backend. Please ensure the application is running properly.');
            });
        }, 1000);
      });
  }

  // Function to load user preferences (consent status, last persona)
  function loadPreferences() {
    fetch('http://localhost:5000/api/prefs')
      .then(response => response.ok ? response.json() : Promise.reject())
      .then(prefs => {
        if (!prefs.consent_given) {
          // Show consent modal overlay
          consentModal.classList.remove('hidden');
        }
        if (prefs.last_persona) {
          // Set default selected persona if exists
          personaSelect.value = prefs.last_persona;
        }
      })
      .catch(err => {
        console.warn('Could not load preferences:', err);
        // If prefs can't load, proceed anyway (consent modal might not show, assume consent)
      });
  }

  // Accept consent
  consentBtn.addEventListener('click', () => {
    fetch('http://localhost:5000/api/consent', { method: 'POST' })
      .then(response => {
        if (response.ok) {
          consentModal.classList.add('hidden');
        } else {
          throw new Error('Consent not recorded');
        }
      })
      .catch(err => {
        console.error('Consent API error:', err);
        alert('Error: Unable to record consent. Please restart the app.');
      });
  });

  // Start Day button handler
  startBtn.addEventListener('click', () => {
    const goalsText = goalsInput.value.trim();
    const personaId = personaSelect.value;
    if (!personaId) {
      alert('Please select a persona.');
      return;
    }
    currentGoal = goalsText;
    const payload = { goals: goalsText, persona: personaId };
    fetch('http://localhost:5000/api/start_day', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(response => {
        if (!response.ok) {
          return response.text().then(text => { throw new Error(text || 'Failed to start day'); });
        }
        return response.json();
      })
      .then(data => {
        // Transition to main tracking view
        setupSection.classList.add('hidden');
        mainSection.classList.remove('hidden');
        // Display chosen persona name and icon
        const personaInfo = personasData[personaId];
        personaNameElem.textContent = 'Persona: ' + (personaInfo.icon ? personaInfo.icon + ' ' : '') + personaInfo.name;
        // Display the goal
        goalDisplay.textContent = 'Goal: ' + (currentGoal || '(none)');
        // Reset stats display
        workTimeElem.textContent = 'Work: 0m';
        distractTimeElem.textContent = 'Distractions: 0m';
        idleTimeElem.textContent = 'Idle: 0m';
        // Optionally update initial persona message (data may contain a greeting)
        if (data.initial_message) {
          personaMsgElem.textContent = data.initial_message;
        }
        // Start polling for status updates
        statusInterval = setInterval(updateStatus, 60000);
        // Also do an immediate status update call so stats start right away
        updateStatus();
      })
      .catch(err => {
        console.error('Start day error:', err);
        alert('Error starting day: ' + err.message);
      });
  });

  // Function to update status from backend
  function updateStatus() {
    fetch('http://localhost:5000/api/status')
      .then(response => response.ok ? response.json() : Promise.reject())
      .then(status => {
        // Update time stats
        workTimeElem.textContent = 'Work: ' + formatTime(status.work_time);
        distractTimeElem.textContent = 'Distractions: ' + formatTime(status.distraction_time);
        idleTimeElem.textContent = 'Idle: ' + formatTime(status.idle_time);
        // If there's a new persona message/nudge, display it
        if (status.message && status.message !== '') {
          personaMsgElem.textContent = status.message;
          // Show desktop notification as well
          if ("Notification" in window) {
            if (Notification.permission === 'default') {
              Notification.requestPermission();
            }
            if (Notification.permission === 'granted') {
              const notification = new Notification(personaNameElem.textContent || 'Productivity Boss', {
                body: status.message
              });
            }
          }
        }
      })
      .catch(err => {
        console.error('Status update error:', err);
        // If status fails (e.g., backend down), stop further polling
        if (statusInterval) {
          clearInterval(statusInterval);
          statusInterval = null;
        }
        alert('Lost connection to backend. Please restart the app.');
      });
  }

  // End Day button handler
  endBtn.addEventListener('click', () => {
    if (statusInterval) {
      clearInterval(statusInterval);
      statusInterval = null;
    }
    fetch('http://localhost:5000/api/end_day')
      .then(response => response.ok ? response.json() : Promise.reject())
      .then(result => {
        // Populate end-of-day report
        summaryStatsElem.innerHTML = `
          <p>Goal: ${currentGoal || '(none)'}</p>
          <p>Work time: ${formatTime(result.work_time)}</p>
          <p>Distraction time: ${formatTime(result.distraction_time)}</p>
          <p>Idle time: ${formatTime(result.idle_time)}</p>
        `;
        reportMsgElem.textContent = result.persona_report || '';
        // Switch to report view
        mainSection.classList.add('hidden');
        reportSection.classList.remove('hidden');
      })
      .catch(err => {
        console.error('End day error:', err);
        alert('Error ending day: ' + err);
      });
  });

  // Close/Finish button handler
  closeBtn.addEventListener('click', () => {
    window.close();
  });

  // Initial load: get personas and prefs
  loadPersonas();
});
