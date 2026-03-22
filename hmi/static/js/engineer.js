'use strict';
/**
 * engineer.js — Pipeline Builder
 *
 * - Absolutely-positioned nodes on canvas-viewport
 * - SVG overlay with clean orthogonal connectors + SVG marker arrowheads
 * - Drag-and-drop via mousedown/mousemove/mouseup
 * - sessionStorage auto-save: canvas persists across page navigations
 * - 8 scenario templates
 * - Save / Load pipeline JSON
 */

// ── Component metadata ────────────────────────────────────────────────────────
const COMP_META = {
  inlet:         { label:'Inlet',       typeLabel:'Source',   singleton:true  },
  outlet:        { label:'Outlet',      typeLabel:'Sink',     singleton:true  },
  pipe:          { label:'Pipe',        typeLabel:'Segment',  singleton:false },
  bend:          { label:'Bend',        typeLabel:'Bend',     singleton:false },
  valve:         { label:'Valve',       typeLabel:'Control',  singleton:false },
  sensor:        { label:'Sensor',      typeLabel:'Monitor',  singleton:false },
  compressor:    { label:'Compressor',  typeLabel:'Pump',     singleton:false },
  fault_leak:    { label:'Leak',        typeLabel:'Fault',    singleton:false },
  fault_blockage:{ label:'Blockage',    typeLabel:'Fault',    singleton:false },
};

const NODE_W = 110;
const NODE_H = 64;
const DEF_Y  = 130;

// ── ID helpers ────────────────────────────────────────────────────────────────
let _ctrs = {};
function _nextId(p){ _ctrs[p] = (_ctrs[p]||0)+1; return `${p}${_ctrs[p]}`; }
function nextNodeId(){ return _nextId('nd'); }

function defaultProps(type){
  switch(type){
    case 'pipe':           return {length_m:2500, diameter_m:0.8};
    case 'bend':           return {count:1};
    case 'valve':          return {id:_nextId('V'), state:1};
    case 'sensor':         return {id:_nextId('S')};
    case 'compressor':     return {id:_nextId('C'), power_kw:500};
    case 'fault_leak':     return {step_offset:0, severity:'0.7'};
    case 'fault_blockage': return {step_offset:0, severity:'0.7'};
    default:               return {};
  }
}

// ── App state ─────────────────────────────────────────────────────────────────
let nodes      = [];
let selectedId = null;
let dragging   = null;

// ── Canvas state persistence (sessionStorage) ─────────────────────────────────
// Full pipeline canvas persists across page navigations within the same browser tab.
// Key uses version suffix so old incompatible states are ignored automatically.
const _STATE_KEY = 'dt_scada_pipeline_v1';

function saveState(){
  try {
    sessionStorage.setItem(_STATE_KEY, JSON.stringify({
      nodes,
      cfg:         {...G},
      scenarioKey:  _activeScenarioKey,
      scenarioName: _activeScenarioName,
    }));
  } catch(e) {}
}

function loadSavedState(){
  try {
    const raw = sessionStorage.getItem(_STATE_KEY);
    if (!raw) return false;
    const s = JSON.parse(raw);
    if (!s || !Array.isArray(s.nodes)) return false;
    nodes = s.nodes;
    if (s.cfg) Object.assign(G, s.cfg);
    _activeScenarioKey  = s.scenarioKey  || 'normal';
    _activeScenarioName = s.scenarioName || 'Normal Pipeline';
    return true;
  } catch(e) { return false; }
}

function clearSavedState(){
  try { sessionStorage.removeItem(_STATE_KEY); } catch(e) {}
}

const G = {
  pipeline_length_m:10000, pipeline_diameter_m:0.8,
  gas_density:0.8, friction_coefficient:0.002, num_bends:0,
  normal_pressure_bar:60, normal_flow_m3s:25,
  normal_temperature_c:30, normal_vibration:0.4,
  pressure_min:50, pressure_max:70, flow_min:20, flow_max:30,
  fault_mode:'none', fault_start_step:150, steps:300, step_seconds:1,
};

