#!/usr/bin/env python3
"""
cortical_browser.py — Production NiiVue cortical browser.

Three surface panels (LH lateral, RH lateral, Asymmetry index on LH geometry),
three orthoslice panels with surface contours, three depth-profile charts.
CLim and colormap controls for both data and asymmetry surfaces.

Usage:
    python cortical_browser.py [subjects_dir] [subj_id] [--port PORT]
"""
import os, sys, glob, json, time, threading, webbrowser, argparse, tempfile
import numpy as np
import nibabel as nib

sys.path.insert(0, os.path.dirname(__file__))
from cortical_io import read_mrtrix_tsf, pad_to_matrix
from http.server import HTTPServer, BaseHTTPRequestHandler

TEMPLATE        = 'ico6_sym'
STEP_MM         = 0.5
NIIVUE_CDN      = 'https://cdn.jsdelivr.net/npm/@niivue/niivue/dist/index.js'
CHARTJS_CDN     = 'https://cdn.jsdelivr.net/npm/chart.js/dist/chart.umd.min.js'
CHARTJS_ANN_CDN = ('https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3'
                   '/dist/chartjs-plugin-annotation.min.js')

# ── HTML template ──────────────────────────────────────────────────────────────
_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Cortical Browser — __SUBJ_ID__</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #1f1f1f; color: #ccc;
  font: 11px/1.4 -apple-system, "Segoe UI", Arial, sans-serif;
  display: flex; flex-direction: column; height: 100vh; overflow: hidden;
}
header {
  background: #2b2b2b; border-bottom: 1px solid #444444;
  padding: 3px 8px; display: flex; align-items: center;
  gap: 6px; flex-shrink: 0; flex-wrap: wrap;
}
.subj { font-weight: bold; color: #f0f0f0; font-size: 12px; white-space: nowrap; }
.glab { color: #d1d1d1; font-size: 10px; white-space: nowrap; }
label { display: flex; align-items: center; gap: 3px; white-space: nowrap; color: #999; }
select {
  background: #d9d9d9; color: #1a1a1a; border: 1px solid #4d4d4d;
  border-radius: 3px; padding: 1px 3px; font-size: 10px;
}
input[type=range] {
  width: 60px; cursor: pointer; accent-color: #8a8a8a;
}
input[type=checkbox] { cursor: pointer; accent-color: #8a8a8a; }
input[type=number] {
  background: #d9d9d9; color: #1a1a1a; border: 1px solid #4d4d4d;
  border-radius: 3px; padding: 1px 4px; font-size: 10px; width: 58px;
  -moz-appearance: textfield;
}
input[type=number]::-webkit-inner-spin-button,
input[type=number]::-webkit-outer-spin-button { display: none; }
button.cbtn {
  background: #3a3a3a; color: #ddd; border: 1px solid #555555;
  border-radius: 3px; padding: 1px 6px; font-size: 10px; cursor: pointer;
}
button.cbtn:hover { background: #484848; }
#depth-label { color: #d1d1d1; min-width: 40px; }
#pos-display  { color: #999999; font-size: 10px; white-space: nowrap; overflow: hidden; max-width: 200px; }
#vtx-display  {
  color: #f5c842; font-size: 11px; font-family: monospace; font-weight: bold;
  background: #262626; border: 1px solid #f5c842; border-radius: 3px;
  padding: 1px 7px; margin-left: auto; white-space: nowrap; min-width: 76px;
  text-align: center;
}
.sep { border-left: 1px solid #444444; height: 14px; flex-shrink: 0; }
#grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  grid-template-rows: 1fr 1fr 1fr;
  flex: 1; gap: 2px; background: #0a0a0a; overflow: hidden;
}
.cell { position: relative; overflow: hidden; background: #141414; }
canvas.nv-canvas { display: block; width: 100% !important; height: 100% !important; }
.clabel {
  position: absolute; top: 4px; left: 6px; z-index: 10;
  font-size: 9px; letter-spacing: 0.4px; text-transform: uppercase;
  color: #999999; background: rgba(0,0,0,0.55);
  padding: 1px 5px; border-radius: 3px; pointer-events: none;
}
.cell-span3 { grid-column: 1 / -1; }
.plot-cell { display: flex; flex-direction: column; padding: 20px 5px 4px; }
.chart-wrap { position: relative; flex: 1; min-height: 0; background: #242424; }
.cbar {
  position: absolute; bottom: 5px; left: 10px; right: 10px; z-index: 10; pointer-events: none;
}
.cbar-g {
  height: 8px; border-radius: 2px; border: 1px solid rgba(255,255,255,0.08);
}
.cbar-ll {
  display: flex; justify-content: space-between;
  font-size: 9px; color: #999999; margin-top: 2px; font-family: monospace;
}
</style>
</head>
<body>

<header>
  <span class="subj">__SUBJ_ID__</span>
  <div class="sep"></div>

  <label>Metric <select id="metricSel">__METRIC_OPTIONS__</select></label>
  <label>Depth
    <input type="range" id="depthSlider" min="0" max="__MAX_DEPTH__" value="__INIT_DEPTH__">
    <span id="depth-label">__INIT_DEPTH_MM__ mm</span>
  </label>
  <div class="sep"></div>

  <span class="glab">Data</span>
  <input type="number" id="climMin" step="0.001" title="Color min">
  <span style="color:#999999">–</span>
  <input type="number" id="climMax" step="0.001" title="Color max">
  <button class="cbtn" id="climAuto">Auto</button>
  <select id="cmapSel">
    <option value="viridis">viridis</option>
    <option value="hot">hot</option>
    <option value="inferno">inferno</option>
    <option value="plasma">plasma</option>
    <option value="magma">magma</option>
    <option value="cividis">cividis</option>
    <option value="thermal">thermal</option>
    <option value="batlow">batlow</option>
    <option value="cool">cool</option>
    <option value="warm">warm</option>
    <option value="gray">gray</option>
    <option value="bone">bone</option>
    <option value="copper">copper</option>
    <option value="jet">jet</option>
  </select>
  <label><input type="checkbox" id="cmapInv"> Inv</label>
  <label>Ov <input type="range" id="ovOp" min="0" max="100" value="80"></label>
  <div class="sep"></div>

  <span class="glab">Asym</span>
  <input type="number" id="asymMin" step="0.001" title="Asym color min">
  <span style="color:#999999">–</span>
  <input type="number" id="asymMax" step="0.001" title="Asym color max">
  <button class="cbtn" id="asymAuto">Auto</button>
  <select id="cmapAsymSel">
    <option value="bwr">blue-white-red</option>
    <option value="cwr">cyan-white-red</option>
    <option value="gwr">green-white-red</option>
    <option value="blue2red">blue2red (hue)</option>
    <option value="blue2magenta">blue2magenta</option>
    <option value="hsv">hsv</option>
    <option value="jet">jet</option>
  </select>
  <label><input type="checkbox" id="cmapAsymInv"> Inv</label>
  <div class="sep"></div>

  <label>Shader <select id="shaderSel">
    <option value="Bright Matte">Bright Matte</option>
    <option value="Matte">Matte</option>
    <option value="Hemi">Hemi</option>
    <option value="Phong">Phong</option>
  </select></label>
  <div class="sep"></div>

  <label><input type="checkbox" id="radioConv" checked> Rad</label>
  <label><input type="checkbox" id="crosshairChk" checked> X-hair</label>
  <label><input type="checkbox" id="surfOnSlicesChk" checked> Surf on slices</label>
  <label>Vertex <input type="number" id="vtxInput" min="0" step="1" title="Jump to vertex ID"></label>
  <span id="pos-display"></span>
  <span id="vtx-display">v — —</span>
</header>

<div id="grid">
  <!-- Row 1: surface 3-D renders -->
  <div class="cell">
    <canvas id="gl-lh" class="nv-canvas"></canvas>
    <span class="clabel">LH lateral</span>
    <div class="cbar">
      <div class="cbar-g" id="cbgrad-lh"></div>
      <div class="cbar-ll"><span id="cblbl-lh-min">0</span><span id="cblbl-lh-max">1</span></div>
    </div>
  </div>
  <div class="cell">
    <canvas id="gl-rh" class="nv-canvas"></canvas>
    <span class="clabel">RH lateral</span>
    <div class="cbar">
      <div class="cbar-g" id="cbgrad-rh"></div>
      <div class="cbar-ll"><span id="cblbl-rh-min">0</span><span id="cblbl-rh-max">1</span></div>
    </div>
  </div>
  <div class="cell">
    <canvas id="gl-asym" class="nv-canvas"></canvas>
    <span class="clabel">Asymmetry index (LH geom)</span>
    <div class="cbar">
      <div class="cbar-g" id="cbgrad-asym"></div>
      <div class="cbar-ll"><span id="cblbl-asym-min">-1</span><span id="cblbl-asym-max">1</span></div>
    </div>
  </div>

  <!-- Row 2: single multiplanar orthoslice (row layout = axial/coronal/sagittal side by side) -->
  <div class="cell cell-span3">
    <canvas id="gl-slices" class="nv-canvas"></canvas>
  </div>

  <!-- Row 3: depth-profile charts -->
  <div class="cell plot-cell">
    <span class="clabel">LH depth profile</span>
    <div class="chart-wrap"><canvas id="chart-lh"></canvas></div>
  </div>
  <div class="cell plot-cell">
    <span class="clabel">RH depth profile</span>
    <div class="chart-wrap"><canvas id="chart-rh"></canvas></div>
  </div>
  <div class="cell plot-cell">
    <span class="clabel">Asymmetry profile</span>
    <div class="chart-wrap"><canvas id="chart-asym"></canvas></div>
  </div>
</div>

<script src="__CHARTJS_CDN__"></script>
<script src="__CHARTJS_ANN_CDN__"></script>
<script type="module">
import * as niivue from "__NIIVUE_CDN__"

// ── injected by Python ────────────────────────────────────────────────────────
const VOLUMES  = __VOLUMES_JSON__
const SURFS    = __SURFS_JSON__
const METRICS  = __METRICS_JSON__
const BASE_URL = "__BASE_URL__"
const TEMPLATE = "__TEMPLATE__"
const STEP_MM  = __STEP_MM__

// ── app state ─────────────────────────────────────────────────────────────────
let currentMetric  = Object.keys(METRICS)[0] || null
let currentCmap    = 'viridis'
let currentCmapAsym = 'bwr'
let dataInvert     = false
let asymInvert     = false
let layerOpacity   = 1.0
let currentShader  = 'Bright Matte'
let currentDepth   = 0
let currentClimMin = 0, currentClimMax = 1
let currentAsymMin = -1, currentAsymMax = 1
let showSurfOnSlices = true
const markerMeshes = new Map()   // nv instance -> its vertex-marker connectome mesh

// Hoisted so updateDepthMarker is safe to call before makeChart runs
var chartLH, chartRH, chartAsym

const firstInfo = currentMetric ? METRICS[currentMetric] : null
if (firstInfo) {
  currentDepth   = Math.floor((firstInfo.n_depths - 1) / 2)
  currentClimMin = firstInfo.cal_min;  currentClimMax = firstInfo.cal_max
  currentAsymMin = firstInfo.cal_min_asym
  currentAsymMax = firstInfo.cal_max_asym
}

const LH_SURF = SURFS.find(s => s.hemi === 'lh') || null
const RH_SURF = SURFS.find(s => s.hemi === 'rh') || null
const VOL_URL = VOLUMES.length ? VOLUMES[0].url : null

// ── NiiVue instances ──────────────────────────────────────────────────────────
const SURF_CFG = { backColor: [0.06, 0.06, 0.06, 1], show3Dcrosshair: false }
const SLIC_CFG = {
  backColor: [0.04, 0.04, 0.04, 1], show3Dcrosshair: true,
  meshThicknessOn2D: 2, multiplanarLayout: 'row'
}

const nvLhL   = new niivue.Niivue(SURF_CFG)
const nvRhL   = new niivue.Niivue(SURF_CFG)
const nvAsym  = new niivue.Niivue(SURF_CFG)
const nvSlices = new niivue.Niivue(SLIC_CFG)

await new Promise(r => requestAnimationFrame(r))
await Promise.all([
  nvLhL.attachTo('gl-lh'),   nvRhL.attachTo('gl-rh'),
  nvAsym.attachTo('gl-asym'),
  nvSlices.attachTo('gl-slices'),
])

// ── custom diverging colormaps ────────────────────────────────────────────────
function buildDivergingCmap(r0, g0, b0, r1, g1, b1) {
  const R = [], G = [], B = [], A = []
  for (let i = 0; i < 256; i++) {
    const t = i / 255
    if (t <= 0.5) {
      const s = t * 2
      R.push(Math.round(r0 + s * (255 - r0)))
      G.push(Math.round(g0 + s * (255 - g0)))
      B.push(Math.round(b0 + s * (255 - b0)))
    } else {
      const s = (t - 0.5) * 2
      R.push(Math.round(255 - s * (255 - r1)))
      G.push(Math.round(255 - s * (255 - g1)))
      B.push(Math.round(255 - s * (255 - b1)))
    }
    A.push(255)
  }
  return { R, G, B, A }
}
const CUSTOM_CMAPS = {
  bwr:  buildDivergingCmap(  0,   0, 255, 255,   0,   0),  // blue-white-red
  gwr:  buildDivergingCmap(  0, 180,   0, 255,   0,   0),  // green-white-red
  cwr:  buildDivergingCmap(  0, 200, 200, 255,   0,   0),  // cyan-white-red
}
for (const nv of [nvLhL, nvRhL, nvAsym, nvSlices]) {
  for (const [name, cmap] of Object.entries(CUSTOM_CMAPS)) {
    try {
      nv.addColormap(name, cmap)
      console.log(`[cmap] registered '${name}' OK (canvas=${nv.canvas?.id})`)
    } catch(e) {
      console.warn(`[cmap] addColormap('${name}') FAILED:`, e.message)
    }
  }
}

// ── custom "Bright Matte" shader ──────────────────────────────────────────────
const BRIGHT_MATTE_FRAG = `#version 300 es
precision highp float;
uniform float opacity;
in vec4 vClr; in vec3 vN;
out vec4 color;
void main() {
  vec3 n  = normalize(vN);
  vec3 l1 = normalize(vec3(0.0,  10.0, -5.0));
  vec3 l2 = normalize(vec3(0.0,  -5.0,  5.0));
  vec3 c  = vClr.rgb * 0.45
           + max(dot(n,l1),0.0) * vClr.rgb * 0.70
           + max(dot(n,l2),0.0) * vClr.rgb * 0.18;
  color = vec4(clamp(c,0.0,1.0), opacity);
}`

for (const nv of [nvLhL, nvRhL, nvAsym]) {
  try { if (typeof nv.addMeshShader === 'function') nv.addMeshShader('Bright Matte', BRIGHT_MATTE_FRAG) }
  catch(e) {}
}

function applyShader(nv, name) {
  if (!nv.meshShaders) return
  let idx = nv.meshShaders.findIndex(s => s.Name === name)
  if (idx < 0) idx = nv.meshShaders.findIndex(s => s.Name === 'Matte')
  if (idx < 0) return
  for (const m of nv.meshes) nv.setMeshShader(m.id, idx)
}
function applyCurrentShader() {
  for (const nv of [nvLhL, nvRhL, nvAsym]) applyShader(nv, currentShader)
}

// ── camera helper ─────────────────────────────────────────────────────────────
function setCam(nv, az, el) {
  nv.scene.renderAzimuth = az; nv.scene.renderElevation = el; nv.drawScene()
}

// ── surface loading ───────────────────────────────────────────────────────────
async function loadAllSurfaces(metric, resetCamera = false) {
  markerMeshes.clear()   // loadMeshes() below replaces each instance's mesh list, wiping any marker sphere
  const info = metric ? METRICS[metric] : null

  function layerData(hemi) {
    if (!info) return []
    return [{ url: `${BASE_URL}/${hemi}_${TEMPLATE}_${metric}.func.gii`,
              colormap: currentCmap, colormapInvert: dataInvert,
              opacity: layerOpacity, cal_min: currentClimMin, cal_max: currentClimMax }]
  }
  function layerAsym() {
    if (!info) return []
    const layer = { url: `${BASE_URL}/asym_${TEMPLATE}_${metric}.func.gii`,
                    colormap: currentCmapAsym, colormapInvert: asymInvert,
                    opacity: layerOpacity, cal_min: currentAsymMin, cal_max: currentAsymMax }
    console.log('[layerAsym] loading:', JSON.stringify(layer))
    return [layer]
  }

  const proms = []
  if (LH_SURF) {
    proms.push(nvLhL.loadMeshes( [{ url: LH_SURF.url, rgba255: LH_SURF.rgba255, layers: layerData('lh') }]))
    proms.push(nvAsym.loadMeshes([{ url: LH_SURF.url, rgba255: LH_SURF.rgba255, layers: layerAsym() }]))
  }
  if (RH_SURF)
    proms.push(nvRhL.loadMeshes([{ url: RH_SURF.url, rgba255: RH_SURF.rgba255, layers: layerData('rh') }]))

  // Orthoslice contours (geometry only, no scalar overlay)
  const sliceMeshes = []
  if (LH_SURF) sliceMeshes.push({ url: LH_SURF.url, rgba255: LH_SURF.rgba255 })
  if (RH_SURF) sliceMeshes.push({ url: RH_SURF.url, rgba255: RH_SURF.rgba255 })
  if (sliceMeshes.length)
    proms.push(nvSlices.loadMeshes([...sliceMeshes]))

  await Promise.all(proms)
  applyCurrentShader()
  applySliceMeshVisibility()
  if (resetCamera) {
    setCam(nvLhL,   90, 15)   // LH lateral
    setCam(nvRhL,  270, 15)   // RH lateral
    setCam(nvAsym,  90, 15)   // Asymmetry (LH geometry, lateral view)
  }

  // Diagnostic: confirm what NiiVue actually loaded on the asym surface
  const _am = nvAsym.meshes[0]
  if (_am) {
    const _l = _am.layers?.[0]
    console.log('[nvAsym] layers:', _am.layers?.length,
                '| colormap:', _l?.colormap,
                '| cal_min:', _l?.cal_min, '| cal_max:', _l?.cal_max,
                '| url:', _l?.url)
  } else {
    console.warn('[nvAsym] no meshes loaded')
  }
}

// ── matrix cache ──────────────────────────────────────────────────────────────
const matCache = {}

async function ensureMatrix(hemi, metric) {
  const key = `${hemi}_${metric}`
  if (matCache[key]) return matCache[key]
  const r = await fetch(`${BASE_URL}/${hemi}_${TEMPLATE}_${metric}_matrix.f32`)
  matCache[key] = new Float32Array(await r.arrayBuffer())
  return matCache[key]
}

async function loadMatrices(metric) {
  await Promise.all([
    ensureMatrix('lh',   metric),
    ensureMatrix('rh',   metric),
    ensureMatrix('asym', metric),
  ])
}

// ── initial load ──────────────────────────────────────────────────────────────
await Promise.all([
  VOL_URL
    ? nvSlices.loadVolumes([{ url: VOL_URL, colormap: 'gray', opacity: 1 }])
    : Promise.resolve(),
  currentMetric ? loadAllSurfaces(currentMetric, true) : Promise.resolve(),
  currentMetric ? loadMatrices(currentMetric)    : Promise.resolve(),
])

// ── slice setup (single multiplanar instance) ─────────────────────────────────
nvSlices.opts.onLocationChange = d => {
  document.getElementById('pos-display').textContent = d.string
}
nvSlices.setSliceType(nvSlices.sliceTypeMultiplanar)
nvSlices.setRadiologicalConvention(true)

// ── depth control ─────────────────────────────────────────────────────────────
function setDepth(d) {
  currentDepth = d
  const mm = d * STEP_MM
  document.getElementById('depth-label').textContent = `${mm.toFixed(1)} mm`
  for (const nv of [nvLhL, nvRhL, nvAsym])
    for (const mesh of nv.meshes)
      if (mesh.layers?.length) nv.setMeshLayerProperty(mesh.id, 0, 'frame4D', d)
  updateDepthMarker(mm)
}

document.getElementById('depthSlider').oninput = e => setDepth(+e.target.value)

// ── CLim helpers ──────────────────────────────────────────────────────────────
function setDataCLim(mn, mx) {
  currentClimMin = mn; currentClimMax = mx
  for (const nv of [nvLhL, nvRhL])
    for (const mesh of nv.meshes)
      if (mesh.layers?.length) {
        nv.setMeshLayerProperty(mesh.id, 0, 'cal_min', mn)
        nv.setMeshLayerProperty(mesh.id, 0, 'cal_max', mx)
      }
  refreshColorbars()
}

function setAsymCLim(mn, mx) {
  currentAsymMin = mn; currentAsymMax = mx
  for (const mesh of nvAsym.meshes)
    if (mesh.layers?.length) {
      nvAsym.setMeshLayerProperty(mesh.id, 0, 'cal_min', mn)
      nvAsym.setMeshLayerProperty(mesh.id, 0, 'cal_max', mx)
    }
  refreshColorbars()
}

function setDataCmap(cmap, invert) {
  currentCmap = cmap; dataInvert = invert
  for (const nv of [nvLhL, nvRhL])
    for (const mesh of nv.meshes)
      if (mesh.layers?.length) {
        nv.setMeshLayerProperty(mesh.id, 0, 'colormap', cmap)
        nv.setMeshLayerProperty(mesh.id, 0, 'colormapInvert', invert)
      }
  refreshColorbars()
}

function setAsymCmap(cmap, invert) {
  currentCmapAsym = cmap; asymInvert = invert
  for (const mesh of nvAsym.meshes)
    if (mesh.layers?.length) {
      nvAsym.setMeshLayerProperty(mesh.id, 0, 'colormap', cmap)
      nvAsym.setMeshLayerProperty(mesh.id, 0, 'colormapInvert', invert)
    }
  refreshColorbars()
}

function setLayerOpacity(op) {
  layerOpacity = op
  for (const nv of [nvLhL, nvRhL, nvAsym])
    for (const mesh of nv.meshes)
      if (mesh.layers?.length) nv.setMeshLayerProperty(mesh.id, 0, 'opacity', op)
}

// ── colorbars ─────────────────────────────────────────────────────────────────
const CMAP_CSS = {
  hot:       '#000 0%,#900 30%,#f00 55%,#ff0 80%,#fff 100%',
  inferno:   '#000 0%,#3b0f70 20%,#8c2981 40%,#dd4968 60%,#fb9a06 80%,#fcffa4 100%',
  plasma:    '#0d0887 0%,#6a00a8 25%,#b12a90 50%,#e16462 75%,#fca636 100%',
  viridis:   '#440154 0%,#31688e 33%,#35b779 67%,#fde725 100%',
  magma:     '#000 0%,#51127c 25%,#b73779 50%,#fd9567 75%,#fbfdbf 100%',
  cividis:   '#00204c 0%,#4a5569 33%,#8a8e73 67%,#dde318 100%',
  thermal:   '#042333 0%,#2c3f6a 25%,#7c4e80 50%,#d45e53 75%,#fde735 100%',
  batlow:    '#011959 0%,#1c5769 25%,#4c8a67 50%,#c08253 75%,#fad7c0 100%',
  cool:      '#0ff 0%,#f0f 100%',
  warm:      '#6e40aa 0%,#ff5e63 50%,#aff05b 100%',
  gray:      '#000 0%,#fff 100%',
  bone:      '#000 0%,#556677 50%,#fff 100%',
  copper:    '#000 0%,#c87941 50%,#ffb07a 100%',
  jet:       '#00f 0%,#0ff 25%,#0f0 50%,#ff0 75%,#f00 100%',
  bwr:       '#00f 0%,#fff 50%,#f00 100%',
  cwr:       '#0cc 0%,#fff 50%,#f00 100%',
  gwr:       '#0b4 0%,#fff 50%,#f00 100%',
  blue2red:  '#00f 0%,#0ff 25%,#0f0 50%,#ff0 75%,#f00 100%',
  blue2magenta: '#00f 0%,#fff 50%,#f0f 100%',
  hsv:       '#f00 0%,#ff0 17%,#0f0 33%,#0ff 50%,#00f 67%,#f0f 83%,#f00 100%',
}

function cmapCss(name, invert) {
  const stops = CMAP_CSS[name] || '#333 0%,#ccc 100%'
  return `linear-gradient(to ${invert ? 'left' : 'right'}, ${stops})`
}

function refreshColorbars() {
  const fmt = v => parseFloat(v).toPrecision(4)
  const pairs = [
    ['lh',   currentCmap,     dataInvert, currentClimMin, currentClimMax],
    ['rh',   currentCmap,     dataInvert, currentClimMin, currentClimMax],
    ['asym', currentCmapAsym, asymInvert, currentAsymMin, currentAsymMax],
  ]
  for (const [id, cmap, inv, mn, mx] of pairs) {
    const g = document.getElementById(`cbgrad-${id}`)
    const l = document.getElementById(`cblbl-${id}-min`)
    const r = document.getElementById(`cblbl-${id}-max`)
    if (g) g.style.background = cmapCss(cmap, inv)
    if (l) l.textContent = fmt(mn)
    if (r) r.textContent = fmt(mx)
  }
}

// ── CLim input fields initialisation ─────────────────────────────────────────
const climMinEl  = document.getElementById('climMin')
const climMaxEl  = document.getElementById('climMax')
const asymMinEl  = document.getElementById('asymMin')
const asymMaxEl  = document.getElementById('asymMax')

function initClimInputs(info) {
  climMinEl.value = info.cal_min.toFixed(4)
  climMaxEl.value = info.cal_max.toFixed(4)
  asymMinEl.value = info.cal_min_asym.toFixed(4)
  asymMaxEl.value = info.cal_max_asym.toFixed(4)
  currentClimMin = info.cal_min; currentClimMax = info.cal_max
  currentAsymMin = info.cal_min_asym; currentAsymMax = info.cal_max_asym
  refreshColorbars()
}

if (firstInfo) initClimInputs(firstInfo)

function onDataClimChange() {
  const mn = parseFloat(climMinEl.value), mx = parseFloat(climMaxEl.value)
  if (isFinite(mn) && isFinite(mx) && mn < mx) setDataCLim(mn, mx)
}
climMinEl.addEventListener('change', onDataClimChange)
climMaxEl.addEventListener('change', onDataClimChange)

function onAsymClimChange() {
  const mn = parseFloat(asymMinEl.value), mx = parseFloat(asymMaxEl.value)
  if (isFinite(mn) && isFinite(mx) && mn < mx) setAsymCLim(mn, mx)
}
asymMinEl.addEventListener('change', onAsymClimChange)
asymMaxEl.addEventListener('change', onAsymClimChange)

document.getElementById('climAuto').addEventListener('click', () => {
  if (!currentMetric) return
  const info = METRICS[currentMetric]
  climMinEl.value = info.cal_min.toFixed(4)
  climMaxEl.value = info.cal_max.toFixed(4)
  setDataCLim(info.cal_min, info.cal_max)
})
document.getElementById('asymAuto').addEventListener('click', () => {
  if (!currentMetric) return
  const info = METRICS[currentMetric]
  asymMinEl.value = info.cal_min_asym.toFixed(4)
  asymMaxEl.value = info.cal_max_asym.toFixed(4)
  setAsymCLim(info.cal_min_asym, info.cal_max_asym)
})

// ── colormap / invert controls ────────────────────────────────────────────────
document.getElementById('cmapSel').addEventListener('change', e =>
  setDataCmap(e.target.value, dataInvert))
document.getElementById('cmapInv').addEventListener('change', e =>
  setDataCmap(currentCmap, e.target.checked))

document.getElementById('cmapAsymSel').addEventListener('change', e =>
  setAsymCmap(e.target.value, asymInvert))
document.getElementById('cmapAsymInv').addEventListener('change', e =>
  setAsymCmap(currentCmapAsym, e.target.checked))

// ── overlay opacity slider ────────────────────────────────────────────────────
document.getElementById('ovOp').oninput  = e => setLayerOpacity(+e.target.value / 100)

// ── surface-on-orthoslice overlay toggle ─────────────────────────────────────
function applySliceMeshVisibility() {
  for (const m of nvSlices.meshes) nvSlices.setMeshProperty(m.id, 'opacity', showSurfOnSlices ? 1 : 0)
  nvSlices.drawScene()
}
document.getElementById('surfOnSlicesChk').addEventListener('change', function() {
  showSurfOnSlices = this.checked
  applySliceMeshVisibility()
})

// ── shader selector ───────────────────────────────────────────────────────────
document.getElementById('shaderSel').addEventListener('change', e => {
  currentShader = e.target.value; applyCurrentShader()
})

// ── radiological / crosshair ──────────────────────────────────────────────────
document.getElementById('radioConv').addEventListener('change', function() {
  nvSlices.setRadiologicalConvention(this.checked)
})
document.getElementById('crosshairChk').addEventListener('change', function() {
  nvSlices.opts.show3Dcrosshair = this.checked; nvSlices.drawScene()
})

// ── metric selector ───────────────────────────────────────────────────────────
document.getElementById('metricSel').addEventListener('change', async e => {
  currentMetric = e.target.value
  const info = METRICS[currentMetric]
  initClimInputs(info)

  const nd = info.n_depths
  const sl = document.getElementById('depthSlider')
  sl.max = nd - 1
  currentDepth = Math.floor((nd - 1) / 2)
  sl.value = currentDepth

  await Promise.all([loadAllSurfaces(currentMetric), loadMatrices(currentMetric)])
  setDepth(currentDepth)
  document.getElementById('vtx-display').textContent = 'v — —'
  document.getElementById('pos-display').textContent = ''
  for (const chart of [chartLH, chartRH, chartAsym]) {
    chart.data.datasets[0].data = []; chart.update('none')
  }
})

// ── initial depth + colorbars ─────────────────────────────────────────────────
setDepth(currentDepth)
refreshColorbars()

// ── surface vertex picking ────────────────────────────────────────────────────
// Mirrors NiiVue's own SceneRenderer.calculateMvpMatrix exactly (orthographic
// projection): modelMatrix = MirrorX * Rx(270-elevation) * Rz(azimuth-180) *
// T(-pivot3D). Rather than re-deriving a camera position/FOV, every triangle is
// pushed through that same transform and rasterized in software (point-in-
// triangle + depth compare), matching what the GPU's own depth buffer would do.
function meshBounds(pts) {
  const n=pts.length/3; let cx=0,cy=0,cz=0
  for(let i=0;i<n;i++){cx+=pts[i*3];cy+=pts[i*3+1];cz+=pts[i*3+2]}
  const c=[cx/n,cy/n,cz/n]; let r=0
  for(let i=0;i<n;i++){const dx=pts[i*3]-c[0],dy=pts[i*3+1]-c[1],dz=pts[i*3+2]-c[2];r=Math.max(r,dx*dx+dy*dy+dz*dz)}
  return {center:c, radius:Math.sqrt(r)}
}

// Software rasterization pick: project every triangle to screen space, keep
// only those whose 2D shape actually contains the click, and among those
// take the one nearest the camera via barycentric-interpolated depth — this
// is the same test a GPU depth buffer performs, so it respects occlusion
// (a vertex on the far side of the head can no longer "win" just because it
// projects near the click point).
function pickTriangle(mesh, origin, azimuthDeg, elevationDeg, scale, whratio, ndcX, ndcY) {
  const thetaZ = (azimuthDeg - 180) * Math.PI / 180
  const thetaX = (270 - elevationDeg) * Math.PI / 180
  const cz = Math.cos(thetaZ), sz = Math.sin(thetaZ)
  const cx = Math.cos(thetaX), sx = Math.sin(thetaX)
  const pts = mesh.pts
  const n = pts.length / 3

  const sxArr = new Float32Array(n), syArr = new Float32Array(n), szArr = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const x0 = pts[i*3]   - origin[0]
    const y0 = pts[i*3+1] - origin[1]
    const z0 = pts[i*3+2] - origin[2]
    const x1 = x0*cz - y0*sz
    const y1 = x0*sz + y0*cz
    const y2 = y1*cx - z0*sx
    const z2 = y1*sx + z0*cx   // view-space depth: larger = nearer the camera
    const mx = -x1             // mirror X
    sxArr[i] = whratio < 1 ? mx / scale          : mx / (scale * whratio)
    syArr[i] = whratio < 1 ? y2 * whratio / scale : y2 / scale
    szArr[i] = z2
  }

  const tris = mesh.tris
  let bestDepth = Infinity, bestVert = -1
  for (let t = 0; t < tris.length; t += 3) {
    const i0 = tris[t], i1 = tris[t+1], i2 = tris[t+2]
    const x0 = sxArr[i0], y0 = syArr[i0]
    const x1 = sxArr[i1], y1 = syArr[i1]
    const x2 = sxArr[i2], y2v = syArr[i2]
    const denom = (y1 - y2v) * (x0 - x2) + (x2 - x1) * (y0 - y2v)
    if (Math.abs(denom) < 1e-12) continue
    const w0 = ((y1 - y2v) * (ndcX - x2) + (x2 - x1) * (ndcY - y2v)) / denom
    const w1 = ((y2v - y0) * (ndcX - x2) + (x0 - x2) * (ndcY - y2v)) / denom
    const w2 = 1 - w0 - w1
    if (w0 < -1e-6 || w1 < -1e-6 || w2 < -1e-6) continue   // click falls outside this triangle
    const depth = w0*szArr[i0] + w1*szArr[i1] + w2*szArr[i2]
    if (depth < bestDepth) {
      bestDepth = depth
      bestVert = (w0 >= w1 && w0 >= w2) ? i0 : (w1 >= w2 ? i1 : i2)
    }
  }
  return bestVert   // -1 if the click missed the mesh's silhouette entirely
}

// ── vertex marker (connectome sphere) ────────────────────────────────────────
function markerConnectomeJSON(x, y, z, size) {
  return {
    name: 'vertex-marker',
    nodeColormap: 'warm', nodeColormapNegative: 'winter',
    nodeMinColor: 0, nodeMaxColor: 1, nodeScale: 1,
    edgeColormap: 'warm', edgeColormapNegative: 'winter',
    edgeMin: 0, edgeMax: 1, edgeScale: 1,
    nodes: { names: ['vertex'], X: [x], Y: [y], Z: [z], Color: [1], Size: [size] },
    edges: []
  }
}

function placeMarker(nvInst, x, y, z) {
  const surf = nvInst.meshes[0]   // the loaded brain surface, always added before any marker
  const radius = surf?.pts ? meshBounds(surf.pts).radius * 0.015 : 2

  let marker = markerMeshes.get(nvInst)
  if (marker) {
    const node = marker.nodes[0]
    marker.updateConnectomeNodeByIndex(0, { ...node, x, y, z, sizeValue: radius })
  } else {
    // loadConnectome() wipes nv.meshes before adding — use the lower-level
    // loadConnectomeAsMesh()+addMesh() instead so the surface mesh survives.
    marker = nvInst.loadConnectomeAsMesh(markerConnectomeJSON(x, y, z, radius))
    nvInst.addMesh(marker)
    markerMeshes.set(nvInst, marker)
  }
  nvInst.drawScene()
}

async function selectVertex(vertIdx, nvInst) {
  if (!currentMetric) return
  const mesh = nvInst.meshes[0]
  if (!mesh?.pts) return
  const nVerts = mesh.pts.length / 3
  if (vertIdx < 0 || vertIdx >= nVerts) return

  // Snap orthoslice crosshairs to vertex world position
  const vx=mesh.pts[vertIdx*3], vy=mesh.pts[vertIdx*3+1], vz=mesh.pts[vertIdx*3+2]
  if (nvSlices.volumes.length && typeof nvSlices.mm2frac === 'function') {
    const frac = nvSlices.mm2frac([vx, vy, vz])
    if (frac) { nvSlices.scene.crosshairPos=[...frac]; nvSlices.drawScene() }
  }

  // Drop a marker sphere on this vertex in every surface panel
  const lhMesh = nvLhL.meshes[0]
  const rhMesh = nvRhL.meshes[0]
  if (lhMesh?.pts) {
    const lx=lhMesh.pts[vertIdx*3], ly=lhMesh.pts[vertIdx*3+1], lz=lhMesh.pts[vertIdx*3+2]
    placeMarker(nvLhL,  lx, ly, lz)
    placeMarker(nvAsym, lx, ly, lz)
  }
  if (rhMesh?.pts) {
    const rx=rhMesh.pts[vertIdx*3], ry=rhMesh.pts[vertIdx*3+1], rz=rhMesh.pts[vertIdx*3+2]
    placeMarker(nvRhL, rx, ry, rz)
  }

  // Read depth profiles from binary matrices
  const info = METRICS[currentMetric]
  const nd   = info.n_depths
  const [lhMat, rhMat, asymMat] = await Promise.all([
    ensureMatrix('lh',   currentMetric),
    ensureMatrix('rh',   currentMetric),
    ensureMatrix('asym', currentMetric),
  ])
  const lhP   = Array.from({length:nd}, (_,d) => lhMat[vertIdx*nd+d])
  const rhP   = Array.from({length:nd}, (_,d) => rhMat[vertIdx*nd+d])
  const asymP = Array.from({length:nd}, (_,d) => asymMat[vertIdx*nd+d])

  setProfiles(lhP, rhP, asymP, nd)
  document.getElementById('vtx-display').textContent = `v${vertIdx}`
  document.getElementById('vtxInput').value = vertIdx
  document.getElementById('pos-display').textContent = `${vx.toFixed(1)}, ${vy.toFixed(1)}, ${vz.toFixed(1)} mm`
}

async function pickOnSurface(canvas, mouseX, mouseY, nvInst) {
  if (!currentMetric) return
  const mesh = nvInst.meshes[0]
  if (!mesh?.pts || !mesh?.tris) return

  const rect = canvas.getBoundingClientRect()
  const ndcX =  (mouseX - rect.left) / rect.width  * 2 - 1
  const ndcY = -((mouseY - rect.top) / rect.height * 2 - 1)

  const origin  = nvInst.pivot3D
  const scale   = (0.8 * nvInst.furthestFromPivot) / (nvInst.scene.volScaleMultiplier || 1)
  const whratio = canvas.clientWidth / canvas.clientHeight
  const az = nvInst.scene.renderAzimuth   ?? 270
  const el = nvInst.scene.renderElevation ??  15

  const vertIdx = pickTriangle(mesh, origin, az, el, scale, whratio, ndcX, ndcY)
  if (vertIdx < 0) return   // click missed the mesh silhouette
  await selectVertex(vertIdx, nvInst)
}

function setupSurfacePicker(canvasId, nvInst) {
  const canvas = document.getElementById(canvasId)
  let downX=0, downY=0
  canvas.addEventListener('mousedown', e => { downX=e.clientX; downY=e.clientY })
  canvas.addEventListener('mouseup',   e => {
    const dx=e.clientX-downX, dy=e.clientY-downY
    if (dx*dx+dy*dy > 25) return
    pickOnSurface(canvas, e.clientX, e.clientY, nvInst)
  })
}
setupSurfacePicker('gl-lh',   nvLhL)
setupSurfacePicker('gl-rh',   nvRhL)
setupSurfacePicker('gl-asym', nvAsym)

// ── vertex ID text entry ──────────────────────────────────────────────────────
document.getElementById('vtxInput').addEventListener('keydown', e => {
  if (e.key !== 'Enter') return
  const id = parseInt(e.target.value, 10)
  if (!Number.isNaN(id)) selectVertex(id, nvLhL)
})

// ── orthoslice zoom (Ctrl + scroll) ──────────────────────────────────────────
let sliceZoom = 1
document.getElementById('gl-slices').addEventListener('wheel', e => {
  if (!e.ctrlKey) return
  e.preventDefault(); e.stopImmediatePropagation()
  sliceZoom = Math.max(0.3, Math.min(8, sliceZoom * (e.deltaY < 0 ? 1.1 : 1/1.1)))
  nvSlices.scene.pan2Dxyzmm[3] = sliceZoom; nvSlices.drawScene()
}, {capture:true, passive:false})

// ── depth-profile charts ──────────────────────────────────────────────────────
function makeChart(id, color, label, fill = false) {
  return new Chart(document.getElementById(id), {
    type: 'line',
    data: { datasets: [{
      label, data: [],
      borderColor: color, backgroundColor: color+'28',
      pointRadius: 2, tension: 0.3, fill, parsing: false
    }]},
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      onClick: (evt, elements, chart) => setDepthFromChart(chart, evt.x),
      plugins: {
        legend: { display: true, labels: { color: '#888', boxWidth: 10, font: {size:10} } },
        annotation: { annotations: { depthLine: {
          type: 'line', xMin: 0, xMax: 0,
          borderColor: '#f5c842', borderWidth: 1.5, borderDash: [4,3]
        }}}
      },
      scales: {
        x: { type:'linear',
             title: { display:true, text:'Depth (mm)', color:'#667' },
             ticks: { color:'#667', maxTicksLimit:8, callback: v => v.toFixed(1) },
             grid:  { color:'#1a1a3a' } },
        y: { ticks: { color:'#667' }, grid: { color:'#1a1a3a' } }
      }
    }
  })
}

function setDepthFromChart(chart, pixelX) {
  const mm  = chart.scales.x.getValueForPixel(pixelX)
  const sl  = document.getElementById('depthSlider')
  const d   = Math.max(0, Math.min(+sl.max, Math.round(mm / STEP_MM)))
  sl.value  = d
  setDepth(d)
}

chartLH   = makeChart('chart-lh',   '#6ab0f5', 'LH')
chartRH   = makeChart('chart-rh',   '#f5a66a', 'RH')
chartAsym = makeChart('chart-asym', '#8af5a6', 'Asymmetry', true)

function updateDepthMarker(mm) {
  if (!chartLH) return
  for (const chart of [chartLH, chartRH, chartAsym]) {
    const ann = chart.options.plugins?.annotation?.annotations?.depthLine
    if (!ann) continue
    ann.xMin = mm; ann.xMax = mm
    chart.update('none')
  }
}

function setProfiles(lhVals, rhVals, asymVals, nd) {
  const toXY = vals => vals.map((v,i) => ({x: i*STEP_MM, y: v}))
  chartLH.data.datasets[0].data   = toXY(lhVals)
  chartRH.data.datasets[0].data   = toXY(rhVals)
  chartAsym.data.datasets[0].data = toXY(asymVals)
  chartLH.update('none'); chartRH.update('none'); chartAsym.update('none')
  updateDepthMarker(currentDepth * STEP_MM)
}

window._nvSurf  = [nvLhL, nvRhL, nvAsym]
window._nvSlice = nvSlices
</script>
</body>
</html>
"""


# ── file discovery ─────────────────────────────────────────────────────────────

def find_files(subj_dir, template=TEMPLATE):
    mri_dir  = os.path.join(subj_dir, 'mri')
    surf_dir = os.path.join(subj_dir, 'surf')
    vol_path = None
    for fname in ('brain.nii.gz', 'brain.nii', 'brain.mgz'):
        p = os.path.join(mri_dir, fname)
        if os.path.isfile(p):
            vol_path = p; break
    def surf(name):
        p = os.path.join(surf_dir, name)
        return p if os.path.isfile(p) else None
    return vol_path, surf(f'lh_white_{template}.surf.gii'), surf(f'rh_white_{template}.surf.gii')


def find_tsf_metrics(subj_dir, template=TEMPLATE):
    dwi_dir = os.path.join(subj_dir, 'dwi')
    metrics = {}
    prefix  = f'lh_{template}_'
    for tsf in sorted(glob.glob(os.path.join(dwi_dir, f'lh_{template}_*.tsf'))):
        metric = os.path.basename(tsf)[len(prefix):].replace('.tsf', '')
        rh     = os.path.join(dwi_dir, f'rh_{template}_{metric}.tsf')
        if os.path.isfile(rh):
            metrics[metric] = {'lh': tsf, 'rh': rh}
    return metrics


# ── TSF → func.gii conversion ─────────────────────────────────────────────────

def tsf_to_func_gii(tsf_path, out_path, mat_path=None):
    """Read TSF, write multi-frame func.gii + optional float32 matrix. Returns (n_depths, M)."""
    _, tracks = read_mrtrix_tsf(tsf_path)
    M = pad_to_matrix(tracks).astype(np.float32)
    finite = M[np.isfinite(M) & (M > 0)]
    cal_min = float(np.percentile(finite,  2)) if finite.size else 0.0
    cal_max = float(np.percentile(finite, 98)) if finite.size else 1.0
    M = np.nan_to_num(M, nan=0.0)
    n_depths = M.shape[1]
    intent   = nib.nifti1.intent_codes['NIFTI_INTENT_NONE']
    darrays  = [nib.gifti.GiftiDataArray(M[:, d], intent=intent, datatype='NIFTI_TYPE_FLOAT32')
                for d in range(n_depths)]
    nib.save(nib.gifti.GiftiImage(darrays=darrays), out_path)
    if mat_path:
        M.tofile(mat_path)
    return n_depths, round(cal_min, 4), round(cal_max, 4), M


def mat_to_asym_func_gii(lh_M, rh_M, out_path, mat_path=None):
    """Compute asymmetry index (LH-RH)/mean(LH,RH), save func.gii + matrix."""
    LH = lh_M.astype(np.float64)
    RH = rh_M.astype(np.float64)
    denom = (LH + RH) / 2.0
    with np.errstate(divide='ignore', invalid='ignore'):
        A = np.where(denom != 0.0, (LH - RH) / denom, 0.0).astype(np.float32)
    A = np.nan_to_num(A, nan=0.0, posinf=0.0, neginf=0.0)

    flat = np.abs(A.ravel())
    flat = flat[flat > 0]
    amax = float(np.percentile(flat, 98)) if flat.size else 1.0

    n_depths = A.shape[1]
    intent   = nib.nifti1.intent_codes['NIFTI_INTENT_NONE']
    darrays  = [nib.gifti.GiftiDataArray(A[:, d], intent=intent, datatype='NIFTI_TYPE_FLOAT32')
                for d in range(n_depths)]
    nib.save(nib.gifti.GiftiImage(darrays=darrays), out_path)
    if mat_path:
        A.tofile(mat_path)
    return round(-amax, 4), round(amax, 4)


def precompute_overlays(tsf_metrics, out_dir, template=TEMPLATE):
    """Convert all TSF pairs to func.gii + binary matrices, including asymmetry."""
    info = {}
    for metric, hemis in tsf_metrics.items():
        lh_gii  = os.path.join(out_dir, f'lh_{template}_{metric}.func.gii')
        rh_gii  = os.path.join(out_dir, f'rh_{template}_{metric}.func.gii')
        asym_gii = os.path.join(out_dir, f'asym_{template}_{metric}.func.gii')
        lh_mat   = os.path.join(out_dir, f'lh_{template}_{metric}_matrix.f32')
        rh_mat   = os.path.join(out_dir, f'rh_{template}_{metric}_matrix.f32')
        asym_mat = os.path.join(out_dir, f'asym_{template}_{metric}_matrix.f32')

        print(f'  lh_{metric} … ', end='', flush=True)
        nd, cmin, cmax, lh_M = tsf_to_func_gii(hemis['lh'], lh_gii, lh_mat)
        print(f'{nd} depths  [{cmin:.3f}, {cmax:.3f}]')

        print(f'  rh_{metric} … ', end='', flush=True)
        _, _, _, rh_M = tsf_to_func_gii(hemis['rh'], rh_gii, rh_mat)
        print('ok')

        print(f'  asym_{metric} … ', end='', flush=True)
        amin, amax = mat_to_asym_func_gii(lh_M, rh_M, asym_gii, asym_mat)
        print(f'[{amin:.3f}, {amax:.3f}]')

        info[metric] = {
            'n_depths':    nd,
            'cal_min':     cmin,
            'cal_max':     cmax,
            'cal_min_asym': amin,
            'cal_max_asym': amax,
        }
    return info


# ── HTML generation ───────────────────────────────────────────────────────────

def make_html(subj_id, vol_path, lh_path, rh_path, overlay_info, port, template=TEMPLATE):
    base = f'http://localhost:{port}/data'

    volumes = []
    if vol_path:
        volumes.append({'url': f'{base}/{os.path.basename(vol_path)}',
                        'colormap': 'gray', 'opacity': 1})
    surfs = []
    if lh_path:
        surfs.append({'url': f'{base}/{os.path.basename(lh_path)}',
                      'rgba255': [100, 180, 255, 255], 'hemi': 'lh'})
    if rh_path:
        surfs.append({'url': f'{base}/{os.path.basename(rh_path)}',
                      'rgba255': [255, 150, 100, 255], 'hemi': 'rh'})

    metric_opts = '\n'.join(
        f'      <option value="{m}">{m}</option>' for m in overlay_info
    ) if overlay_info else '<option value="">none</option>'

    first_info = next(iter(overlay_info.values())) if overlay_info else None
    max_depth  = (first_info['n_depths'] - 1) if first_info else 0
    init_depth = max_depth // 2

    html = _HTML
    for k, v in [
        ('__SUBJ_ID__',        subj_id),
        ('__NIIVUE_CDN__',     NIIVUE_CDN),
        ('__CHARTJS_CDN__',    CHARTJS_CDN),
        ('__CHARTJS_ANN_CDN__', CHARTJS_ANN_CDN),
        ('__VOLUMES_JSON__',   json.dumps(volumes)),
        ('__SURFS_JSON__',     json.dumps(surfs)),
        ('__METRICS_JSON__',   json.dumps(overlay_info)),
        ('__BASE_URL__',       base),
        ('__TEMPLATE__',       template),
        ('__STEP_MM__',        str(STEP_MM)),
        ('__METRIC_OPTIONS__', metric_opts),
        ('__MAX_DEPTH__',      str(max_depth)),
        ('__INIT_DEPTH__',     str(init_depth)),
        ('__INIT_DEPTH_MM__',  f'{init_depth * STEP_MM:.1f}'),
    ]:
        html = html.replace(k, v)
    return html


# ── HTTP server ───────────────────────────────────────────────────────────────

def make_handler(html_bytes, file_map):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split('?')[0]
            if path in ('/', '/index.html'):
                self._reply(200, 'text/html; charset=utf-8', html_bytes)
            elif path in file_map:
                with open(file_map[path], 'rb') as fh:
                    self._reply(200, 'application/octet-stream', fh.read())
            else:
                self._reply(404, 'text/plain', b'Not found\n')

        def _reply(self, code, ctype, data):
            self.send_response(code)
            self.send_header('Content-Type',                ctype)
            self.send_header('Content-Length',              str(len(data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_):
            pass
    return Handler


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='NiiVue cortical browser (production)')
    ap.add_argument('subjects_dir', nargs='?',
                    default='/home/lconcha/fs-edmonton')
    ap.add_argument('subj_id',      nargs='?', default='sub-Mcd005')
    ap.add_argument('--port', type=int, default=8787)
    args = ap.parse_args()

    subj_dir = os.path.join(args.subjects_dir, args.subj_id)
    if not os.path.isdir(subj_dir):
        sys.exit(f'Subject directory not found: {subj_dir}')

    vol_path, lh_path, rh_path = find_files(subj_dir)
    tsf_metrics = find_tsf_metrics(subj_dir)

    print(f'Subject  : {args.subj_id}')
    print(f'Volume   : {vol_path  or "NOT FOUND"}')
    print(f'LH surf  : {lh_path   or "NOT FOUND"}')
    print(f'RH surf  : {rh_path   or "NOT FOUND"}')
    print(f'Metrics  : {list(tsf_metrics) or "none"}')

    out_dir = tempfile.mkdtemp(prefix='cortical_browser_')
    print(f'\nConverting overlays → {out_dir}')
    overlay_info = precompute_overlays(tsf_metrics, out_dir)

    # Build file map: surfaces, volume, and all overlay/matrix files
    file_map = {}
    for p in (vol_path, lh_path, rh_path):
        if p:
            file_map[f'/data/{os.path.basename(p)}'] = p

    for metric in tsf_metrics:
        for prefix in ('lh', 'rh', 'asym'):
            for suffix in ('.func.gii', '_matrix.f32'):
                fname = f'{prefix}_{TEMPLATE}_{metric}{suffix}'
                fpath = os.path.join(out_dir, fname)
                if os.path.isfile(fpath):
                    file_map[f'/data/{fname}'] = fpath

    html_bytes = make_html(
        args.subj_id, vol_path, lh_path, rh_path,
        overlay_info, args.port
    ).encode('utf-8')

    server = HTTPServer(('localhost', args.port), make_handler(html_bytes, file_map))
    url    = f'http://localhost:{args.port}/'
    print(f'\nBrowser  : {url}')
    print('Ctrl+C to quit.\n')

    threading.Thread(target=server.serve_forever, daemon=True).start()
    webbrowser.open(url)
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown(); print('Done.')


if __name__ == '__main__':
    main()
