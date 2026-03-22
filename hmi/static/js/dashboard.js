/**
 * dashboard.js — Operations Dashboard
 *
 * Adaptive polling: 500 ms running · 3 s idle
 * AI score chart uses /api/ai/scores (continuous history, all steps)
 * Experiment mini-summary shown in info bar
 */

'use strict';

const C = {
  red:'#f85149', blue:'#58a6ff', green:'#3fb950',
  purple:'#bc8cff', amber:'#d29922', teal:'#39d3c3',
  t1:'#8b949e', t2:'#484f58', grid:'rgba(255,255,255,0.06)',
};

Chart.defaults.color          = C.t1;
Chart.defaults.borderColor    = C.grid;
Chart.defaults.font.family    = "'SF Pro Display','Segoe UI',system-ui,sans-serif";
Chart.defaults.font.size      = 10;
Chart.defaults.animation      = false;
Chart.defaults.plugins.legend.display = false;

let pollTimer    = null;
let pollInterval = 3000;
let eventFilter  = 'all';
const _seen      = new Set();
const MAX_PTS    = 300;

let mainChart, tempChart, vibChart, aiChart;

// ── Charts ────────────────────────────────────────────────────────────────────
function buildMainChart() {
  const ctx = document.getElementById('main-chart')?.getContext('2d');
  if (!ctx) return;
  mainChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label:'Pressure (bar)', data:[], borderColor:C.red,  backgroundColor:'transparent',
          borderWidth:1.5, pointRadius:0, tension:0.3, yAxisID:'yP' },
        { label:'Flow (m³/s)',    data:[], borderColor:C.blue, backgroundColor:'transparent',
          borderWidth:1.5, pointRadius:0, tension:0.3, yAxisID:'yF' },
      ],
    },
    options: {
      responsive:true, maintainAspectRatio:false,
      interaction:{ mode:'index', intersect:false },
      plugins:{
        tooltip:{
          backgroundColor:'#1c2128', borderColor:'rgba(255,255,255,0.12)',
          borderWidth:1, titleColor:C.t1, bodyColor:C.t1, padding:8,
          callbacks:{ title: items => items[0].label.split('T')[1]?.slice(0,8)||items[0].label }
        },
      },
      scales:{
        x:{ ticks:{ maxTicksLimit:8, color:C.t2,
              callback:(_,i)=>{ const l=mainChart?.data?.labels?.[i]||''; return l.split('T')[1]?.slice(0,5)||''; }
            }, grid:{color:C.grid} },
        yP:{ type:'linear', position:'left',  ticks:{color:C.red, maxTicksLimit:5},
             grid:{color:C.grid}, title:{display:true,text:'bar',color:C.red,font:{size:9}} },
        yF:{ type:'linear', position:'right', ticks:{color:C.blue,maxTicksLimit:5},
             grid:{drawOnChartArea:false}, title:{display:true,text:'m³/s',color:C.blue,font:{size:9}} },
      },
    },
  });
}

function buildMini(id, color) {
  const ctx = document.getElementById(id)?.getContext('2d');
  if (!ctx) return null;
  return new Chart(ctx, {
    type:'line',
    data:{ labels:[], datasets:[{ data:[], borderColor:color, backgroundColor:'transparent',
      borderWidth:1.5, pointRadius:0, tension:0.4 }] },
    options:{ responsive:true, maintainAspectRatio:false,
      plugins:{tooltip:{enabled:false}}, scales:{x:{display:false},y:{display:false}} },
  });
}

function buildAiChart() {
  const ctx = document.getElementById('ai-chart')?.getContext('2d');
  if (!ctx) return;
  aiChart = new Chart(ctx, {
    type:'line',
    data:{ labels:[], datasets:[
      { label:'Score', data:[], borderColor:C.purple, backgroundColor:'rgba(188,140,255,0.06)',
        fill:true, borderWidth:1.5, pointRadius:0, tension:0.3 },
      { label:'Threshold', data:[], borderColor:C.amber, backgroundColor:'transparent',
        borderWidth:1, borderDash:[3,3], pointRadius:0 },
    ]},
    options:{ responsive:true, maintainAspectRatio:false,
      plugins:{tooltip:{enabled:false}}, scales:{x:{display:false},y:{display:false}} },
  });
}