// ── Templates ─────────────────────────────────────────────────────────────────
const TEMPLATES = {
  normal:{
    name:'✅  Normal Pipeline',
    desc:'10 km baseline — no faults. Use this to train the AI anomaly detector.',
    cfg:{fault_mode:'none', fault_start_step:300, steps:300, step_seconds:0.5,
         normal_pressure_bar:60, normal_flow_m3s:25},
    nodes:[
      {type:'inlet',  x:40,  y:DEF_Y},
      {type:'pipe',   x:200, y:DEF_Y, props:{length_m:3000,diameter_m:0.8}},
      {type:'sensor', x:370, y:DEF_Y, props:{id:'S1'}},
      {type:'valve',  x:540, y:DEF_Y, props:{id:'V1',state:1}},
      {type:'pipe',   x:710, y:DEF_Y, props:{length_m:4000,diameter_m:0.8}},
      {type:'sensor', x:880, y:DEF_Y, props:{id:'S2'}},
      {type:'pipe',   x:1050,y:DEF_Y, props:{length_m:3000,diameter_m:0.8}},
      {type:'outlet', x:1220,y:DEF_Y},
    ]
  },
  slight_drift:{
    name:'⚠️  Slight Fault — Sensor Drift',
    desc:'Gradual pressure sensor drift from step 30. SCADA stays silent. Tests AI early detection.',
    cfg:{fault_mode:'sensor_drift', fault_start_step:30, steps:120, step_seconds:0.5,
         normal_pressure_bar:60, normal_flow_m3s:25},
    nodes:[
      {type:'inlet',      x:40,  y:DEF_Y},
      {type:'pipe',       x:200, y:DEF_Y, props:{length_m:4000,diameter_m:0.8}},
      {type:'sensor',     x:370, y:DEF_Y, props:{id:'S1'}},
      {type:'valve',      x:540, y:DEF_Y, props:{id:'V1',state:1}},
      {type:'pipe',       x:710, y:DEF_Y, props:{length_m:6000,diameter_m:0.8}},
      {type:'sensor',     x:880, y:DEF_Y, props:{id:'S2'}},
      {type:'fault_leak', x:880, y:DEF_Y+110, props:{step_offset:200,severity:'0.3'}},
      {type:'outlet',     x:1050,y:DEF_Y},
    ]
  },
  pressure_leak:{
    name:'🔴  Pressure Leak',
    desc:'Sudden pipe leak at step 30. Pressure drops, flow spikes. SCADA triggers HIGH alarms immediately.',
    cfg:{fault_mode:'leak', fault_start_step:30, steps:120, step_seconds:0.5,
         normal_pressure_bar:60, normal_flow_m3s:25},
    nodes:[
      {type:'inlet',      x:40,  y:DEF_Y},
      {type:'pipe',       x:200, y:DEF_Y, props:{length_m:3000,diameter_m:0.8}},
      {type:'sensor',     x:370, y:DEF_Y, props:{id:'S1'}},
      {type:'fault_leak', x:540, y:DEF_Y+110, props:{step_offset:0,severity:'0.8'}},
      {type:'pipe',       x:710, y:DEF_Y, props:{length_m:4000,diameter_m:0.8}},
      {type:'valve',      x:880, y:DEF_Y, props:{id:'V1',state:1}},
      {type:'pipe',       x:1050,y:DEF_Y, props:{length_m:3000,diameter_m:0.8}},
      {type:'outlet',     x:1220,y:DEF_Y},
    ]
  },
  blockage:{
    name:'🔴  Pipeline Blockage',
    desc:'Flow obstruction from step 30. Upstream pressure builds, flow drops. Classic SCADA scenario.',
    cfg:{fault_mode:'blockage', fault_start_step:30, steps:120, step_seconds:0.5,
         normal_pressure_bar:60, normal_flow_m3s:25},
    nodes:[
      {type:'inlet',           x:40,  y:DEF_Y},
      {type:'pipe',            x:200, y:DEF_Y, props:{length_m:3000,diameter_m:0.8}},
      {type:'sensor',          x:370, y:DEF_Y, props:{id:'S1'}},
      {type:'fault_blockage',  x:540, y:DEF_Y+110, props:{step_offset:0,severity:'0.9'}},
      {type:'valve',           x:710, y:DEF_Y, props:{id:'V1',state:1}},
      {type:'pipe',            x:880, y:DEF_Y, props:{length_m:5000,diameter_m:0.8}},
      {type:'outlet',          x:1050,y:DEF_Y},
    ]
  },
  silent_degradation:{
    name:'🕵️  Silent Degradation',
    desc:'Smooth start, drift from step 20. SCADA stays silent. Tests how early AI detects patterns.',
    cfg:{fault_mode:'sensor_drift', fault_start_step:20, steps:150, step_seconds:0.5,
         normal_pressure_bar:60, normal_flow_m3s:25},
    nodes:[
      {type:'inlet',  x:40,  y:DEF_Y},
      {type:'pipe',   x:200, y:DEF_Y, props:{length_m:4000,diameter_m:0.8}},
      {type:'sensor', x:370, y:DEF_Y, props:{id:'S1'}},
      {type:'sensor', x:540, y:DEF_Y, props:{id:'S2'}},
      {type:'valve',  x:710, y:DEF_Y, props:{id:'V1',state:1}},
      {type:'pipe',   x:880, y:DEF_Y, props:{length_m:6000,diameter_m:0.8}},
      {type:'sensor', x:1050,y:DEF_Y, props:{id:'S3'}},
      {type:'outlet', x:1220,y:DEF_Y},
    ]
  },
  valve_stuck:{
    name:'⚠️  Valve Stuck Closed',
    desc:'Valve closes from step 30. Pressure builds upstream, flow falls. Multivariate AI test.',
    cfg:{fault_mode:'blockage', fault_start_step:30, steps:120, step_seconds:0.5,
         normal_pressure_bar:65, normal_flow_m3s:20},
    nodes:[
      {type:'inlet',  x:40,  y:DEF_Y},
      {type:'pipe',   x:200, y:DEF_Y, props:{length_m:5000,diameter_m:0.8}},
      {type:'sensor', x:370, y:DEF_Y, props:{id:'S1'}},
      {type:'valve',  x:540, y:DEF_Y, props:{id:'V1',state:0}},
      {type:'pipe',   x:710, y:DEF_Y, props:{length_m:5000,diameter_m:0.8}},
      {type:'sensor', x:880, y:DEF_Y, props:{id:'S2'}},
      {type:'outlet', x:1050,y:DEF_Y},
    ]
  },
  compressor_failure:{
    name:'🔴  Compressor Failure',
    desc:'Compressor trips at step 25. Flow collapses, downstream pressure falls. Tests AI reaction speed vs SCADA.',
    cfg:{fault_mode:'blockage', fault_start_step:25, steps:100, step_seconds:0.5,
         normal_pressure_bar:60, normal_flow_m3s:25},
    nodes:[
      {type:'inlet',      x:40,  y:DEF_Y},
      {type:'compressor', x:200, y:DEF_Y, props:{id:'C1',power_kw:500}},
      {type:'pipe',       x:370, y:DEF_Y, props:{length_m:4000,diameter_m:0.8}},
      {type:'sensor',     x:540, y:DEF_Y, props:{id:'S1'}},
      {type:'fault_blockage', x:710, y:DEF_Y+110, props:{step_offset:0,severity:'1.0'}},
      {type:'pipe',       x:880, y:DEF_Y, props:{length_m:4000,diameter_m:0.8}},
      {type:'outlet',     x:1050,y:DEF_Y},
    ]
  },
  full_fault:{
    name:'💀  Full System Fault',
    desc:'Simultaneous leak + blockage from step 20. Max stress. Both SCADA and AI respond.',
    cfg:{fault_mode:'leak', fault_start_step:20, steps:100, step_seconds:0.5,
         normal_pressure_bar:60, normal_flow_m3s:25},
    nodes:[
      {type:'inlet',           x:40,  y:DEF_Y},
      {type:'pipe',            x:200, y:DEF_Y, props:{length_m:2000,diameter_m:0.8}},
      {type:'fault_leak',      x:200, y:DEF_Y+110, props:{step_offset:0,severity:'1.0'}},
      {type:'sensor',          x:370, y:DEF_Y, props:{id:'S1'}},
      {type:'fault_blockage',  x:540, y:DEF_Y+110, props:{step_offset:0,severity:'0.8'}},
      {type:'valve',           x:710, y:DEF_Y, props:{id:'V1',state:0}},
      {type:'pipe',            x:880, y:DEF_Y, props:{length_m:2000,diameter_m:0.8}},
      {type:'outlet',          x:1050,y:DEF_Y},
    ]
  },
};

