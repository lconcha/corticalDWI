#!/usr/bin/env python3
"""
cortical_browser.py — Production NiiVue cortical browser.

Three surface panels (LH lateral, RH lateral, Asymmetry index on LH geometry),
three orthoslice panels with surface contours, three depth-profile charts.
CLim and colormap controls for both data and asymmetry surfaces.

Usage:
    python cortical_browser.py [subjects_dir] [subj_id] [--port PORT]
"""
import os, sys, glob, json, time, threading, webbrowser, argparse, tempfile, re, warnings
import numpy as np
import nibabel as nib
import h5py

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
:root { --accent-yellow: #F5C842; }   /* selected-vertex accent, shared by box/crosshair/plot line */
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
.apptitle { font-weight: bold; color: var(--accent-yellow); font-size: 12px; letter-spacing: 0.5px; white-space: nowrap; }
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
/* Re-enable up/down spinners for the Rings field only */
#ringsInput { -moz-appearance: number-input; width: 52px; }
#ringsInput::-webkit-inner-spin-button,
#ringsInput::-webkit-outer-spin-button {
  display: inline-block; -webkit-appearance: inner-spin-button; opacity: 1;
}
#vtxInput {
  background: var(--accent-yellow); color: #1a1a1a; border: 1px solid var(--accent-yellow); font-weight: bold;
}
button.cbtn {
  background: #3a3a3a; color: #ddd; border: 1px solid #555555;
  border-radius: 3px; padding: 1px 6px; font-size: 10px; cursor: pointer;
}
button.cbtn:hover { background: #484848; }
#depth-label { color: #d1d1d1; min-width: 40px; }
#pos-display  { color: #999999; font-size: 10px; white-space: nowrap; overflow: hidden; max-width: 200px; }
#vtx-display  {
  color: #ccc; font-size: 11px; font-family: monospace; font-weight: bold;
  background: #262626; border: 1px solid #555555; border-radius: 3px;
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
.cbar-title {
  display: block; text-align: center;
  font-size: 9px; color: #999999; margin-bottom: 2px; font-family: monospace;
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
  <span class="apptitle">CORTICAL BROWSER</span>
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
  <label>Ov <input type="range" id="ovOp" min="0" max="100" value="100"></label>
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
    <option value="Matte">Matte</option>
    <option value="Phong">Phong</option>
    <option value="Diffuse" selected>Diffuse</option>
  </select></label>
  <div class="sep"></div>

  <label>LH surf <select id="lhSurfSel"></select></label>
  <label>RH surf <select id="rhSurfSel"></select></label>
  <label>Asym surf <select id="asymSurfSel"></select></label>
  <div class="sep"></div>

  <label><input type="checkbox" id="radioConv" checked> Rad</label>
  <label><input type="checkbox" id="crosshairChk" checked> X-hair</label>
  <label title="Overlay white-matter surface outline on the orthoslices (loaded on first use)"><input type="checkbox" id="contourWmChk"> WM</label>
  <label title="Overlay pial surface outline on the orthoslices (loaded on first use)"><input type="checkbox" id="contourPialChk"> pial</label>
  <label>Vertex <input type="number" id="vtxInput" min="0" step="1" title="Jump to vertex ID"></label>
  <label>Rings <input type="number" id="ringsInput" min="0" step="1" value="0" title="Neighbor rings to average around the selected vertex"></label>
  <label><input type="checkbox" id="pivotAtVertexChk"> Pivot@vertex</label>
  <button class="cbtn" id="resetPivotBtn" title="Reset 3D view rotation pivot to the whole-brain center">Reset pivot</button>
  <label><input type="checkbox" id="showNormativeChk" title="Fetch and overlay cohort normative mean ± SD (computed lazily on first use)"> Show normative</label>
  <span id="pos-display"></span>
  <span id="vtx-display">—, —, — mm</span>
</header>

<div id="grid">
  <!-- Row 1: surface 3-D renders -->
  <div class="cell">
    <canvas id="gl-lh" class="nv-canvas"></canvas>
    <span class="clabel">LH lateral</span>
    <div class="cbar">
      <span class="cbar-title" id="cbtitle-lh"></span>
      <div class="cbar-g" id="cbgrad-lh"></div>
      <div class="cbar-ll"><span id="cblbl-lh-min">0</span><span id="cblbl-lh-max">1</span></div>
    </div>
  </div>
  <div class="cell">
    <canvas id="gl-rh" class="nv-canvas"></canvas>
    <span class="clabel">RH lateral</span>
    <div class="cbar">
      <span class="cbar-title" id="cbtitle-rh"></span>
      <div class="cbar-g" id="cbgrad-rh"></div>
      <div class="cbar-ll"><span id="cblbl-rh-min">0</span><span id="cblbl-rh-max">1</span></div>
    </div>
  </div>
  <div class="cell">
    <canvas id="gl-asym" class="nv-canvas"></canvas>
    <span class="clabel">Asymmetry index (LH geom)</span>
    <div class="cbar">
      <span class="cbar-title" id="cbtitle-asym"></span>
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
const SURF_TYPES = __SURF_TYPES_JSON__
const NORMATIVE = __NORMATIVE_JSON__
const METRICS  = __METRICS_JSON__
const BASE_URL = "__BASE_URL__"
const TEMPLATE = "__TEMPLATE__"
const STEP_MM  = __STEP_MM__

// Selected-vertex accent color, shared across the vertex box (CSS --accent-yellow),
// the orthoslice crosshair, and the plots' depth reference line.
const ACCENT_YELLOW = '#F5C842'
const ACCENT_YELLOW_RGBA = [0xF5/255, 0xC8/255, 0x42/255, 1]

// ── app state ─────────────────────────────────────────────────────────────────
let currentMetric  = Object.keys(METRICS)[0] || null
let currentCmap    = 'viridis'
let currentCmapAsym = 'bwr'
let dataInvert     = false
let asymInvert     = false
let layerOpacity   = 1.0
let currentShader  = 'Diffuse'
let currentDepth   = 0
let currentClimMin = 0, currentClimMax = 1
let currentAsymMin = -1, currentAsymMax = 1
// Orthoslice surface contours are off by default and lazily loaded per kind.
let nRings = 0
let currentVertex = null
let pivotAtVertex = false
let showNormative = false
const markerMeshes = new Map()   // nv instance -> its vertex-marker connectome mesh
const neighborMeshes = new Map() // nv instance -> its neighbor-rings connectome mesh

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

// Per-hemisphere accent colors: single source of truth is each surface's
// rgba255 (set in Python); the LH/RH plot lines reuse the same hue so the
// surfaces and their depth-profile plots always match.
const rgba255ToHex = ([r, g, b]) =>
  '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('')
const LH_COLOR = LH_SURF ? rgba255ToHex(LH_SURF.rgba255) : '#66B3FF'
const RH_COLOR = RH_SURF ? rgba255ToHex(RH_SURF.rgba255) : '#FF854D'

// Independently-selectable surface geometry per panel (white/pial/inflated/
// very_inflated/average_white/average_pial) — all share the same ico6_sym
// topology, so switching only changes vertex coordinates, not data mapping.
let lhSurfUrl   = LH_SURF?.url ?? null
let rhSurfUrl   = RH_SURF?.url ?? null
let asymSurfUrl = LH_SURF?.url ?? null

// Orthoslice contour meshes, lazily loaded per surface kind ('wm' = white,
// 'pial') and kept in memory once loaded so toggling visibility is instant.
// Only white/pial are ever overlaid; the LH/RH panel surface-type selectors
// (inflated, very_inflated, ...) never touch these. Each loaded entry holds
// both hemispheres: { lh: NVMesh, rh: NVMesh }.
const SLICE_CONTOUR_SURF = { wm: 'white', pial: 'pial' }
const sliceContours = { wm: null, pial: null }
const sliceContourVisible = { wm: false, pial: false }

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

// Initial 3D camera framing per panel, reused by the first load and the "r"
// reset shortcut so both stay in sync.
function applyInitialCameras() {
  setCam(nvLhL,   90, 15)   // LH lateral
  setCam(nvRhL,  270, 15)   // RH lateral
  setCam(nvAsym,  90, 15)   // Asymmetry (LH geometry, lateral view)
}

// draw3D() calls nv.setPivot3D() at the start of every single frame, which
// recomputes pivot3D from the scene's bounding box — so a one-off assignment
// to nv.pivot3D gets silently overwritten on the very next redraw. Overriding
// the method itself keeps our chosen pivot authoritative on every frame, while
// still running the original logic first so furthestFromPivot/extents (zoom)
// stay correct.
function setCustomPivot(nv, point) {
  if (!nv._origSetPivot3D) nv._origSetPivot3D = nv.setPivot3D.bind(nv)
  nv.setPivot3D = function() {
    nv._origSetPivot3D()
    nv.pivot3D = point
  }
  nv.drawScene()
}

function resetPivot(nv) {
  if (nv._origSetPivot3D) {
    nv.setPivot3D = nv._origSetPivot3D
    delete nv._origSetPivot3D
  }
  nv.drawScene()
}

// ── surface loading ───────────────────────────────────────────────────────────
// Split into one loader per panel + one for the orthoslice contours, so a
// single surface-type dropdown change only reloads what actually changed
// instead of re-fetching/re-parsing/re-uploading all three mesh panels.
function layerDataFor(hemi, metric) {
  const info = metric ? METRICS[metric] : null
  if (!info) return []
  return [{ url: `${BASE_URL}/${hemi}_${TEMPLATE}_${metric}.func.gii`,
            colormap: currentCmap, colormapInvert: dataInvert,
            opacity: layerOpacity, cal_min: currentClimMin, cal_max: currentClimMax }]
}
function layerAsymFor(metric) {
  const info = metric ? METRICS[metric] : null
  if (!info) return []
  return [{ url: `${BASE_URL}/asym_${TEMPLATE}_${metric}.func.gii`,
            colormap: currentCmapAsym, colormapInvert: asymInvert,
            opacity: layerOpacity, cal_min: currentAsymMin, cal_max: currentAsymMax }]
}

async function loadLhPanel(metric) {
  if (!LH_SURF || !lhSurfUrl) return
  console.time('loadLhPanel')
  markerMeshes.delete(nvLhL); neighborMeshes.delete(nvLhL)
  await nvLhL.loadMeshes([{ url: lhSurfUrl, rgba255: LH_SURF.rgba255, layers: layerDataFor('lh', metric) }])
  applyShader(nvLhL, currentShader)
  console.timeEnd('loadLhPanel')
}

async function loadRhPanel(metric) {
  if (!RH_SURF || !rhSurfUrl) return
  console.time('loadRhPanel')
  markerMeshes.delete(nvRhL); neighborMeshes.delete(nvRhL)
  await nvRhL.loadMeshes([{ url: rhSurfUrl, rgba255: RH_SURF.rgba255, layers: layerDataFor('rh', metric) }])
  applyShader(nvRhL, currentShader)
  console.timeEnd('loadRhPanel')
}

async function loadAsymPanel(metric) {
  if (!LH_SURF || !asymSurfUrl) return
  console.time('loadAsymPanel')
  markerMeshes.delete(nvAsym); neighborMeshes.delete(nvAsym)
  await nvAsym.loadMeshes([{ url: asymSurfUrl, rgba255: LH_SURF.rgba255, layers: layerAsymFor(metric) }])
  applyShader(nvAsym, currentShader)
  console.timeEnd('loadAsymPanel')

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

// Orthoslice contours (geometry only, no scalar overlay). Loaded on demand the
// first time their WM/pial toggle is switched on, then kept in nvSlices' mesh
// list so on/off is just an opacity change — no re-parse/re-upload. Added via
// addMesh (not loadMeshes, which would replace nvSlices' whole mesh list).
async function ensureSliceContour(kind) {
  if (sliceContours[kind]) return sliceContours[kind]
  const surfType = SLICE_CONTOUR_SURF[kind]
  const lhUrl = SURF_TYPES[surfType]?.lh
  const rhUrl = SURF_TYPES[surfType]?.rh
  console.time(`ensureSliceContour:${kind}`)
  const [lhMesh, rhMesh] = await Promise.all([
    lhUrl ? niivue.NVMesh.loadFromUrl({ url: lhUrl, gl: nvSlices.gl, rgba255: LH_SURF.rgba255 }) : null,
    rhUrl ? niivue.NVMesh.loadFromUrl({ url: rhUrl, gl: nvSlices.gl, rgba255: RH_SURF.rgba255 }) : null,
  ])
  for (const m of [lhMesh, rhMesh]) if (m) nvSlices.addMesh(m)
  sliceContours[kind] = { lh: lhMesh, rh: rhMesh }
  applyShader(nvSlices, 'Crosscut')   // clean plane-intersection contour instead of a thick slab
  console.timeEnd(`ensureSliceContour:${kind}`)
  return sliceContours[kind]
}

function applySliceContourVisibility(kind) {
  const c = sliceContours[kind]
  if (!c) return
  const op = sliceContourVisible[kind] ? 1 : 0
  for (const m of [c.lh, c.rh]) if (m) nvSlices.setMeshProperty(m.id, 'opacity', op)
  nvSlices.drawScene()
}

async function toggleSliceContour(kind, on) {
  sliceContourVisible[kind] = on
  if (on) await ensureSliceContour(kind)
  applySliceContourVisibility(kind)
}

async function loadAllSurfaces(metric, resetCamera = false) {
  await Promise.all([
    loadLhPanel(metric),
    loadRhPanel(metric),
    loadAsymPanel(metric),
  ])
  if (resetCamera) {
    applyInitialCameras()
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

// ── normative (cohort) matrix cache ──────────────────────────────────────────
const normCache = {}

async function ensureNormativeMatrix(kind, metric, stat) {
  const key = `${kind}_${metric}_${stat}`
  if (normCache[key]) return normCache[key]
  const r = await fetch(`${BASE_URL}/normative_${kind}_${metric}_${stat}.f32`)
  normCache[key] = new Float32Array(await r.arrayBuffer())
  return normCache[key]
}

async function normativeRingStat(kind, metric, ringSet) {
  const info = NORMATIVE[metric]?.[kind]
  if (!info) return null
  const nd = info.n_depths
  const [meanMat, stdMat] = await Promise.all([
    ensureNormativeMatrix(kind, metric, 'mean'),
    ensureNormativeMatrix(kind, metric, 'std'),
  ])
  // Ring-average the precomputed per-vertex cohort mean; combine per-vertex
  // SDs by averaging variances (a "pooled SD" approximation — the true
  // per-ring SD would need the raw per-subject stack, not just mean/std).
  const mean = new Array(nd).fill(0)
  const variance = new Array(nd).fill(0)
  for (const vi of ringSet) {
    for (let d = 0; d < nd; d++) {
      mean[d]     += meanMat[vi*nd+d]
      variance[d] += stdMat[vi*nd+d] ** 2
    }
  }
  const n = ringSet.length
  for (let d = 0; d < nd; d++) { mean[d] /= n; variance[d] /= n }
  return { mean, sd: variance.map(Math.sqrt), n: NORMATIVE[metric].n_subjects }
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

// Remember the volume's default grayscale window so "r" can restore it after
// the user drag-adjusts orthoslice contrast.
let defaultVolCalMin = null, defaultVolCalMax = null
if (nvSlices.volumes.length) {
  defaultVolCalMin = nvSlices.volumes[0].cal_min
  defaultVolCalMax = nvSlices.volumes[0].cal_max
}

// ── slice setup (single multiplanar instance) ─────────────────────────────────
nvSlices.opts.onLocationChange = d => {
  document.getElementById('pos-display').textContent = d.string
}
nvSlices.setSliceType(nvSlices.sliceTypeMultiplanar)
nvSlices.setRadiologicalConvention(true)
nvSlices.setCrosshairColor(ACCENT_YELLOW_RGBA)   // match selected-vertex color
nvSlices.setCrosshairWidth(0.5)                   // thinner than the default 1px

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

// Step cortical depth by ±1, clamped to the current metric's range, keeping the
// slider in sync. Used by the +/- keyboard shortcuts.
function stepDepth(delta) {
  if (!currentMetric) return
  const nd = METRICS[currentMetric].n_depths
  const d = Math.max(0, Math.min(nd - 1, currentDepth + delta))
  if (d === currentDepth) return
  document.getElementById('depthSlider').value = d
  setDepth(d)
}

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

// Pin the Asymmetry plot's y-axis to the asym colormap limits so the plot and
// the surface color scale share the same range.
function applyAsymYLimits() {
  if (!chartAsym) return
  chartAsym.options.scales.y.min = currentAsymMin
  chartAsym.options.scales.y.max = currentAsymMax
  chartAsym.update('none')
}

function setAsymCLim(mn, mx) {
  currentAsymMin = mn; currentAsymMax = mx
  for (const mesh of nvAsym.meshes)
    if (mesh.layers?.length) {
      nvAsym.setMeshLayerProperty(mesh.id, 0, 'cal_min', mn)
      nvAsym.setMeshLayerProperty(mesh.id, 0, 'cal_max', mx)
    }
  applyAsymYLimits()
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
    ['lh',   currentCmap,     dataInvert, currentClimMin, currentClimMax, currentMetric],
    ['rh',   currentCmap,     dataInvert, currentClimMin, currentClimMax, currentMetric],
    ['asym', currentCmapAsym, asymInvert, currentAsymMin, currentAsymMax, `${currentMetric} asymmetry`],
  ]
  for (const [id, cmap, inv, mn, mx, title] of pairs) {
    const g = document.getElementById(`cbgrad-${id}`)
    const l = document.getElementById(`cblbl-${id}-min`)
    const r = document.getElementById(`cblbl-${id}-max`)
    const t = document.getElementById(`cbtitle-${id}`)
    if (g) g.style.background = cmapCss(cmap, inv)
    if (l) l.textContent = fmt(mn)
    if (r) r.textContent = fmt(mx)
    if (t) t.textContent = title || ''
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
  applyAsymYLimits()
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

// ── WM / pial contour overlays on the orthoslices (lazy-loaded) ──────────────
document.getElementById('contourWmChk').addEventListener('change', function() {
  toggleSliceContour('wm', this.checked)
})
document.getElementById('contourPialChk').addEventListener('change', function() {
  toggleSliceContour('pial', this.checked)
})

// ── shader selector ───────────────────────────────────────────────────────────
document.getElementById('shaderSel').addEventListener('change', e => {
  currentShader = e.target.value; applyCurrentShader()
})

// ── per-panel surface-type selectors (white/pial/inflated/...) ──────────────
function populateSurfSel(selEl, hemi) {
  const types = Object.keys(SURF_TYPES).filter(t => SURF_TYPES[t][hemi])
  selEl.innerHTML = types.map(t => `<option value="${t}">${t}</option>`).join('')
  if (types.includes('white')) selEl.value = 'white'
}
populateSurfSel(document.getElementById('lhSurfSel'),   'lh')
populateSurfSel(document.getElementById('rhSurfSel'),   'rh')
populateSurfSel(document.getElementById('asymSurfSel'), 'lh')

async function reselectAfterSurfChange() {
  if (currentVertex === null) return
  console.time('reselectAfterSurfChange')
  await selectVertex(currentVertex, nvLhL)
  console.timeEnd('reselectAfterSurfChange')
}
document.getElementById('lhSurfSel').addEventListener('change', async e => {
  lhSurfUrl = SURF_TYPES[e.target.value]?.lh ?? lhSurfUrl
  lhVertexAreas = null   // geometry changed — per-vertex area must be recomputed
  // Orthoslice contours are independent WM/pial overlays, so the panel's
  // surface-type change only reloads the LH 3-D panel.
  await loadLhPanel(currentMetric)
  await reselectAfterSurfChange()
})
document.getElementById('rhSurfSel').addEventListener('change', async e => {
  rhSurfUrl = SURF_TYPES[e.target.value]?.rh ?? rhSurfUrl
  rhVertexAreas = null
  await loadRhPanel(currentMetric)
  await reselectAfterSurfChange()
})
document.getElementById('asymSurfSel').addEventListener('change', async e => {
  asymSurfUrl = SURF_TYPES[e.target.value]?.lh ?? asymSurfUrl
  // Asym's geometry doesn't feed the slice contours or the LH/RH panels.
  await loadAsymPanel(currentMetric)
  await reselectAfterSurfChange()
})

// ── radiological / crosshair ──────────────────────────────────────────────────
document.getElementById('radioConv').addEventListener('change', function() {
  nvSlices.setRadiologicalConvention(this.checked)
})
const defaultCrosshairWidth = nvSlices.opts.crosshairWidth
document.getElementById('crosshairChk').addEventListener('change', function() {
  nvSlices.opts.show3Dcrosshair = this.checked
  nvSlices.setCrosshairWidth(this.checked ? defaultCrosshairWidth : 0)
  nvSlices.drawScene()
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
  if (currentVertex !== null) {
    // Keep the selected vertex; re-select to redraw its markers and replot the
    // three depth profiles against the newly-loaded metric.
    await selectVertex(currentVertex, nvLhL)
  } else {
    document.getElementById('vtx-display').textContent = '—, —, — mm'
    document.getElementById('pos-display').textContent = ''
    resetPivot(nvLhL); resetPivot(nvRhL); resetPivot(nvAsym)
    for (const chart of [chartLH, chartRH, chartAsym]) {
      chart.data.datasets[0].label = chart.baseLabel
      for (const i of [0, 1, 2, 3, 4, 5]) chart.data.datasets[i].data = []
      chart.update('none')
    }
  }
})

// ── initial depth + colorbars ─────────────────────────────────────────────────
setDepth(currentDepth)
refreshColorbars()

// ── neighbor-ring expansion (mirrors getNeighborRings in cortical_browser_2.m) ─
// Built lazily from the LH mesh topology and reused for RH/Asym since all three
// share the same ico6_sym triangulation — only vertex coordinates differ.
let vertexAdjacency = null

function buildAdjacency(tris, nVerts) {
  const adj = Array.from({length: nVerts}, () => new Set())
  for (let t = 0; t < tris.length; t += 3) {
    const a = tris[t], b = tris[t+1], c = tris[t+2]
    adj[a].add(b); adj[a].add(c)
    adj[b].add(a); adj[b].add(c)
    adj[c].add(a); adj[c].add(b)
  }
  return adj
}

function ensureAdjacency() {
  if (vertexAdjacency) return vertexAdjacency
  const mesh = nvLhL.meshes[0]
  if (!mesh?.tris || !mesh?.pts) return null
  vertexAdjacency = buildAdjacency(mesh.tris, mesh.pts.length / 3)
  return vertexAdjacency
}

function neighborRings(v, rings) {
  const adj = ensureAdjacency()
  if (!adj || rings <= 0) return [v]
  const visited = new Set([v])
  let frontier = [v]
  for (let r = 0; r < rings && frontier.length; r++) {
    const next = []
    for (const vi of frontier) {
      for (const nb of adj[vi]) {
        if (!visited.has(nb)) { visited.add(nb); next.push(nb) }
      }
    }
    frontier = next
  }
  return Array.from(visited)
}

// ── per-vertex surface area (mirrors FreeSurfer's ?h.area: each triangle's
// area is split into thirds, one third credited to each of its 3 vertices) ──
let lhVertexAreas = null, rhVertexAreas = null

function buildVertexAreas(pts, tris) {
  const areas = new Float64Array(pts.length / 3)
  for (let t = 0; t < tris.length; t += 3) {
    const i0 = tris[t], i1 = tris[t+1], i2 = tris[t+2]
    const ux = pts[i1*3]   - pts[i0*3],   uy = pts[i1*3+1] - pts[i0*3+1], uz = pts[i1*3+2] - pts[i0*3+2]
    const vx = pts[i2*3]   - pts[i0*3],   vy = pts[i2*3+1] - pts[i0*3+1], vz = pts[i2*3+2] - pts[i0*3+2]
    const crx = uy*vz - uz*vy, cry = uz*vx - ux*vz, crz = ux*vy - uy*vx
    const third = 0.5 * Math.sqrt(crx*crx + cry*cry + crz*crz) / 3
    areas[i0] += third; areas[i1] += third; areas[i2] += third
  }
  return areas
}

function ensureVertexAreas(hemi) {
  const nv = hemi === 'lh' ? nvLhL : nvRhL
  if (hemi === 'lh' && lhVertexAreas) return lhVertexAreas
  if (hemi === 'rh' && rhVertexAreas) return rhVertexAreas
  const mesh = nv.meshes[0]
  if (!mesh?.tris || !mesh?.pts) return null
  console.time(`buildVertexAreas(${hemi})`)
  const areas = buildVertexAreas(mesh.pts, mesh.tris)
  console.timeEnd(`buildVertexAreas(${hemi})`)
  if (hemi === 'lh') lhVertexAreas = areas; else rhVertexAreas = areas
  return areas
}

function ringArea(hemi, ringSet) {
  const areas = ensureVertexAreas(hemi)
  if (!areas) return null
  let sum = 0
  for (const v of ringSet) sum += areas[v]
  return sum
}

function meanStd(rows) {
  const n = rows.length, nd = rows[0].length
  const mean = new Array(nd).fill(0)
  for (const row of rows) for (let d = 0; d < nd; d++) mean[d] += row[d]
  for (let d = 0; d < nd; d++) mean[d] /= n
  if (n <= 1) return { mean, sd: null }
  const sd = new Array(nd).fill(0)
  for (const row of rows) for (let d = 0; d < nd; d++) { const diff = row[d] - mean[d]; sd[d] += diff*diff }
  for (let d = 0; d < nd; d++) sd[d] = Math.sqrt(sd[d] / (n - 1))
  return { mean, sd }
}

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
    showLegend: false,   // suppress the floating "vertex" text label over the sphere
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
  return radius
}

// ── neighbor-ring markers (white spheres, 30% of the seed's radius) ─────────
function neighborConnectomeJSON(node0, size) {
  return {
    name: 'vertex-neighbors',
    nodeColormap: 'gray', nodeColormapNegative: 'gray',
    nodeMinColor: 0, nodeMaxColor: 1, nodeScale: 1,
    edgeColormap: 'gray', edgeColormapNegative: 'gray',
    edgeMin: 0, edgeMax: 1, edgeScale: 1,
    showLegend: false,   // suppress the floating "nbrN" text labels over each sphere
    nodes: { names: [node0.name], X: [node0.x], Y: [node0.y], Z: [node0.z], Color: [1], Size: [size] },
    edges: []
  }
}

function syncNeighborMarkers(nvInst, points, size) {
  const mesh = neighborMeshes.get(nvInst)
  if (!points.length) {
    // Fully remove the mesh rather than emptying/shrinking its node array —
    // mutating a connectome's node count/sizes in place was corrupting the
    // scene's rendering. removeMesh() is the same officially supported path
    // used to drop any mesh/connectome, so it's re-created fresh next time.
    if (mesh) {
      nvInst.removeMesh(mesh)
      neighborMeshes.delete(nvInst)
      nvInst.drawScene()
    }
    return
  }
  const nodes = points.map((p, i) => ({ name: `nbr${i}`, x: p[0], y: p[1], z: p[2], colorValue: 1, sizeValue: size }))
  if (!mesh) {
    const newMesh = nvInst.loadConnectomeAsMesh(neighborConnectomeJSON(nodes[0], size))
    nvInst.addMesh(newMesh)
    neighborMeshes.set(nvInst, newMesh)
    newMesh.nodes = nodes
    newMesh.updateConnectome(nvInst.gl)
    nvInst.drawScene()
    return
  }
  mesh.nodes = nodes
  mesh.updateConnectome(nvInst.gl)
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

  const ringSet     = neighborRings(vertIdx, nRings)
  const neighborIdx = ringSet.filter(v => v !== vertIdx)

  // Drop a marker sphere on this vertex (plus smaller white spheres on its
  // neighbor-ring vertices) in every surface panel
  const lhMesh = nvLhL.meshes[0]
  const rhMesh = nvRhL.meshes[0]
  if (lhMesh?.pts) {
    const lx=lhMesh.pts[vertIdx*3], ly=lhMesh.pts[vertIdx*3+1], lz=lhMesh.pts[vertIdx*3+2]
    const seedR = placeMarker(nvLhL,  lx, ly, lz)
    placeMarker(nvAsym, lx, ly, lz)
    const lhNbrPts = neighborIdx.map(vi => [lhMesh.pts[vi*3], lhMesh.pts[vi*3+1], lhMesh.pts[vi*3+2]])
    syncNeighborMarkers(nvLhL,  lhNbrPts, seedR * 0.3)
    syncNeighborMarkers(nvAsym, lhNbrPts, seedR * 0.3)   // same LH geometry/scale as nvLhL

    // Pivot the 3D orbit camera around the selected vertex instead of the
    // whole-brain center, if enabled via the "Pivot@vertex" checkbox
    if (pivotAtVertex) {
      setCustomPivot(nvLhL,  [lx, ly, lz])
      setCustomPivot(nvAsym, [lx, ly, lz])
    }
  }
  if (rhMesh?.pts) {
    const rx=rhMesh.pts[vertIdx*3], ry=rhMesh.pts[vertIdx*3+1], rz=rhMesh.pts[vertIdx*3+2]
    const seedRr = placeMarker(nvRhL, rx, ry, rz)
    const rhNbrPts = neighborIdx.map(vi => [rhMesh.pts[vi*3], rhMesh.pts[vi*3+1], rhMesh.pts[vi*3+2]])
    syncNeighborMarkers(nvRhL, rhNbrPts, seedRr * 0.3)
    if (pivotAtVertex) setCustomPivot(nvRhL, [rx, ry, rz])
  }

  currentVertex = vertIdx

  // Read depth profiles from binary matrices, averaged over the neighbor-ring set
  const info = METRICS[currentMetric]
  const nd   = info.n_depths
  const [lhMat, rhMat, asymMat] = await Promise.all([
    ensureMatrix('lh',   currentMetric),
    ensureMatrix('rh',   currentMetric),
    ensureMatrix('asym', currentMetric),
  ])
  const rowsOf = mat => ringSet.map(vi => {
    const row = new Array(nd)
    for (let d = 0; d < nd; d++) row[d] = mat[vi*nd+d]
    return row
  })
  const lhArea = ringArea('lh', ringSet)
  const rhArea = ringArea('rh', ringSet)

  let normStat = null
  if (showNormative && NORMATIVE[currentMetric]) {
    const [normLh, normRh, normAsym] = await Promise.all([
      normativeRingStat('lh',   currentMetric, ringSet),
      normativeRingStat('rh',   currentMetric, ringSet),
      normativeRingStat('asym', currentMetric, ringSet),
    ])
    normStat = { lh: normLh, rh: normRh, asym: normAsym }
  }

  setProfiles(meanStd(rowsOf(lhMat)), meanStd(rowsOf(rhMat)), meanStd(rowsOf(asymMat)), ringSet.length, lhArea, rhArea, normStat)
  document.getElementById('vtx-display').textContent = `${vx.toFixed(1)}, ${vy.toFixed(1)}, ${vz.toFixed(1)} mm`
  document.getElementById('vtxInput').value = vertIdx
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

// ── 3D surface zoom (scroll) — niivue's own default wheel-zoom clamps to a
// narrow range; override it here with a much wider one ────────────────────
function setupSurfaceZoom(canvasId, nvInst) {
  const canvas = document.getElementById(canvasId)
  canvas.addEventListener('wheel', e => {
    e.preventDefault(); e.stopImmediatePropagation()
    const factor  = e.deltaY < 0 ? 1.1 : 1/1.1
    const current = nvInst.scene.volScaleMultiplier || 1
    nvInst.scene.volScaleMultiplier = Math.max(0.05, Math.min(100, current * factor))
    nvInst.drawScene()
  }, {capture:true, passive:false})
}
setupSurfaceZoom('gl-lh',   nvLhL)
setupSurfaceZoom('gl-rh',   nvRhL)
setupSurfaceZoom('gl-asym', nvAsym)

// ── vertex ID text entry ──────────────────────────────────────────────────────
document.getElementById('vtxInput').addEventListener('keydown', e => {
  if (e.key !== 'Enter') return
  const id = parseInt(e.target.value, 10)
  if (!Number.isNaN(id)) selectVertex(id, nvLhL)
})

// ── neighbor-ring count ───────────────────────────────────────────────────────
document.getElementById('ringsInput').addEventListener('change', e => {
  const r = Math.max(0, parseInt(e.target.value, 10) || 0)
  e.target.value = r
  nRings = r
  if (currentVertex !== null) selectVertex(currentVertex, nvLhL)
})

// ── pivot@vertex toggle + reset 3D orbit pivot back to the whole-brain center ─
document.getElementById('pivotAtVertexChk').addEventListener('change', function() {
  pivotAtVertex = this.checked
  if (!pivotAtVertex) {
    resetPivot(nvLhL); resetPivot(nvRhL); resetPivot(nvAsym)
  } else if (currentVertex !== null) {
    selectVertex(currentVertex, nvLhL)   // re-apply pivot for the current selection
  }
})
document.getElementById('resetPivotBtn').addEventListener('click', () => {
  resetPivot(nvLhL); resetPivot(nvRhL); resetPivot(nvAsym)
})

// ── show/hide normative (cohort) comparison ──────────────────────────────────
document.getElementById('showNormativeChk').addEventListener('change', async function() {
  showNormative = this.checked
  if (showNormative) {
    if (currentVertex !== null) await selectVertex(currentVertex, nvLhL)
  } else {
    for (const chart of [chartLH, chartRH, chartAsym]) {
      for (const i of [3, 4, 5]) chart.data.datasets[i].data = []
      chart.update('none')
    }
  }
})

// Disable the toggle when the server found no cohort normative data, so it's
// clearly unavailable rather than silently doing nothing.
{
  const chk = document.getElementById('showNormativeChk')
  if (Object.keys(NORMATIVE).length === 0) {
    chk.disabled = true
    chk.checked = false
    chk.parentElement.style.opacity = 0.4
    chk.parentElement.title = 'No cohort normative data available for this dataset'
  }
}

// ── orthoslice zoom (Ctrl + scroll) ──────────────────────────────────────────
let sliceZoom = 1
document.getElementById('gl-slices').addEventListener('wheel', e => {
  if (!e.ctrlKey) return
  e.preventDefault(); e.stopImmediatePropagation()
  sliceZoom = Math.max(0.3, Math.min(8, sliceZoom * (e.deltaY < 0 ? 1.1 : 1/1.1)))
  nvSlices.scene.pan2Dxyzmm[3] = sliceZoom; nvSlices.drawScene()
}, {capture:true, passive:false})

// Reset the orthoslices: viewport (zoom + pan) and the grayscale contrast.
function resetSliceView() {
  sliceZoom = 1
  nvSlices.scene.pan2Dxyzmm = [0, 0, 0, 1]
  if (nvSlices.volumes.length && defaultVolCalMin !== null) {
    nvSlices.volumes[0].cal_min = defaultVolCalMin
    nvSlices.volumes[0].cal_max = defaultVolCalMax
    nvSlices.updateGLVolume()
  }
  nvSlices.drawScene()
}

// Reset the 3D surface panels to their initial framing: camera angles, zoom,
// and rotation pivot.
function reset3DSurfaceView() {
  applyInitialCameras()
  for (const nv of [nvLhL, nvRhL, nvAsym]) {
    nv.scene.volScaleMultiplier = 1
    resetPivot(nv)   // also redraws
  }
}

// ── keyboard shortcuts ────────────────────────────────────────────────────────
// Step the orthoslice crosshair by whole voxels along L-R (x), P-A (y), I-S (z).
function stepCrosshair(dx, dy, dz) {
  if (!nvSlices.volumes.length) return
  nvSlices.moveCrosshairInVox(dx, dy, dz)
}

// Step the neighbor-ring count via its input so the field (and its spinners)
// stay in sync and the existing change handler does the clamp + replot.
function stepRings(delta) {
  const el = document.getElementById('ringsInput')
  el.value = Math.max(0, (parseInt(el.value, 10) || 0) + delta)
  el.dispatchEvent(new Event('change'))
}

// Global handler; ignores keys typed into form fields so vertex/number inputs
// still work normally. More shortcuts get added to the switch below.
document.addEventListener('keydown', e => {
  const t = e.target
  if (t && (t.tagName === 'INPUT' || t.tagName === 'SELECT' ||
            t.tagName === 'TEXTAREA' || t.isContentEditable)) return
  if (e.ctrlKey || e.metaKey || e.altKey) return
  // Numpad +/- adjust the ring count (distinct from the main-keyboard +/-,
  // which change depth); keyed off e.code since e.key is identical for both.
  if (e.code === 'NumpadAdd')      { stepRings( 1); e.preventDefault(); return }
  if (e.code === 'NumpadSubtract') { stepRings(-1); e.preventDefault(); return }
  switch (e.key.toLowerCase()) {
    case 'r':
      resetSliceView()
      reset3DSurfaceView()
      e.preventDefault()
      break
    case 'x': {   // toggle the crosshair via its checkbox so the UI stays in sync
      const chk = document.getElementById('crosshairChk')
      chk.checked = !chk.checked
      chk.dispatchEvent(new Event('change'))
      e.preventDefault()
      break
    }
    case 'p': {   // toggle Pivot@vertex via its checkbox so the UI stays in sync
      const chk = document.getElementById('pivotAtVertexChk')
      chk.checked = !chk.checked
      chk.dispatchEvent(new Event('change'))
      e.preventDefault()
      break
    }
    // Orthoslice navigation: arrows/PgUp/PgDn step through the three planes.
    case 'arrowup':    stepCrosshair(0, 0,  1); e.preventDefault(); break  // axial → superior
    case 'arrowdown':  stepCrosshair(0, 0, -1); e.preventDefault(); break  // axial → inferior
    case 'arrowright': stepCrosshair( 1, 0, 0); e.preventDefault(); break  // sagittal → right
    case 'arrowleft':  stepCrosshair(-1, 0, 0); e.preventDefault(); break  // sagittal → left
    case 'pageup':     stepCrosshair(0,  1, 0); e.preventDefault(); break  // coronal → anterior
    case 'pagedown':   stepCrosshair(0, -1, 0); e.preventDefault(); break  // coronal → posterior
    // Cortical depth: +/Home go deeper, -/End go shallower ('=' is unshifted '+').
    case '+':
    case '=':
    case 'home':       stepDepth( 1); e.preventDefault(); break
    case '-':
    case 'end':        stepDepth(-1); e.preventDefault(); break
  }
})

// ── depth-profile charts ──────────────────────────────────────────────────────
function makeChart(id, color, label, fill = false) {
  const chart = new Chart(document.getElementById(id), {
    type: 'line',
    data: { datasets: [
      {
        label, data: [],
        borderColor: color, backgroundColor: color+'28',
        pointRadius: 2, tension: 0.3, fill, parsing: false
      },
      { // +SD band — hidden from legend, only shown when >1 vertex selected
        data: [], borderColor: color, borderDash: [5,4], borderWidth: 1,
        pointRadius: 0, tension: 0.3, fill: false, parsing: false, _isSd: true
      },
      { // -SD band
        data: [], borderColor: color, borderDash: [5,4], borderWidth: 1,
        pointRadius: 0, tension: 0.3, fill: false, parsing: false, _isSd: true
      },
      { // normative (cohort) mean — always white, hidden until data exists
        label: 'Normative', data: [], borderColor: '#ffffff',
        pointRadius: 0, tension: 0.3, fill: false, parsing: false, borderWidth: 1.5
      },
      { // normative +SD band
        data: [], borderColor: '#ffffff', borderDash: [5,4], borderWidth: 1,
        pointRadius: 0, tension: 0.3, fill: false, parsing: false, _isSd: true
      },
      { // normative -SD band
        data: [], borderColor: '#ffffff', borderDash: [5,4], borderWidth: 1,
        pointRadius: 0, tension: 0.3, fill: false, parsing: false, _isSd: true
      },
    ]},
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      onClick: (evt, elements, chart) => setDepthFromChart(chart, evt.x),
      plugins: {
        legend: { display: true, labels: { color: '#dddddd', boxWidth: 10, font: {size:10},
          filter: (item, data) => !data.datasets[item.datasetIndex]?._isSd } },
        annotation: { annotations: { depthLine: {
          type: 'line', xMin: 0, xMax: 0,
          borderColor: ACCENT_YELLOW, borderWidth: 1.5, borderDash: [4,3]
        }}}
      },
      scales: {
        x: { type:'linear',
             title: { display:true, text:'Depth (mm)', color:'#dddddd' },
             ticks: { color:'#dddddd', maxTicksLimit:8, callback: v => v.toFixed(1) },
             grid:  { color:'#303030' } },
        y: { ticks: { color:'#dddddd', maxTicksLimit:5 }, grid: { color:'#303030' } }
      }
    }
  })
  chart.baseLabel = label
  return chart
}

function setDepthFromChart(chart, pixelX) {
  const mm  = chart.scales.x.getValueForPixel(pixelX)
  const sl  = document.getElementById('depthSlider')
  const d   = Math.max(0, Math.min(+sl.max, Math.round(mm / STEP_MM)))
  sl.value  = d
  setDepth(d)
}

chartLH   = makeChart('chart-lh',   LH_COLOR, 'LH')
chartRH   = makeChart('chart-rh',   RH_COLOR, 'RH')
chartAsym = makeChart('chart-asym', '#8af5a6', 'Asymmetry', true)
applyAsymYLimits()

function updateDepthMarker(mm) {
  if (!chartLH) return
  for (const chart of [chartLH, chartRH, chartAsym]) {
    const ann = chart.options.plugins?.annotation?.annotations?.depthLine
    if (!ann) continue
    ann.xMin = mm; ann.xMax = mm
    chart.update('none')
  }
}

function setProfiles(lhStat, rhStat, asymStat, count, lhArea, rhArea, normStat) {
  const toXY = vals => vals.map((v,i) => ({x: i*STEP_MM, y: v}))
  const entries = [
    [chartLH,   lhStat,   lhArea,  normStat?.lh],
    [chartRH,   rhStat,   rhArea,  normStat?.rh],
    [chartAsym, asymStat, null,    normStat?.asym],
  ]
  for (const [chart, stat, area, norm] of entries) {
    let label = chart.baseLabel
    if (count > 1) label += ` (n=${count})`
    if (area != null) label += ` [${area.toFixed(1)} mm²]`
    chart.data.datasets[0].label = label
    chart.data.datasets[0].data  = toXY(stat.mean)
    if (count > 1 && stat.sd) {
      chart.data.datasets[1].data = toXY(stat.mean.map((m,i) => m + stat.sd[i]))
      chart.data.datasets[2].data = toXY(stat.mean.map((m,i) => m - stat.sd[i]))
    } else {
      chart.data.datasets[1].data = []
      chart.data.datasets[2].data = []
    }

    if (norm) {
      chart.data.datasets[3].label = `Normative (N=${norm.n})`
      chart.data.datasets[3].data  = toXY(norm.mean)
      chart.data.datasets[4].data  = toXY(norm.mean.map((m,i) => m + norm.sd[i]))
      chart.data.datasets[5].data  = toXY(norm.mean.map((m,i) => m - norm.sd[i]))
    } else {
      chart.data.datasets[3].data = []
      chart.data.datasets[4].data = []
      chart.data.datasets[5].data = []
    }
  }
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


SURF_TYPE_FILENAMES = {
    'white':         lambda hemi, t: f'{hemi}_white_{t}.surf.gii',
    'pial':          lambda hemi, t: f'{hemi}_pial_{t}.surf.gii',
    'inflated':      lambda hemi, t: f'{hemi}_white_{t}_inflated.surf.gii',
    'very_inflated': lambda hemi, t: f'{hemi}_white_{t}_veryInflated.surf.gii',
}
SURF_TYPE_ORDER = ['white', 'pial', 'inflated', 'very_inflated', 'average_white', 'average_pial']


def find_surface_types(subjects_dir, subj_dir, template=TEMPLATE):
    """Discover available surface-type files for lh/rh, mirroring the MATLAB
    viewer's getSurfPath(): per-subject white/pial/inflated/very_inflated,
    plus fsaverage-style average_white/average_pial templates shared across
    subjects. Returns {surf_type: {'lh': path, 'rh': path}}, only including
    entries whose file actually exists."""
    surf_dir      = os.path.join(subj_dir, 'surf')
    templates_dir = os.path.join(subjects_dir, 'templates', 'surf')
    result = {}
    for surf_type, fname_fn in SURF_TYPE_FILENAMES.items():
        entry = {}
        for hemi in ('lh', 'rh'):
            p = os.path.join(surf_dir, fname_fn(hemi, template))
            if os.path.isfile(p):
                entry[hemi] = p
        if entry:
            result[surf_type] = entry
    for surf_type, prefix in (('average_white', 'white'), ('average_pial', 'pial')):
        entry = {}
        for hemi in ('lh', 'rh'):
            p = os.path.join(templates_dir, f'{hemi}_{prefix}.{template}.surf.gii')
            if os.path.isfile(p):
                entry[hemi] = p
        if entry:
            result[surf_type] = entry
    return result


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
# Split into a cheap in-memory "stats" pass (needed up front for every metric,
# so the dropdown/depth-slider/CLim inputs work before its overlay exists) and
# an expensive "materialize" pass (write the actual .func.gii + .f32 files),
# which only runs for a metric once it's actually requested.

def read_tsf_matrix(tsf_path):
    """Read a TSF file into a padded (n_vertices, n_depths) float32 matrix."""
    _, tracks = read_mrtrix_tsf(tsf_path)
    M = pad_to_matrix(tracks).astype(np.float32)
    return np.nan_to_num(M, nan=0.0)


def matrix_cal_range(M):
    finite = M[np.isfinite(M) & (M > 0)]
    cal_min = float(np.percentile(finite,  2)) if finite.size else 0.0
    cal_max = float(np.percentile(finite, 98)) if finite.size else 1.0
    return round(cal_min, 4), round(cal_max, 4)


def compute_asym_matrix(lh_M, rh_M):
    """Compute asymmetry index (LH-RH)/mean(LH,RH)."""
    LH = lh_M.astype(np.float64)
    RH = rh_M.astype(np.float64)
    denom = (LH + RH) / 2.0
    with np.errstate(divide='ignore', invalid='ignore'):
        A = np.where(denom != 0.0, (LH - RH) / denom, 0.0).astype(np.float32)
    return np.nan_to_num(A, nan=0.0, posinf=0.0, neginf=0.0)


def asym_cal_range():
    # Fixed symmetric range for the asymmetry index; the front-end uses this for
    # both the surface color limits and the asym plot's y-axis.
    return -1.0, 1.0


def write_func_gii(M, out_path):
    intent  = nib.nifti1.intent_codes['NIFTI_INTENT_NONE']
    darrays = [nib.gifti.GiftiDataArray(M[:, d], intent=intent, datatype='NIFTI_TYPE_FLOAT32')
               for d in range(M.shape[1])]
    nib.save(nib.gifti.GiftiImage(darrays=darrays), out_path)


def scan_overlay_stats(tsf_metrics):
    """Read every metric's TSF data and compute its stats, without writing any
    files. Returns (info, arrays) where arrays[metric] = (lh_M, rh_M)."""
    info = {}
    arrays = {}
    for metric, hemis in tsf_metrics.items():
        lh_M = read_tsf_matrix(hemis['lh'])
        rh_M = read_tsf_matrix(hemis['rh'])
        cmin, cmax = matrix_cal_range(lh_M)
        amin, amax = asym_cal_range()
        info[metric] = {
            'n_depths':     lh_M.shape[1],
            'cal_min':      cmin,
            'cal_max':      cmax,
            'cal_min_asym': amin,
            'cal_max_asym': amax,
        }
        arrays[metric] = (lh_M, rh_M)
        print(f'  {metric}: {lh_M.shape[1]} depths  [{cmin:.3f}, {cmax:.3f}]  asym [{amin:.3f}, {amax:.3f}]')
    return info, arrays


def materialize_overlay(metric, lh_M, rh_M, out_dir, template=TEMPLATE):
    """Write the func.gii + binary matrix files for one metric.
    Returns a list of (url_path, file_path) pairs to merge into file_map."""
    lh_gii   = os.path.join(out_dir, f'lh_{template}_{metric}.func.gii')
    rh_gii   = os.path.join(out_dir, f'rh_{template}_{metric}.func.gii')
    asym_gii = os.path.join(out_dir, f'asym_{template}_{metric}.func.gii')
    lh_mat   = os.path.join(out_dir, f'lh_{template}_{metric}_matrix.f32')
    rh_mat   = os.path.join(out_dir, f'rh_{template}_{metric}_matrix.f32')
    asym_mat = os.path.join(out_dir, f'asym_{template}_{metric}_matrix.f32')

    write_func_gii(lh_M, lh_gii);  lh_M.tofile(lh_mat)
    write_func_gii(rh_M, rh_gii);  rh_M.tofile(rh_mat)
    A = compute_asym_matrix(lh_M, rh_M)
    write_func_gii(A, asym_gii);   A.tofile(asym_mat)

    paths = (lh_gii, rh_gii, asym_gii, lh_mat, rh_mat, asym_mat)
    return [(f'/data/{os.path.basename(p)}', p) for p in paths]


# ── normative (cohort) data ────────────────────────────────────────────────────
# Reads the HDF5 file produced by cortical_create_normative_data_from_tsf.py
# (per-vertex, per-depth, per-subject, per-metric raw values for lh/rh) and
# reduces it to per-vertex mean/std across the cohort — the "univariate"
# normative comparison. This is independent of the current subject's own
# per-metric materialization, so it can run for every metric the cohort has,
# regardless of which of the subject's own overlays have been materialized.
#
# Split into a cheap metadata-only scan (used at startup, so a large cohort
# file doesn't slow down server launch) and a per-metric materialize step
# that actually computes mean/std — run lazily, only once the client asks
# for that metric's normative data (mirroring materialize_overlay's lazy
# per-metric conversion), triggered by the "Show normative" toggle rather
# than happening unconditionally for every metric on every launch.

def scan_normative_info(subjects_dir, available_metrics, template=TEMPLATE):
    """Cheap: report which metrics have cohort normative data available and
    their depth-axis sizes, without computing any mean/std. Returns
    info[metric] = {'n_subjects': int, 'lh': {'n_depths': int}, 'rh': {...},
    'asym': {...}}; {} if no cohort file is present."""
    h5_path = os.path.join(subjects_dir, 'templates', 'normative', f'{template}_multivariate.h5')
    if not os.path.isfile(h5_path):
        return {}

    info = {}
    with h5py.File(h5_path, 'r') as h5f:
        cohort_metrics = list(h5f['metrics'].asstr()[:])
        n_subjects = int(h5f['subjects'].shape[0])
        lh_depths  = h5f['lh_M'].shape[1]
        rh_depths  = h5f['rh_M'].shape[1]
        asym_depths = min(lh_depths, rh_depths)
        for metric in available_metrics:
            if metric not in cohort_metrics:
                continue
            info[metric] = {
                'n_subjects': n_subjects,
                'lh':   {'n_depths': int(lh_depths)},
                'rh':   {'n_depths': int(rh_depths)},
                'asym': {'n_depths': int(asym_depths)},
            }
    return info


def materialize_normative(subjects_dir, metric, out_dir, template=TEMPLATE):
    """Compute per-vertex lh/rh/asym mean+std across the cohort for ONE
    metric and write flat float32 (nVerts*nDepths) files, using the same
    layout as the per-subject _matrix.f32 files. Returns a list of
    (url_path, file_path) pairs to merge into file_map."""
    h5_path = os.path.join(subjects_dir, 'templates', 'normative', f'{template}_multivariate.h5')
    file_entries = []
    with h5py.File(h5_path, 'r') as h5f:
        cohort_metrics = list(h5f['metrics'].asstr()[:])
        n_subjects = h5f['subjects'].shape[0]
        idx = cohort_metrics.index(metric)
        print(f'  normative {metric} (N={n_subjects}) …')
        lh_stack = h5f['lh_M'][:, :, :, idx]   # (nVerts, nDepthsL, nSubjects)
        rh_stack = h5f['rh_M'][:, :, :, idx]   # (nVerts, nDepthsR, nSubjects)

        # Some ragged tail depths have zero subjects contributing (no
        # streamline reaches that deep anywhere) — nanmean/nanstd warn on
        # those all-NaN slices, which is expected and harmless here.
        with np.errstate(invalid='ignore'), warnings.catch_warnings():
            warnings.simplefilter('ignore', category=RuntimeWarning)
            lh_mean = np.nanmean(lh_stack, axis=2).astype(np.float32)
            lh_std  = np.nanstd(lh_stack,  axis=2).astype(np.float32)
            rh_mean = np.nanmean(rh_stack, axis=2).astype(np.float32)
            rh_std  = np.nanstd(rh_stack,  axis=2).astype(np.float32)

            # Per-subject asymmetry (elementwise, so this works fine on the
            # 3D subject-stacked arrays directly), then averaged over subjects
            common_d = min(lh_stack.shape[1], rh_stack.shape[1])
            asym_stack = compute_asym_matrix(lh_stack[:, :common_d, :], rh_stack[:, :common_d, :])
            asym_mean = np.nanmean(asym_stack, axis=2).astype(np.float32)
            asym_std  = np.nanstd(asym_stack,  axis=2).astype(np.float32)

        arrays = {'lh': (lh_mean, lh_std), 'rh': (rh_mean, rh_std), 'asym': (asym_mean, asym_std)}
        for kind, (mean_arr, std_arr) in arrays.items():
            mean_path = os.path.join(out_dir, f'normative_{kind}_{metric}_mean.f32')
            std_path  = os.path.join(out_dir, f'normative_{kind}_{metric}_std.f32')
            mean_arr.tofile(mean_path)
            std_arr.tofile(std_path)
            file_entries.append((f'/data/{os.path.basename(mean_path)}', mean_path))
            file_entries.append((f'/data/{os.path.basename(std_path)}',  std_path))

    return file_entries


# ── HTML generation ───────────────────────────────────────────────────────────

def make_html(subj_id, vol_path, lh_path, rh_path, overlay_info, port, surf_types=None, normative_info=None, template=TEMPLATE):
    base = f'http://localhost:{port}/data'

    volumes = []
    if vol_path:
        volumes.append({'url': f'{base}/{os.path.basename(vol_path)}',
                        'colormap': 'gray', 'opacity': 1})
    # Per-hemisphere accent colors; the front-end derives the LH/RH plot line
    # colors from these same rgba255 values so surfaces and plots stay in sync.
    surfs = []
    if lh_path:
        surfs.append({'url': f'{base}/{os.path.basename(lh_path)}',
                      'rgba255': [102, 179, 255, 255], 'hemi': 'lh'})   # #66B3FF
    if rh_path:
        surfs.append({'url': f'{base}/{os.path.basename(rh_path)}',
                      'rgba255': [255, 133, 77, 255], 'hemi': 'rh'})    # #FF854D

    surf_types_urls = {
        surf_type: {hemi: f'{base}/{os.path.basename(p)}' for hemi, p in hemis.items()}
        for surf_type, hemis in (surf_types or {}).items()
    }

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
        ('__SURF_TYPES_JSON__', json.dumps(surf_types_urls)),
        ('__NORMATIVE_JSON__', json.dumps(normative_info or {})),
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

def make_handler(html_bytes, file_map, overlay_arrays, materialized, out_dir,
                  subjects_dir=None, normative_materialized=None, template=TEMPLATE):
    # Matches lh_<template>_<metric>.func.gii, rh_..., asym_..., and the
    # corresponding _matrix.f32 files, isolating <metric>.
    overlay_re = re.compile(
        r'^(?:lh|rh|asym)_' + re.escape(template) + r'_(.+?)(?:\.func\.gii|_matrix\.f32)$'
    )
    # Matches normative_<lh|rh|asym>_<metric>_<mean|std>.f32, isolating <metric>.
    normative_re = re.compile(r'^normative_(?:lh|rh|asym)_(.+?)_(?:mean|std)\.f32$')
    if normative_materialized is None:
        normative_materialized = set()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split('?')[0]
            if path in ('/', '/index.html'):
                self._reply(200, 'text/html; charset=utf-8', html_bytes)
                return
            if path not in file_map:
                self._materialize_if_needed(path)
            if path in file_map:
                with open(file_map[path], 'rb') as fh:
                    # Every /data/ file is content-addressed by hemi/template/
                    # metric/surf-type and never changes once written, so the
                    # browser can cache it forever — this matters a lot when
                    # switching surface type, since the other panels' meshes
                    # get reloaded from the same URLs without re-fetching.
                    self._reply(200, 'application/octet-stream', fh.read(), cacheable=True)
            else:
                self._reply(404, 'text/plain', b'Not found\n')

        def _materialize_if_needed(self, path):
            """First request for a not-yet-generated metric's overlay (or
            normative comparison) triggers on-demand conversion; subsequent
            requests just hit file_map."""
            fname = path.rsplit('/', 1)[-1]

            m = overlay_re.match(fname)
            if m:
                metric = m.group(1)
                if metric in materialized or metric not in overlay_arrays:
                    return
                lh_M, rh_M = overlay_arrays[metric]
                for url, fpath in materialize_overlay(metric, lh_M, rh_M, out_dir, template):
                    file_map[url] = fpath
                materialized.add(metric)
                return

            m = normative_re.match(fname)
            if m and subjects_dir:
                metric = m.group(1)
                if metric in normative_materialized:
                    return
                for url, fpath in materialize_normative(subjects_dir, metric, out_dir, template):
                    file_map[url] = fpath
                normative_materialized.add(metric)

        def _reply(self, code, ctype, data, cacheable=False):
            self.send_response(code)
            self.send_header('Content-Type',                ctype)
            self.send_header('Content-Length',              str(len(data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            if cacheable:
                self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
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
    surf_types  = find_surface_types(args.subjects_dir, subj_dir)

    print(f'Subject  : {args.subj_id}')
    print(f'Volume   : {vol_path  or "NOT FOUND"}')
    print(f'LH surf  : {lh_path   or "NOT FOUND"}')
    print(f'RH surf  : {rh_path   or "NOT FOUND"}')
    print(f'Metrics  : {list(tsf_metrics) or "none"}')
    print(f'Surf types: {list(surf_types) or "none"}')

    out_dir = tempfile.mkdtemp(prefix='cortical_browser_')
    print(f'\nScanning {len(tsf_metrics)} metric(s) (stats only, no conversion yet)…')
    overlay_info, overlay_arrays = scan_overlay_stats(tsf_metrics)

    # Build file map: surfaces and volume are ready immediately; overlays are
    # materialized lazily by the request handler as each metric is selected —
    # except the default (first) metric, which we prepare now so the initial
    # page load has something to show right away.
    file_map = {}
    for p in (vol_path, lh_path, rh_path):
        if p:
            file_map[f'/data/{os.path.basename(p)}'] = p
    for hemis in surf_types.values():
        for p in hemis.values():
            file_map[f'/data/{os.path.basename(p)}'] = p

    materialized = set()
    first_metric = next(iter(tsf_metrics), None)
    if first_metric:
        print(f'Materializing default metric: {first_metric}')
        lh_M, rh_M = overlay_arrays[first_metric]
        for url, fpath in materialize_overlay(first_metric, lh_M, rh_M, out_dir):
            file_map[url] = fpath
        materialized.add(first_metric)

    print('\nChecking for cohort normative data (metadata only — computed lazily on request)…')
    normative_info = scan_normative_info(args.subjects_dir, tsf_metrics.keys())
    print(f'Normative metrics: {list(normative_info) or "none"}')
    normative_materialized = set()

    html_bytes = make_html(
        args.subj_id, vol_path, lh_path, rh_path,
        overlay_info, args.port, surf_types, normative_info
    ).encode('utf-8')

    server = HTTPServer(('localhost', args.port),
        make_handler(html_bytes, file_map, overlay_arrays, materialized, out_dir,
                      args.subjects_dir, normative_materialized))
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
