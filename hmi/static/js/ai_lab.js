/**
 * ai_lab.js — AI Lab page
 *
 * Polls three endpoints:
 *   GET /api/ai/status     → model version, threshold, training state
 *   GET /api/ai/experiment → SCADA vs AI comparison
 *   GET /api/ai/scores     → full score history for current/last run
 *
 * Polls every 1.5 s while training, 3 s otherwise.
 */
'use strict';

const C = {
  purple:'#bc8cff', amber:'#d29922', red:'#f85149',
  green:'#3fb950', blue:'#58a6ff', t1:'#8b949e', t2:'#484f58',
  grid:'rgba(255,255,255,0.06)',
};

Chart.defaults.color       = C.t1;
Chart.defaults.borderColor = C.grid;
Chart.defaults.animation   = false;
Chart.defaults.font.family = "'SF Pro Display','Segoe UI',system-ui,sans-serif";
Chart.defaults.font.size   = 10;
Chart.defaults.plugins.legend.display = false;

// ── State ─────────────────────────────────────────────────────────────────────
let scoreChart   = null;
let pollTimer    = null;
let pollInterval = 3000;
let trainingWasRunning = false;

// ── Score chart ───────────────────────────────────────────────────────────────
function buildScoreChart() {
  const ctx = document.getElementById('score-chart')?.getContext('2d');
  if (!ctx) return;
  scoreChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'Anomaly Score',
          data: [], borderColor: C.purple,
          backgroundColor: 'rgba(188,140,255,0.06)',
          fill: true, borderWidth: 1.5, pointRadius: 0, tension: 0.3,
        },
        {
          label: 'Threshold',
          data: [], borderColor: C.amber,
          backgroundColor: 'transparent',
          borderWidth: 1.2, borderDash: [4, 3], pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        tooltip: {
          backgroundColor: '#1c2128', borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1, padding: 6, titleColor: C.t1, bodyColor: C.t1,
          callbacks: {
            title: items => `Step ${items[0].dataIndex + 1}`,
            label: item => item.dataset.label === 'Threshold'
              ? `Threshold: ${item.raw.toFixed(5)}`
              : `Score: ${item.raw.toFixed(5)}`,
          },
        },
        annotation: { annotations: {} },
      },
      scales: {
        x: {
          ticks: { maxTicksLimit: 10, color: C.t2, callback: (_, i) => `${i + 1}` },
          grid: { color: C.grid },
          title: { display: true, text: 'Simulation step', color: C.t2, font: { size: 9 } },
        },
        y: {
          ticks: { maxTicksLimit: 6, color: C.t1 },
          grid: { color: C.grid },
          title: { display: true, text: 'Reconstruction MSE', color: C.t1, font: { size: 9 } },
        },
      },
    },
  });
}

// ── Fetch AI status ───────────────────────────────────────────────────────────
async function fetchAiStatus() {
  let json;
  try {
    json = await (await fetch('/api/ai/status')).json();
  } catch (e) { return; }
  if (!json?.ok) return;

  const m = json.model || {};
  const t = json.training || {};

  // Model status card
  const hasModel = m.version !== null && m.version !== undefined;
  setText('no-model-notice', hasModel ? '' : null, 'display',
          hasModel ? 'none' : '');
  document.getElementById('no-model-notice').style.display = hasModel ? 'none' : '';

  setText('ms-version',    hasModel ? `v${m.version}` : '—');
  setText('ms-threshold',  m.threshold != null ? m.threshold.toFixed(6) : '—');
  setText('ms-method',     m.threshold_method || '—');
  setText('ms-dataset',    m.dataset_size ? `${m.dataset_size.toLocaleString()} normal readings` : '—');
  setText('ms-loss',       m.training_loss != null ? m.training_loss.toFixed(6) : '—');
  setText('ms-val-loss',   m.val_loss      != null ? m.val_loss.toFixed(6)      : '—');
  setText('ms-epochs',     m.epochs_run    != null ? `${m.epochs_run}` : '—');
  setText('ms-trained-at', m.trained_at ? m.trained_at.replace('T', ' ').slice(0, 19) + ' UTC' : '—');

  // Registry
  setText('registry-count-badge', json.registry_count || 0);
  renderRegistry(json.registry || []);

  // Training progress
  const isTraining = t.running;
  const trainBtn   = document.getElementById('train-btn');
  const progressArea = document.getElementById('train-progress-area');
  const errTxt     = document.getElementById('train-error-txt');
  const okTxt      = document.getElementById('train-success-txt');

  if (isTraining) {
    trainingWasRunning = true;
    if (trainBtn)      { trainBtn.disabled = true; trainBtn.textContent = 'Training…'; }
    if (progressArea)  progressArea.style.display = '';
    if (errTxt)        errTxt.style.display = 'none';
    if (okTxt)         okTxt.style.display  = 'none';
    animateProgressBar();
    setPollInterval(1500);
  } else {
    if (trainBtn) { trainBtn.disabled = false; trainBtn.textContent = 'Train AI Model'; }
    if (progressArea) progressArea.style.display = 'none';
    stopProgressBarAnim();

    if (trainingWasRunning) {
      trainingWasRunning = false;
      if (t.error) {
        if (errTxt) { errTxt.textContent = '❌ ' + t.error; errTxt.style.display = ''; }
      } else {
        if (okTxt) {
          okTxt.textContent = `✅ Training complete — v${m.version}  threshold: ${(m.threshold||0).toFixed(5)}`;
          okTxt.style.display = '';
          setTimeout(() => { if (okTxt) okTxt.style.display = 'none'; }, 8000);
        }
      }
      setPollInterval(3000);
    }
  }

  // Sim state info
  try {
    const sd = await (await fetch('/api/system/status')).json();
    const state = sd.state || 'idle';
    const infoEl = document.getElementById('ai-sim-state-info');
    if (infoEl) {
      if (state === 'running') {
        infoEl.textContent = `Simulation running: "${sd.scenario_name || '?'}" · step ${sd.step}/${sd.total_steps}`;
        infoEl.style.color = 'var(--green)';
      } else {
        infoEl.textContent = sd.scenario_name ? `Last run: "${sd.scenario_name}"` : 'Simulation idle';
        infoEl.style.color = 'var(--t2)';
      }
    }
  } catch (e) {}
}