// ── Telemetry ─────────────────────────────────────────────────────────────────
async function fetchTelemetry() {
  let json;
  try { json = await (await fetch(`/api/telemetry/live?limit=${MAX_PTS}`)).json(); }
  catch(e) { return; }
  if (!json?.ok || !Array.isArray(json.data) || json.data.length === 0) return;

  const rows   = json.data;
  const labels = rows.map(r=>r.timestamp);

  if (mainChart) {
    mainChart.data.labels           = labels;
    mainChart.data.datasets[0].data = rows.map(r=>r.pressure_bar);
    mainChart.data.datasets[1].data = rows.map(r=>r.flow_m3s);
    mainChart.update('none');
  }
  if (tempChart) { tempChart.data.labels = labels; tempChart.data.datasets[0].data = rows.map(r=>r.temperature_c); tempChart.update('none'); }
  if (vibChart)  { vibChart.data.labels  = labels; vibChart.data.datasets[0].data  = rows.map(r=>r.vibration);     vibChart.update('none'); }

  const last = rows[rows.length-1];
  updateKpi('pressure',  last.pressure_bar,  50, 70);
  updateKpi('flow',      last.flow_m3s,      20, 30);
  updateKpi('temp',      last.temperature_c, 28, 32);
  setText('kpi-vibration-val', last.vibration.toFixed(2));
  setText('mini-temp-val', last.temperature_c.toFixed(1));
  setText('mini-vib-val',  last.vibration.toFixed(2));
}

function updateKpi(key, value, min, max) {
  const valEl  = document.getElementById(`kpi-${key}-val`);
  const badge  = document.getElementById(`kpi-${key}-badge`);
  const card   = document.getElementById(`kpi-${key}`);
  if (!valEl) return;
  valEl.textContent = value.toFixed(1);
  valEl.className   = 'kpi-value';
  if (card)  card.className  = 'kpi-card';
  if (badge) badge.className = 'kpi-badge';
  if (value < min || value > max) {
    valEl.classList.add('alarm'); card?.classList.add('alarm'); badge?.classList.add('badge-alarm');
    if (badge) badge.textContent = value < min ? 'ALARM LOW' : 'ALARM HIGH';
  } else if (value < min * 1.06 || value > max * 0.94) {
    valEl.classList.add('warning'); card?.classList.add('warning'); badge?.classList.add('badge-warn');
    if (badge) badge.textContent = 'WARN';
  } else {
    badge?.classList.add('badge-ok');
    if (badge) badge.textContent = 'OK';
  }
}

// ── AI Score chart (continuous — uses /api/ai/scores, not just events) ────────
async function fetchAiScores() {
  let json;
  try { json = await (await fetch('/api/ai/scores?limit=300')).json(); }
  catch(e) { return; }
  if (!json?.ok || !Array.isArray(json.data) || json.data.length === 0) return;

  const scores    = json.data;
  const threshold = json.threshold || 0.07;
  const last      = scores[scores.length - 1];

  if (aiChart) {
    aiChart.data.labels           = scores.map((_, i) => i);
    aiChart.data.datasets[0].data = scores;
    aiChart.data.datasets[1].data = scores.map(() => threshold);
    aiChart.update('none');
  }

  setText('mini-ai-val',     last.toFixed(4));
  setText('ai-score-inline', last.toFixed(4));

  if (last > threshold) {
    document.getElementById('kpi-vibration')?.classList.add('ai-flag');
    document.getElementById('kpi-vibration-val')?.classList.add('ai-flag');
    const b = document.getElementById('kpi-vibration-badge');
    if (b) { b.className = 'kpi-badge badge-ai'; b.textContent = 'AI FLAG'; }
  }
}

// ── AI events (for event feed dedup + feature explanation bars) ───────────────
async function fetchAiEvents() {
  let json;
  try { json = await (await fetch('/api/ai-events/live?limit=100')).json(); }
  catch(e) { return; }
  if (!json?.ok || !Array.isArray(json.data)) return;
  json.data.forEach(r => appendEvent('ai', r));
}

// ── SCADA events ──────────────────────────────────────────────────────────────
async function fetchScadaEvents() {
  let json;
  try { json = await (await fetch('/api/events/live?limit=100')).json(); }
  catch(e) { return; }
  if (!json?.ok || !Array.isArray(json.data)) return;
  json.data.forEach(r => appendEvent('scada', r));
}

// ── Experiment mini-summary ───────────────────────────────────────────────────
async function fetchExperimentSummary() {
  let json;
  try { json = await (await fetch('/api/ai/experiment')).json(); }
  catch(e) { return; }
  if (!json?.ok) return;
  const d  = json.data || {};
  const el = document.getElementById('experiment-mini');
  if (!el) return;
  if (d.steps_run > 0 && d.latency_verdict && d.latency_verdict !== 'No fault detected yet') {
    el.textContent = '⚗️ ' + d.latency_verdict;
    el.style.color  = d.ai_advantage ? 'var(--green)' : 'var(--amber)';
    el.style.display = '';
  } else {
    el.style.display = 'none';
  }
}