// ── Load template ─────────────────────────────────────────────────────────────
function loadTemplate(key){
  const tpl = TEMPLATES[key];
  if (!tpl || !tpl.nodes) return;
  _ctrs = {};
  nodes = tpl.nodes.map(n => ({
    id:    nextNodeId(),
    type:  n.type,
    x:     n.x,
    y:     n.y,
    props: n.props ? {...n.props} : defaultProps(n.type),
  }));
  if (tpl.cfg) Object.assign(G, tpl.cfg);
  selectedId = null;
  dragging   = null;
  render();
  showToast(`Loaded: ${tpl.name}`);
}

// ── Add component ─────────────────────────────────────────────────────────────
function addComponent(type){
  const meta = COMP_META[type];
  if (!meta) return;
  if (meta.singleton && nodes.some(n => n.type === type)){
    showToast(`Only one ${meta.label} allowed`); return;
  }
  const maxX    = nodes.length ? Math.max(...nodes.map(n => n.x)) : -150;
  const isFault = type.startsWith('fault_');
  const x       = isFault ? Math.max(40, maxX - 160) : maxX + 160;
  const y       = isFault ? DEF_Y + 110 : DEF_Y;
  const node    = { id:nextNodeId(), type, x, y, props:defaultProps(type) };
  nodes.push(node);
  selectedId = node.id;
  render();
  setTimeout(()=>{
    const s = document.getElementById('canvas-scroll');
    if (s) s.scrollLeft = s.scrollWidth;
  }, 50);
}

function removeNode(id){
  nodes = nodes.filter(n => n.id !== id);
  if (selectedId === id) selectedId = null;
  render();
}

function selectNode(id){
  selectedId = (selectedId === id) ? null : id;
  document.querySelectorAll('.pipe-node').forEach(el => {
    el.classList.toggle('selected', el.dataset.id === selectedId);
  });
  renderProps();
}

function clearPipeline(){
  nodes      = [];
  _ctrs      = {};
  selectedId = null;
  dragging   = null;
  clearSavedState();
  render();
}

// ── Master render ─────────────────────────────────────────────────────────────
function render(){
  renderNodes();
  renderConnections();
  renderProps();
  renderFooter();
  saveState();  // persist canvas to sessionStorage on every change
}