// ── Fetch experiment data ─────────────────────────────────────────────────────
async function fetchExperiment() {
  let json;
  try {
    json = await (await fetch('/api/ai/experiment')).json();
  } catch (e) { return; }
  if (!json?.ok) return;

  const d = json.data || {};

  // Scenario badge
  const badge = document.getElementById('exp-scenario-badge');
  if (badge && d.scenario_name) badge.textContent = d.scenario_name;

  // SCADA column
  setText('exp-scada-step',  d.scada_first_alarm_step != null ? `Step ${d.scada_first_alarm_step}` : 'Not triggered');
  setText('exp-scada-time',  d.scada_first_alarm_ts   ? d.scada_first_alarm_ts.split('T')[1]?.slice(0, 8) || '—' : '—');
  setText('exp-scada-count', d.scada_alarm_count != null ? d.scada_alarm_count : '—');

  // AI column
  setText('exp-ai-step',  d.ai_first_anomaly_step != null ? `Step ${d.ai_first_anomaly_step}` : 'Not triggered');
  setText('exp-ai-time',  d.ai_first_anomaly_ts   ? d.ai_first_anomaly_ts.split('T')[1]?.slice(0, 8) || '—' : '—');
  setText('exp-ai-count', d.ai_anomaly_count != null ? d.ai_anomaly_count : '—');

  // Verdict
  const verdictEl = document.getElementById('verdict-text');
  const iconEl    = document.getElementById('verdict-icon');
  const verdictBox = document.getElementById('experiment-verdict');
  if (verdictEl && d.steps_run > 0) {
    verdictEl.textContent = d.latency_verdict;
    if (iconEl) {
      if (d.ai_advantage) {
        iconEl.textContent = '✅';
        verdictBox?.classList.remove('verdict-neutral', 'verdict-scada');
        verdictBox?.classList.add('verdict-ai');
      } else if (d.latency_steps !== null && d.latency_steps < 0) {
        iconEl.textContent = '⚠️';
        verdictBox?.classList.remove('verdict-neutral', 'verdict-ai');
        verdictBox?.classList.add('verdict-scada');
      } else {
        iconEl.textContent = '⚡';
        verdictBox?.classList.remove('verdict-ai', 'verdict-scada');
        verdictBox?.classList.add('verdict-neutral');
      }
    }
  }

  // Stats chips
  setText('exp-steps-run',  d.steps_run  || '—');
  setText('exp-score-mean', d.score_mean != null ? d.score_mean.toFixed(5) : '—');
  setText('exp-score-max',  d.score_max  != null ? d.score_max.toFixed(5)  : '—');
  setText('exp-threshold',  d.threshold_used != null ? d.threshold_used.toFixed(5) : '—');
}

// ── Fetch score history ───────────────────────────────────────────────────────
async function fetchScores() {
  let json;
  try {
    json = await (await fetch('/api/ai/scores?limit=500')).json();
  } catch (e) { return; }
  if (!json?.ok || !Array.isArray(json.data) || json.data.length === 0) return;

  const scores    = json.data;
  const threshold = json.threshold || 0.07;
  const labels    = scores.map((_, i) => i + 1);

  const emptyEl   = document.getElementById('score-chart-empty');
  if (emptyEl) emptyEl.style.display = 'none';

  if (!scoreChart) return;
  scoreChart.data.labels                = labels;
  scoreChart.data.datasets[0].data      = scores;
  scoreChart.data.datasets[1].data      = labels.map(() => threshold);

  // Colour anomaly points
  scoreChart.data.datasets[0].pointRadius = scores.map(s => s > threshold ? 3 : 0);
  scoreChart.data.datasets[0].pointBackgroundColor = scores.map(s =>
    s > threshold ? C.red : C.purple
  );

  scoreChart.update('none');

  // Live value
  const last = scores[scores.length - 1];
  const liveEl = document.getElementById('score-live-val');
  if (liveEl) {
    liveEl.textContent = last.toFixed(5);
    liveEl.style.color = last > threshold ? C.red : C.purple;
  }
}