// ── Event feed ────────────────────────────────────────────────────────────────
function appendEvent(kind, row) {
  const key = `${kind}-${row.timestamp}`;
  if (_seen.has(key)) return;
  _seen.add(key);

  const list = document.getElementById('events-list');
  if (!list) return;
  const empty = list.querySelector('.events-empty');
  if (empty) empty.remove();

  const item = document.createElement('div');
  item.classList.add('event-item');
  item.dataset.kind = kind;
  const ts = row.timestamp?.split('T')[1]?.slice(0,8) || row.timestamp || '';

  if (kind === 'ai') {
    item.classList.add('ai-anomaly');
    const expl   = row.explanation || {};
    const maxErr = Math.max(...Object.values(expl), 0.001);
    const bars   = Object.entries(expl).map(([feat, val]) => `
      <div class="explain-row">
        <span class="explain-feature">${feat}</span>
        <div class="explain-bar-bg"><div class="explain-bar" style="width:${Math.round(val/maxErr*100)}%"></div></div>
        <span class="explain-score">${val.toFixed(4)}</span>
      </div>`).join('');
    item.innerHTML = `
      <div class="event-top">
        <span class="event-type-badge badge-ai">AI ANOMALY</span>
        <span class="event-time">${ts}</span>
      </div>
      <div class="event-desc">Multivariate pattern deviation</div>
      <div class="event-val">score: ${row.anomaly_score?.toFixed(4)} · threshold: ${row.threshold?.toFixed(4)}</div>
      ${bars ? `<div class="explain-block"><div class="explain-title">FEATURE CONTRIBUTIONS</div>${bars}</div>` : ''}`;
  } else {
    const sev = (row.severity || '').toUpperCase();
    item.classList.add(sev === 'HIGH' ? 'scada-high' : 'scada-medium');
    item.innerHTML = `
      <div class="event-top">
        <span class="event-type-badge ${sev === 'HIGH' ? 'badge-scada-high' : 'badge-scada-medium'}">SCADA ${sev}</span>
        <span class="event-time">${ts}</span>
      </div>
      <div class="event-desc">${(row.event_type || 'Alarm').replace(/_/g, ' ')}</div>
      <div class="event-val">${row.parameter}: ${Number(row.value || 0).toFixed(2)}</div>`;
  }

  list.insertBefore(item, list.firstChild);
  applyEventFilter();
}

function setEventFilter(f) {
  eventFilter = f;
  document.querySelectorAll('.etab').forEach(b => b.classList.toggle('active', b.dataset.filter === f));
  applyEventFilter();
}

function applyEventFilter() {
  document.querySelectorAll('#events-list .event-item').forEach(el => {
    const k = el.dataset.kind;
    el.style.display = (
      eventFilter === 'all' ||
      (eventFilter === 'scada' && k === 'scada') ||
      (eventFilter === 'ai'    && k === 'ai')
    ) ? '' : 'none';
  });
}

// ── System status ─────────────────────────────────────────────────────────────
async function fetchStatus() {
  let d;
  try { d = await (await fetch('/api/system/status')).json(); }
  catch(e) { setText('update-indicator', 'ERR'); return 'unknown'; }

  const state   = d.state || 'idle';
  const dot     = document.getElementById('sim-state-dot');
  const label   = document.getElementById('sim-state-label');
  const info    = document.getElementById('ctrl-info');
  const stopBtn = document.getElementById('stop-btn');

  if (dot)   dot.className  = 'sim-state-dot ' + (state === 'running' ? 'running' : state === 'error' ? 'error' : state === 'stopping' ? 'stopping' : '');
  if (label) label.textContent = state.charAt(0).toUpperCase() + state.slice(1);

  if (state === 'running') {
    let infoTxt = d.scenario_name ? `"${d.scenario_name}" · ` : '';
    if (d.fault_mode && d.fault_mode !== 'none') {
      infoTxt += d.fault_active
        ? `🔴 ${d.fault_mode} ACTIVE · `
        : `⏳ fault in ${d.steps_until_fault} steps · `;
    }
    infoTxt += `step ${d.step}/${d.total_steps}`;
    if (info) info.textContent = infoTxt;
    if (stopBtn) stopBtn.style.display = '';
  } else {
    if (info) info.textContent = d.last_error ? 'Error: ' + d.last_error : (d.scenario_name ? `Last: "${d.scenario_name}"` : '');
    if (stopBtn) stopBtn.style.display = 'none';
  }

  const dbEl = document.getElementById('db-indicator');
  if (dbEl) dbEl.classList.toggle('connected', d.db_connected);

  setText('update-indicator', new Date().toLocaleTimeString());

  const ni = state === 'running' ? 500 : 3000;
  if (ni !== pollInterval) { pollInterval = ni; restartPoll(); }

  return state;
}

async function stopSimulation() {
  try { await fetch('/api/simulation/stop', { method: 'POST' }); } catch(e) {}
}

// ── Poll ──────────────────────────────────────────────────────────────────────
async function poll() {
  await fetchStatus();
  await fetchTelemetry();
  await fetchAiScores();      // continuous score chart
  await fetchAiEvents();      // anomaly events for feed
  await fetchScadaEvents();
  await fetchExperimentSummary();
}

function restartPoll() {
  clearInterval(pollTimer);
  pollTimer = setInterval(poll, pollInterval);
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// ── Init ──────────────────────────────────────────────────────────────────────
buildMainChart();
tempChart = buildMini('temp-chart', C.green);
vibChart  = buildMini('vib-chart',  C.purple);
buildAiChart();

poll();
pollTimer = setInterval(poll, pollInterval);