// ── Node rendering ────────────────────────────────────────────────────────────
function renderNodes(){
  const vp      = document.getElementById('canvas-viewport');
  const emptyEl = document.getElementById('canvas-empty');
  const stats   = document.getElementById('pipeline-stats');
  if (!vp) return;

  if (emptyEl) emptyEl.style.display = nodes.length === 0 ? 'flex' : 'none';
  if (stats)   stats.textContent = `${nodes.length} component${nodes.length !== 1 ? 's' : ''}`;

  vp.querySelectorAll('.pipe-node').forEach(el => el.remove());
  if (nodes.length === 0) return;

  const maxX = Math.max(...nodes.map(n => n.x)) + NODE_W + 80;
  const maxY = Math.max(...nodes.map(n => n.y)) + NODE_H + 80;
  vp.style.minWidth  = `${Math.max(maxX, 800)}px`;
  vp.style.minHeight = `${Math.max(maxY, 320)}px`;
  const svg = document.getElementById('pipe-connections');
  if (svg){
    svg.style.width  = `${Math.max(maxX, 800)}px`;
    svg.style.height = `${Math.max(maxY, 320)}px`;
  }

  nodes.forEach(node => {
    const meta    = COMP_META[node.type] || { label:node.type, typeLabel:'?' };
    const isFault = node.type.startsWith('fault_');
    const sub     = getSubLabel(node);

    const el = document.createElement('div');
    el.className  = 'pipe-node' + (node.id === selectedId ? ' selected' : '') + (isFault ? ' fault-node' : '');
    el.dataset.id   = node.id;
    el.dataset.type = node.type;
    el.style.cssText = `left:${node.x}px;top:${node.y}px`;

    el.innerHTML = `
      <div class="node-box">
        <div class="node-type-label" data-ntype="${node.type}">${meta.typeLabel}</div>
        <div class="node-name">${getLabel(node)}</div>
        ${sub ? `<div class="node-sub">${sub}</div>` : ''}
      </div>
      <div class="node-dot" data-ntype="${node.type}"></div>
      <button class="node-remove" title="Remove">✕</button>`;

    el.addEventListener('mousedown', e => {
      if (e.target.classList.contains('node-remove')) return;
      e.preventDefault(); e.stopPropagation();
      startDrag(e, node.id);
    });
    el.addEventListener('click', e => {
      if (e.target.classList.contains('node-remove')) return;
      selectNode(node.id);
    });
    el.querySelector('.node-remove').addEventListener('click', e => {
      e.stopPropagation(); removeNode(node.id);
    });

    vp.appendChild(el);
  });
}

function getLabel(node){
  if (node.props?.id) return `${COMP_META[node.type]?.label} ${node.props.id}`;
  return COMP_META[node.type]?.label || node.type;
}

function getSubLabel(node){
  switch(node.type){
    case 'pipe':           return `${node.props.length_m}m · ⌀${node.props.diameter_m}m`;
    case 'bend':           return `${node.props.count} bend${node.props.count !== 1 ? 's' : ''}`;
    case 'valve':          return node.props.state ? 'open' : 'closed';
    case 'sensor':         return 'P · F · T · Vib';
    case 'compressor':     return `${node.props.power_kw} kW`;
    case 'fault_leak':
    case 'fault_blockage': return `@step ${node.props.step_offset || 0} · sev ${node.props.severity}`;
    default: return '';
  }
}

// ── SVG connections — clean orthogonal routing with proper arrowheads ─────────
//
// Design:
//  • SVG <defs> defines two named arrow markers (pipe and fault styles)
//  • Main pipeline: horizontal straight lines when same Y; L-shaped orthogonal
//    elbow routing when nodes are at different vertical positions
//  • Fault connectors: vertical dashed drop-lines from nearest main node
//  • No bezier curves — bezier goes diagonal and looks messy on off-axis nodes
//
function renderConnections(){
  const svg = document.getElementById('pipe-connections');
  if (!svg) return;
  svg.innerHTML = '';
  if (nodes.length < 2) return;

  // ── Arrow marker definitions ──────────────────────────────────────────────
  const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
  defs.innerHTML = `
    <marker id="arr" markerWidth="8" markerHeight="6"
            refX="7" refY="3" orient="auto" markerUnits="userSpaceOnUse">
      <polygon points="0 0, 8 3, 0 6" fill="rgba(255,255,255,0.30)"/>
    </marker>
    <marker id="arr-fault" markerWidth="8" markerHeight="6"
            refX="7" refY="3" orient="auto" markerUnits="userSpaceOnUse">
      <polygon points="0 0, 8 3, 0 6" fill="rgba(210,153,34,0.55)"/>
    </marker>`;
  svg.appendChild(defs);

  // ── Main pipeline connections ─────────────────────────────────────────────
  // Sort non-fault nodes by X position to draw left→right connections.
  const main = nodes
    .filter(n => !n.type.startsWith('fault_'))
    .sort((a, b) => a.x - b.x);

  for (let i = 0; i < main.length - 1; i++){
    const A  = main[i];
    const B  = main[i + 1];
    const x1 = A.x + NODE_W;        // right edge of A
    const y1 = A.y + NODE_H / 2;    // vertical centre of A
    const x2 = B.x;                  // left edge of B
    const y2 = B.y + NODE_H / 2;    // vertical centre of B

    let d;
    if (Math.abs(y1 - y2) <= 6){
      // Same horizontal row — straight line
      d = `M ${x1} ${y1} L ${x2} ${y2}`;
    } else {
      // Different rows — orthogonal elbow: horizontal → vertical → horizontal
      // Midpoint is where the vertical segment runs
      const midX = x1 + (x2 - x1) / 2;
      d = `M ${x1} ${y1} L ${midX} ${y1} L ${midX} ${y2} L ${x2} ${y2}`;
    }

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', d);
    path.setAttribute('stroke', 'rgba(255,255,255,0.22)');
    path.setAttribute('stroke-width', '2');
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    path.setAttribute('marker-end', 'url(#arr)');
    svg.appendChild(path);
  }

  // ── Fault drop-line connectors ────────────────────────────────────────────
  // Each fault node draws a vertical dashed line to its nearest main node.
  nodes.filter(n => n.type.startsWith('fault_')).forEach(fault => {
    const nearest = main.reduce((best, n) =>
      (!best || Math.abs(n.x - fault.x) < Math.abs(best.x - fault.x)) ? n : best, null);
    if (!nearest) return;

    const cx = nearest.x + NODE_W / 2;   // horizontal centre of nearest node
    const y1 = nearest.y + NODE_H;        // bottom of nearest node
    const y2 = fault.y;                   // top of fault node

    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', cx); line.setAttribute('y1', y1);
    line.setAttribute('x2', cx); line.setAttribute('y2', y2);
    line.setAttribute('stroke', 'rgba(210,153,34,0.45)');
    line.setAttribute('stroke-width', '1.5');
    line.setAttribute('stroke-dasharray', '5 3');
    line.setAttribute('marker-end', 'url(#arr-fault)');
    svg.appendChild(line);
  });
}