// ── Registry renderer ─────────────────────────────────────────────────────────
function renderRegistry(entries) {
  const list = document.getElementById('registry-list');
  if (!list) return;
  if (!entries.length) {
    list.innerHTML = '<div class="registry-empty">No trained models yet</div>';
    return;
  }
  list.innerHTML = [...entries].reverse().map(e => `
    <div class="registry-entry ${e.version === entries[entries.length-1].version ? 'registry-latest' : ''}">
      <div class="re-header">
        <span class="re-version">v${e.version}</span>
        ${e.version === entries[entries.length-1].version ? '<span class="re-latest-badge">LATEST</span>' : ''}
        <span class="re-date">${(e.trained_at||'').replace('T',' ').slice(0,16)} UTC</span>
      </div>
      <div class="re-stats">
        <span class="re-stat"><span class="re-stat-label">threshold</span><span class="re-stat-val">${(e.threshold||0).toFixed(5)}</span></span>
        <span class="re-stat"><span class="re-stat-label">loss</span><span class="re-stat-val">${(e.training_loss||0).toFixed(5)}</span></span>
        <span class="re-stat"><span class="re-stat-label">data</span><span class="re-stat-val">${(e.dataset_size||0).toLocaleString()}</span></span>
        <span class="re-stat"><span class="re-stat-label">epochs</span><span class="re-stat-val">${e.epochs_run||'?'}</span></span>
      </div>
      <div class="re-method">${e.threshold_method||''}</div>
    </div>`).join('');
}

// ── Training ──────────────────────────────────────────────────────────────────
async function startTraining() {
  const steps  = parseInt(document.getElementById('train-steps')?.value  || '500');
  const epochs = parseInt(document.getElementById('train-epochs')?.value || '50');
  const errTxt = document.getElementById('train-error-txt');
  const okTxt  = document.getElementById('train-success-txt');
  if (errTxt) errTxt.style.display = 'none';
  if (okTxt)  okTxt.style.display  = 'none';

  try {
    const res  = await fetch('/api/ai/train', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ steps, epochs }),
    });
    const data = await res.json();
    if (!data.ok) {
      if (errTxt) { errTxt.textContent = '❌ ' + (data.message || 'Failed'); errTxt.style.display = ''; }
    }
    // Status will be picked up on next poll
  } catch (e) {
    if (errTxt) { errTxt.textContent = '❌ Network error: ' + e.message; errTxt.style.display = ''; }
  }
}

// ── Progress bar animation ────────────────────────────────────────────────────
let _pbAnim = null;
let _pbPct  = 0;
function animateProgressBar() {
  if (_pbAnim) return;
  _pbPct = 0;
  _pbAnim = setInterval(() => {
    // Slow logarithmic approach to 95 %
    _pbPct += (95 - _pbPct) * 0.015;
    const bar = document.getElementById('train-progress-bar');
    const txt = document.getElementById('train-status-txt');
    if (bar) bar.style.width = `${Math.min(_pbPct, 95)}%`;
    if (txt) {
      if (_pbPct < 20)      txt.textContent = 'Generating normal dataset…';
      else if (_pbPct < 40) txt.textContent = 'Preprocessing & scaling data…';
      else if (_pbPct < 65) txt.textContent = 'Training autoencoder (this may take a minute)…';
      else if (_pbPct < 85) txt.textContent = 'Calibrating anomaly threshold…';
      else                  txt.textContent = 'Saving model artifacts…';
    }
  }, 200);
}
function stopProgressBarAnim() {
  if (_pbAnim) { clearInterval(_pbAnim); _pbAnim = null; }
  const bar = document.getElementById('train-progress-bar');
  if (bar) { bar.style.width = '100%'; setTimeout(() => { bar.style.width = '0%'; }, 600); }
}

// ── Polling ───────────────────────────────────────────────────────────────────
async function poll() {
  await fetchAiStatus();
  await fetchExperiment();
  await fetchScores();
}

function setPollInterval(ms) {
  if (ms === pollInterval) return;
  pollInterval = ms;
  clearInterval(pollTimer);
  pollTimer = setInterval(poll, pollInterval);
}

// ── Utility ───────────────────────────────────────────────────────────────────
function setText(id, text) {
  const el = document.getElementById(id);
  if (el && text !== null) el.textContent = text;
}

// ── Boot ──────────────────────────────────────────────────────────────────────
buildScoreChart();
poll();
pollTimer = setInterval(poll, pollInterval);