// ── Drag and drop ─────────────────────────────────────────────────────────────
function startDrag(e, id){
  const vp = document.getElementById('canvas-viewport');
  const sc = document.getElementById('canvas-scroll');
  if (!vp) return;
  const rect = vp.getBoundingClientRect();
  const node = nodes.find(n => n.id === id);
  if (!node) return;
  dragging = {
    id,
    offsetX: (e.clientX - rect.left + (sc?.scrollLeft || 0)) - node.x,
    offsetY: (e.clientY - rect.top  + (sc?.scrollTop  || 0)) - node.y,
  };
  selectNode(id);
  document.body.style.cursor = 'grabbing';
}

document.addEventListener('mousemove', e => {
  if (!dragging) return;
  const vp   = document.getElementById('canvas-viewport');
  const sc   = document.getElementById('canvas-scroll');
  if (!vp) return;
  const rect = vp.getBoundingClientRect();
  const node = nodes.find(n => n.id === dragging.id);
  if (!node) return;

  node.x = Math.max(0, Math.round(e.clientX - rect.left + (sc?.scrollLeft || 0) - dragging.offsetX));
  node.y = Math.max(0, Math.round(e.clientY - rect.top  + (sc?.scrollTop  || 0) - dragging.offsetY));

  const el = document.querySelector(`.pipe-node[data-id="${dragging.id}"]`);
  if (el){ el.style.left = `${node.x}px`; el.style.top = `${node.y}px`; }

  const maxX = Math.max(...nodes.map(n => n.x)) + NODE_W + 80;
  const maxY = Math.max(...nodes.map(n => n.y)) + NODE_H + 80;
  vp.style.minWidth  = `${Math.max(maxX, 800)}px`;
  vp.style.minHeight = `${Math.max(maxY, 320)}px`;
  const svg = document.getElementById('pipe-connections');
  if (svg){ svg.style.width = `${Math.max(maxX, 800)}px`; svg.style.height = `${Math.max(maxY, 320)}px`; }

  renderConnections();
});

document.addEventListener('mouseup', () => {
  if (dragging){
    dragging = null;
    document.body.style.cursor = '';
    renderProps();
    saveState();   // save final drag position
  }
});

// ── Properties panel ──────────────────────────────────────────────────────────
function renderProps(){
  const panel = document.getElementById('props-panel-inner');
  if (!panel) return;
  const node = selectedId ? nodes.find(n => n.id === selectedId) : null;
  node ? renderNodeProps(panel, node) : renderGlobalProps(panel);
}

function renderNodeProps(panel, node){
  const meta   = COMP_META[node.type] || { label:node.type, typeLabel:'?' };
  const fields = nodeFields(node.type);
  panel.innerHTML = `
    <div class="props-section">
      <div class="props-section-title">${meta.label}
        <span class="props-badge ${badgeClass(node.type)}">${meta.typeLabel}</span>
      </div>
      <div class="field-row">
        <span class="field-label">Position</span>
        <span style="font-size:10px;color:var(--t2);font-family:var(--font-mono)">${node.x}, ${node.y}</span>
      </div>
      ${fields.map(f => buildField(f, node.props)).join('')}
    </div>
    <div class="props-section">
      <div class="props-section-title" style="margin-bottom:8px">Actions</div>
      <button class="btn-full btn-full-outline" id="btn-del" style="color:var(--red)">Remove component</button>
    </div>
    ${simSection()}
    ${runSection()}`;
  document.getElementById('btn-del')?.addEventListener('click', () => removeNode(node.id));
  fields.forEach(f => {
    const el = document.getElementById(`f-${f.key}`);
    if (!el) return;
    el.addEventListener('change', () => {
      node.props[f.key] = f.type === 'select' ? el.value
                        : (f.isNum !== false ? parseFloat(el.value) : el.value);
      renderNodes(); renderConnections(); renderNodeProps(panel, node);
    });
  });
  attachGlobalListeners();
}

function renderGlobalProps(panel){
  panel.innerHTML = `${configSection()}${simSection()}${runSection()}`;
  attachGlobalListeners();
}

function nodeFields(type){
  switch(type){
    case 'pipe':   return [
      {key:'length_m',  label:'Length',   unit:'m',   type:'number'},
      {key:'diameter_m',label:'Diameter', unit:'m',   type:'number'},
    ];
    case 'bend':   return [{key:'count',    label:'Count',  unit:'—',  type:'number'}];
    case 'valve':  return [
      {key:'id',   label:'ID',    unit:'—', type:'text',  isNum:false},
      {key:'state',label:'State', unit:'—', type:'select', options:[{v:'1',l:'Open'},{v:'0',l:'Closed'}]},
    ];
    case 'sensor': return [{key:'id', label:'ID', unit:'—', type:'text', isNum:false}];
    case 'compressor': return [
      {key:'id',      label:'ID',    unit:'—',  type:'text',   isNum:false},
      {key:'power_kw',label:'Power', unit:'kW', type:'number'},
    ];
    case 'fault_leak':
    case 'fault_blockage': return [
      {key:'step_offset',label:'Active at step', unit:'—',  type:'number'},
      {key:'severity',   label:'Severity',       unit:'0–1',type:'number'},
    ];
    default: return [];
  }
}

function buildField(f, props){
  const v = props[f.key] ?? '';
  if (f.type === 'select'){
    const opts = f.options.map(o =>
      `<option value="${o.v}" ${String(v) === o.v ? 'selected' : ''}>${o.l}</option>`
    ).join('');
    return `<div class="field-row">
      <span class="field-label">${f.label}</span>
      <select class="field-select" id="f-${f.key}">${opts}</select>
      <span class="field-unit">${f.unit}</span>
    </div>`;
  }
  return `<div class="field-row">
    <span class="field-label">${f.label}</span>
    <input class="field-input" id="f-${f.key}" type="${f.type}" value="${v}"/>
    <span class="field-unit">${f.unit}</span>
  </div>`;
}

function badgeClass(t){
  if (t === 'inlet' || t === 'outlet')   return 'props-badge-green';
  if (t === 'valve' || t === 'compressor') return 'props-badge-blue';
  if (t === 'sensor')                    return 'props-badge-purple';
  if (t.startsWith('fault'))             return 'props-badge-amber';
  return 'props-badge-blue';
}

function nr(key, label, val, unit){
  return `<div class="field-row">
    <span class="field-label">${label}</span>
    <input class="field-input" id="f-${key}" type="number" value="${val}" step="any"/>
    <span class="field-unit">${unit}</span>
  </div>`;
}

function configSection(){
  return `
  <div class="props-section">
    <div class="props-section-title">Pipeline parameters</div>
    ${nr('pipeline_length_m',   'Total length',   G.pipeline_length_m,   'm')}
    ${nr('pipeline_diameter_m', 'Diameter',       G.pipeline_diameter_m, 'm')}
    ${nr('gas_density',         'Gas density',    G.gas_density,         'kg/m³')}
    ${nr('friction_coefficient','Friction coeff', G.friction_coefficient,'—')}
  </div>
  <div class="props-section">
    <div class="props-section-title">Normal operating conditions</div>
    ${nr('normal_pressure_bar', 'Pressure',    G.normal_pressure_bar,  'bar')}
    ${nr('normal_flow_m3s',     'Flow',        G.normal_flow_m3s,      'm³/s')}
    ${nr('normal_temperature_c','Temperature', G.normal_temperature_c, '°C')}
    ${nr('normal_vibration',    'Vibration',   G.normal_vibration,     '—')}
  </div>
  <div class="props-section">
    <div class="props-section-title">SCADA thresholds</div>
    ${nr('pressure_min','Pressure min', G.pressure_min,'bar')}
    ${nr('pressure_max','Pressure max', G.pressure_max,'bar')}
    ${nr('flow_min',    'Flow min',     G.flow_min,    'm³/s')}
    ${nr('flow_max',    'Flow max',     G.flow_max,    'm³/s')}
  </div>`;
}

function simSection(){
  return `
  <div class="props-section">
    <div class="props-section-title">Simulation settings</div>
    <div class="field-row"><span class="field-label">Fault mode</span>
      <select class="field-select" id="f-fault_mode" style="width:120px">
        ${['none','leak','blockage','sensor_drift'].map(v =>
          `<option value="${v}" ${G.fault_mode === v ? 'selected' : ''}>${v}</option>`
        ).join('')}
      </select>
    </div>
    ${nr('fault_start_step','Fault at step', G.fault_start_step,'—')}
    ${nr('steps',           'Total steps',   G.steps,           '—')}
    ${nr('step_seconds',    'Step interval', G.step_seconds,    's')}
  </div>`;
}

function runSection(){
  return `<div class="props-section" style="border-bottom:none">
    <button class="btn-full btn-full-primary" onclick="handleRunClick()">&#9654; Run simulation</button>
    <button class="btn-full btn-full-outline" style="margin-top:6px" onclick="exportConfig()">Export config.py</button>
    <div class="props-status-row"><div class="status-dot"></div><span id="run-status-txt">Ready</span></div>
  </div>`;
}

function attachGlobalListeners(){
  ['pipeline_length_m','pipeline_diameter_m','gas_density','friction_coefficient',
   'normal_pressure_bar','normal_flow_m3s','normal_temperature_c','normal_vibration',
   'pressure_min','pressure_max','flow_min','flow_max','fault_start_step','steps','step_seconds']
  .forEach(k => {
    const el = document.getElementById(`f-${k}`);
    if (!el) return;
    el.addEventListener('change', () => { G[k] = parseFloat(el.value); renderFooter(); saveState(); });
  });
  const fm = document.getElementById('f-fault_mode');
  if (fm) fm.addEventListener('change', () => { G.fault_mode = fm.value; renderFooter(); saveState(); });
}

// ── Footer ────────────────────────────────────────────────────────────────────
function renderFooter(){
  const bends  = nodes.filter(n => n.type === 'bend').reduce((s, n) => s + (n.props.count || 1), 0);
  const faults = nodes.filter(n => n.type.startsWith('fault_'));
  const el = document.getElementById('effective-length-tag');
  const bt = document.getElementById('bend-tag');
  const ft = document.getElementById('fault-tag');
  if (el) el.textContent = `Length: ${G.pipeline_length_m.toLocaleString()} m`;
  if (bt) bt.textContent = `Bends: ${bends}`;
  if (ft){
    const has = faults.length > 0 || G.fault_mode !== 'none';
    ft.style.display = has ? '' : 'none';
    if (has) ft.textContent = 'Fault active';
  }
}

// ── Run simulation ────────────────────────────────────────────────────────────
async function handleRunClick(){
  const txt = document.getElementById('run-status-txt');
  const hasLeakNode = nodes.some(n => n.type === 'fault_leak');
  const hasBlockageNode = nodes.some(n => n.type === 'fault_blockage');
  const hasAnyFaultNode = hasLeakNode || hasBlockageNode;

  // Prevent misleading runs: fault blocks on canvas but backend fault mode = none.
  // Canvas fault nodes are descriptive; runtime fault injection is controlled by fault_mode.
  if (hasAnyFaultNode && G.fault_mode === 'none'){
    showToast('Fault blocks are present, but Fault mode is set to "none". Select leak/blockage/sensor_drift first.');
    if (txt) txt.textContent = 'Set fault mode before running';
    return;
  }

  try {
    const r = await fetch('/api/system/status');
    const d = await r.json();
    if (d.state === 'running'){ showToast('Already running — go to Dashboard'); return; }
  } catch(e) {}

  if (txt) txt.textContent = 'Starting…';
  const body = {
    pipeline_cfg:    {...G},
    fault_mode:      G.fault_mode === 'none' ? null : G.fault_mode,
    fault_start_step:G.fault_start_step,
    steps:           G.steps,
    step_seconds:    G.step_seconds,
    scenario_name:   _activeScenarioName || 'Custom',
    pipeline_nodes:  nodes.map(n => ({ type:n.type, props:n.props })),
  };
  try {
    const res  = await fetch('/api/simulation/start', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.ok){
      showToast('Simulation started — switching to Dashboard');
      if (txt) txt.textContent = 'Running';
      setTimeout(() => { window.location.href = '/dashboard'; }, 800);
    } else {
      showToast(data.message || 'Failed to start');
      if (txt) txt.textContent = 'Error: ' + data.message;
    }
  } catch(e) {
    showToast('Network error: ' + e.message);
    if (txt) txt.textContent = 'Network error';
  }
}

// ── Export config.py ──────────────────────────────────────────────────────────
function exportConfig(){
  const bends = nodes.filter(n => n.type === 'bend').reduce((s, n) => s + (n.props.count || 1), 0);
  const txt = `# digital_twin/config.py — exported from Pipeline Engineer HMI
# Generated: ${new Date().toISOString()}

PIPELINE_LENGTH_M             = ${G.pipeline_length_m}
PIPELINE_DIAMETER_M           = ${G.pipeline_diameter_m}
GAS_DENSITY                   = ${G.gas_density}
NUM_BENDS                     = ${bends}
BEND_EQUIVALENT_LENGTH_FACTOR = 8

NORMAL_PRESSURE_BAR  = ${G.normal_pressure_bar}
NORMAL_FLOW_M3S      = ${G.normal_flow_m3s}
NORMAL_TEMPERATURE_C = ${G.normal_temperature_c}
NORMAL_VIBRATION     = ${G.normal_vibration}

PRESSURE_MIN = ${G.pressure_min}
PRESSURE_MAX = ${G.pressure_max}
FLOW_MIN     = ${G.flow_min}
FLOW_MAX     = ${G.flow_max}

TIME_STEP_SECONDS    = ${G.step_seconds}
TOTAL_STEPS          = ${G.steps}
FRICTION_COEFFICIENT = ${G.friction_coefficient}
`;
  dlText(txt, 'config.py');
}

// ── Save / Load pipeline JSON ─────────────────────────────────────────────────
function savePipeline(){
  dlText(
    JSON.stringify({ nodes, globalConfig:G, savedAt:new Date().toISOString() }, null, 2),
    'pipeline_config.json'
  );
  showToast('Pipeline saved as pipeline_config.json');
}

function loadPipelineFile(){
  const inp = document.createElement('input');
  inp.type = 'file'; inp.accept = '.json';
  inp.onchange = e => {
    const file = e.target.files[0]; if (!file) return;
    const fr   = new FileReader();
    fr.onload  = ev => {
      try {
        const data = JSON.parse(ev.target.result);
        if (data.nodes){
          nodes = data.nodes;
          if (data.globalConfig) Object.assign(G, data.globalConfig);
          _ctrs = {}; selectedId = null;
          render();
          showToast('Pipeline loaded');
        }
      } catch(err){ showToast('Load error: ' + err.message); }
    };
    fr.readAsText(file);
  };
  inp.click();
}

function dlText(text, filename){
  const a = Object.assign(document.createElement('a'), {
    href:     URL.createObjectURL(new Blob([text], {type:'text/plain'})),
    download: filename,
  });
  a.click();
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(msg){
  let t = document.getElementById('eng-toast');
  if (!t){
    t = document.createElement('div');
    t.id = 'eng-toast';
    t.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);'
      + 'background:var(--bg4);border:1px solid var(--borderem);color:var(--t0);'
      + 'padding:8px 18px;border-radius:6px;font-size:12px;z-index:9999;'
      + 'pointer-events:none;opacity:0;transition:opacity .2s;'
      + 'white-space:nowrap;max-width:80vw;text-align:center';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.style.opacity = '1';
  clearTimeout(t._t);
  t._t = setTimeout(() => { t.style.opacity = '0'; }, 2800);
}

// ── Template dropdown init ────────────────────────────────────────────────────
function initTemplateDropdown(){
  const sel = document.getElementById('template-select');
  if (!sel) return;
  Object.entries(TEMPLATES).forEach(([k, v]) => {
    const o = document.createElement('option');
    o.value = k; o.textContent = v.name;
    sel.appendChild(o);
  });
  sel.addEventListener('change', () => {
    if (!sel.value) return;
    _activeScenarioKey  = sel.value;
    _activeScenarioName = TEMPLATES[sel.value]?.name || sel.value;
    loadTemplate(sel.value);
  });
}

// ── Active scenario tracking ──────────────────────────────────────────────────
let _activeScenarioName = 'Normal Pipeline';
let _activeScenarioKey  = 'normal';

// ── Boot ──────────────────────────────────────────────────────────────────────
// Priority:
//   1. sessionStorage saved state → restore canvas as-is (user's custom layout)
//   2. Running simulation → sync template dropdown to match the running scenario
//   3. Fresh start (no saved state, no running sim) → load default normal template
//
async function boot(){
  initTemplateDropdown();

  // Step 1: restore saved canvas if it exists
  const hadSaved = loadSavedState();

  if (hadSaved){
    // Render the restored canvas immediately so the user sees their layout
    render();
    // Sync the template dropdown to the saved scenario key
    const sel = document.getElementById('template-select');
    if (sel) sel.value = _activeScenarioKey;
  }

  // Step 2: check backend state (non-blocking — don't wipe canvas if already restored)
  try {
    const res    = await fetch('/api/system/status');
    const status = await res.json();

    if (status.state === 'running' || status.state === 'stopping'){
      const scenarioName = status.scenario_name || '';
      const matchKey = Object.entries(TEMPLATES)
        .find(([, v]) => v.name === scenarioName)?.[0];

      if (matchKey){
        // Update dropdown to show running scenario
        const sel = document.getElementById('template-select');
        if (sel) sel.value = matchKey;

        // Only load the template onto the canvas if we had no saved state
        // (don't overwrite custom layouts the user may have built)
        if (!hadSaved){
          _activeScenarioKey  = matchKey;
          _activeScenarioName = scenarioName;
          loadTemplate(matchKey);
        } else {
          _activeScenarioName = scenarioName;
        }
      } else if (!hadSaved){
        loadTemplate('normal');
      }

      // Change run button to go-to-dashboard
      const runBtn = document.getElementById('run-btn');
      if (runBtn){
        runBtn.textContent = '▶ Go to Dashboard';
        runBtn.onclick = () => { window.location.href = '/dashboard'; };
      }

      const pct       = Math.round((status.step / Math.max(status.total_steps, 1)) * 100);
      const faultInfo = status.fault_mode !== 'none'
        ? ` · ${status.fault_mode}${status.fault_active ? ' ACTIVE' : ` starts @${status.fault_start_step}`}`
        : '';
      showToast(`Simulation running: "${scenarioName}" ${pct}%${faultInfo}`);

    } else {
      // Idle — if nothing was saved, load the normal template as default
      if (!hadSaved){
        loadTemplate('normal');
      }
    }
  } catch(e){
    if (!hadSaved) loadTemplate('normal');
  }
}

boot();
