import * as niivue from "__NIIVUE_CDN__"

// ── injected by Python ────────────────────────────────────────────────────────
const VOLUMES  = __VOLUMES_JSON__
const SURFS    = __SURFS_JSON__
const SURF_TYPES = __SURF_TYPES_JSON__
const STREAMLINES = __STREAMLINES_JSON__
const DWI_AVAILABLE = __DWI_AVAILABLE_JSON__
const NORMATIVE = __NORMATIVE_JSON__
const METRICS  = __METRICS_JSON__
const BASE_URL = "__BASE_URL__"
// Per-launch cache-buster: appended to every /data/ fetch so an immutable-cached
// file from a previous subject (same port, same URL) can't leak into this one.
const CACHE_BUST = "__CACHE_BUST__"
const Q = CACHE_BUST ? `?v=${CACHE_BUST}` : ''
const TEMPLATE = "__TEMPLATE__"
const STEP_MM  = __STEP_MM__

// Selected-vertex accent color, shared across the vertex box (CSS --accent-yellow),
// the orthoslice crosshair, and the plots' depth reference line.
const ACCENT_YELLOW = '#F5C842'
const ACCENT_YELLOW_RGBA = [0xF5/255, 0xC8/255, 0x42/255, 1]

// Shared light-gray text color for all plot axis labels, titles, and legends.
const PLOT_TEXT = '#dddddd'

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

// ── multivariate (Mahalanobis / z-score) explorer state ──────────────────────
// Available only when the server found cohort data (same gate as normative).
const MV_AVAILABLE = Object.keys(NORMATIVE).length > 0
// Off by default: the per-vertex Mahalanobis fit re-estimates a cohort
// covariance from scratch on every request, which gets slower as more
// control subjects are added — not worth paying on every vertex jump unless
// the panels are actually being looked at.
let showMultivariate = false
let mvZlim = 3            // max |z| on radar / z-bar panels (user-editable)
let mvMahalLim = 50       // max Mahalanobis distance on the depth panel
const mvCache = {}        // "vertex:rings" -> parsed /mahal payload
let mvCurrent = null      // payload for the currently selected vertex

// Hoisted so updateDepthMarker is safe to call before makeChart runs
var chartLH, chartRH, chartAsym
var chartMahal, chartRadar, chartZBar

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
const hexToRgba = (hex, alpha) => {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`
}
const LH_COLOR = LH_SURF ? rgba255ToHex(LH_SURF.rgba255) : '#66B3FF'
const RH_COLOR = RH_SURF ? rgba255ToHex(RH_SURF.rgba255) : '#FF854D'

// Independently-selectable surface geometry per panel (white/pial/inflated/
// very_inflated/average_white/average_pial) — all share the same surface
// template topology, so switching only changes vertex coordinates, not data mapping.
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
  meshThicknessOn2D: 2, multiplanarLayout: 'row',
  isColorbar: true,           // one colorbar for the ortho view (NiiVue draws it instance-wide, not per-panel)
  showColorbarBorder: false   // drop the outline around the colorbar
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
// A flat (single-color) colormap: every LUT index maps to the same RGB, so a
// layer using it always paints one solid color regardless of its cal_min/max
// or the data value — used below to mark "no data" vertices with each panel's
// own base tint, so they read as if no overlay were ever applied there.
function buildFlatCmap(r, g, b) {
  return { R: [r, r], G: [g, g], B: [b, b], A: [255, 255] }
}
const CUSTOM_CMAPS = {
  bwr:  buildDivergingCmap(  0,   0, 255, 255,   0,   0),  // blue-white-red
  gwr:  buildDivergingCmap(  0, 180,   0, 255,   0,   0),  // green-white-red
  cwr:  buildDivergingCmap(  0, 200, 200, 255,   0,   0),  // cyan-white-red
  flat_lh: buildFlatCmap(...((LH_SURF?.rgba255 ?? [102, 179, 255]).slice(0, 3))),
  flat_rh: buildFlatCmap(...((RH_SURF?.rgba255 ?? [255, 133, 77]).slice(0, 3))),
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

// Colormaps for scalar data, shared by BOTH the surface data overlays (cmapSel)
// and the orthoslice volume (volCmapSel) so the two menus are identical. Built
// from NiiVue's full registered set (so lipari, navia, etc. are all included),
// minus the CT-specific clinical maps and our own diverging maps — the latter
// live on the asymmetry menu (cmapAsymSel), since asymmetry is signed and needs
// a white-centered map, not a sequential one.
const CUSTOM_CMAP_NAMES = new Set(Object.keys(CUSTOM_CMAPS))
const SURFACE_CMAPS = (nvSlices.colormaps ? nvSlices.colormaps() : ['gray'])
  .filter(n => !/^ct[-_]/i.test(n) && !CUSTOM_CMAP_NAMES.has(n))
  .sort()
function fillCmapSelect(sel, selected) {
  sel.innerHTML = SURFACE_CMAPS.map(n =>
    `<option value="${n}"${n === selected ? ' selected' : ''}>${n}</option>`).join('')
}
fillCmapSelect(document.getElementById('cmapSel'), currentCmap)

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
  return [{ url: `${BASE_URL}/${hemi}_${TEMPLATE}_${metric}.func.gii${Q}`,
            colormap: currentCmap, colormapInvert: dataInvert,
            opacity: layerOpacity, cal_min: currentClimMin, cal_max: currentClimMax }]
}
function layerAsymFor(metric) {
  const info = metric ? METRICS[metric] : null
  if (!info) return []
  return [{ url: `${BASE_URL}/asym_${TEMPLATE}_${metric}.func.gii${Q}`,
            colormap: currentCmapAsym, colormapInvert: asymInvert,
            opacity: layerOpacity, cal_min: currentAsymMin, cal_max: currentAsymMax }]
}

// NiiVue's mesh layer loader only reads a fixed whitelist of properties off the
// layer descriptor (opacity/colormap/colormapNegative/useNegativeCmap/cal_min/
// cal_max) — isTransparentBelowCalMin isn't among them and is hardcoded true at
// load time, so it must be flipped afterward via setMeshLayerProperty (same
// reason colormapInvert is re-applied via setMeshLayerProperty elsewhere rather
// than trusted from the descriptor). Without this, any vertex below the
// colormap's cal_min renders fully transparent, indistinguishable from "no
// data"; we want it clamped to the colormap's lowest color instead.
function disableTransparentBelowCalMin(nv) {
  const mesh = nv.meshes[0]
  if (mesh?.layers?.length) nv.setMeshLayerProperty(mesh.id, 0, 'isTransparentBelowCalMin', false)
}

// ── "no data" mask overlay ────────────────────────────────────────────────────
// A second stacked layer that flags vertices where the underlying TSF matrix
// is NaN at the current depth (no streamline reached this far / an explicitly
// invalid sample) — distinct from a genuinely low-but-valid value, which the
// data layer above already clamps to its lowest color rather than hiding.
// This pipeline has no true per-vertex alpha, so the closest thing to
// "transparent" it can do is paint a solid color; using each panel's own flat
// base tint (flat_lh/flat_rh, registered above) makes a "no data" vertex read
// as if no data overlay were ever applied there. mnCal for this layer is fixed
// at 0.5 (independent of the live, user-adjustable data cal_min), so a mask
// value of 0 (valid) always cleanly skips — leaving the data layer's color
// untouched — while 1 (invalid) always paints.
function invalidMask(matArray, nd, depth) {
  const nVerts = matArray.length / nd
  const mask = new Float32Array(nVerts)
  for (let vi = 0; vi < nVerts; vi++) mask[vi] = Number.isNaN(matArray[vi * nd + depth]) ? 1 : 0
  return mask
}
function applyInvalidMask(nv, matArray, nd, depth, cmapName) {
  const mesh = nv.meshes[0]
  if (!mesh?.layers?.length || !matArray) return
  mesh.layers[1] = {
    values: invalidMask(matArray, nd, depth), nFrame4D: 1, frame4D: 0,
    colormap: cmapName, colormapNegative: 'winter', useNegativeCmap: false,
    colormapInvert: false, colormapType: 0, colormapLabel: null,
    isTransparentBelowCalMin: true, isAdditiveBlend: false, colorbarVisible: false,
    outlineBorder: 0, opacity: 1, cal_min: 0.5, cal_max: 1,
    cal_minNeg: NaN, cal_maxNeg: NaN, global_min: 0, global_max: 1,
  }
  mesh.updateMesh(nv.gl)
}
const MASK_CMAP_FOR = { lh: 'flat_lh', rh: 'flat_rh', asym: 'flat_lh' }   // nvAsym shares LH geometry/base color
function refreshInvalidMasks(depth) {
  if (!currentMetric) return
  const nd = METRICS[currentMetric].n_depths
  for (const [hemi, nv] of [['lh', nvLhL], ['rh', nvRhL], ['asym', nvAsym]]) {
    const mat = matCache[`${hemi}_${currentMetric}`]
    if (mat) applyInvalidMask(nv, mat, nd, depth, MASK_CMAP_FOR[hemi])
  }
}

async function loadLhPanel(metric) {
  if (!LH_SURF || !lhSurfUrl) return
  console.time('loadLhPanel')
  markerMeshes.delete(nvLhL); neighborMeshes.delete(nvLhL)
  await nvLhL.loadMeshes([{ url: lhSurfUrl, rgba255: LH_SURF.rgba255, layers: layerDataFor('lh', metric) }])
  disableTransparentBelowCalMin(nvLhL)
  applyShader(nvLhL, currentShader)
  console.timeEnd('loadLhPanel')
}

async function loadRhPanel(metric) {
  if (!RH_SURF || !rhSurfUrl) return
  console.time('loadRhPanel')
  markerMeshes.delete(nvRhL); neighborMeshes.delete(nvRhL)
  await nvRhL.loadMeshes([{ url: rhSurfUrl, rgba255: RH_SURF.rgba255, layers: layerDataFor('rh', metric) }])
  disableTransparentBelowCalMin(nvRhL)
  applyShader(nvRhL, currentShader)
  console.timeEnd('loadRhPanel')
}

async function loadAsymPanel(metric) {
  if (!LH_SURF || !asymSurfUrl) return
  console.time('loadAsymPanel')
  markerMeshes.delete(nvAsym); neighborMeshes.delete(nvAsym)
  await nvAsym.loadMeshes([{ url: asymSurfUrl, rgba255: LH_SURF.rgba255, layers: layerAsymFor(metric) }])
  disableTransparentBelowCalMin(nvAsym)
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

// LH/RH Laplace white-matter streamlines (.tck), loaded on demand
// from the "Load streamlines" button and overlaid on the orthoslices only
// (nvSlices, not the 3-D surface panels). meshThicknessOn2D clips every mesh
// in nvSlices — contours and streamlines alike — to a slab around each 2-D slice
// plane, so the streamlines render as their intersection with that plane.
const STREAMLINE_THICKNESS_MM = 2
let streamlineMeshes = null    // { lh, rh } once loaded
let streamlinesVisible = true  // toggled by the "Show" checkbox once streamlines are loaded

async function ensureStreamlines() {
  if (streamlineMeshes) return streamlineMeshes
  console.time('ensureStreamlines')
  const [lhMesh, rhMesh] = await Promise.all([
    STREAMLINES.lh ? niivue.NVMesh.loadFromUrl({ url: STREAMLINES.lh, gl: nvSlices.gl, rgba255: LH_SURF.rgba255 }) : null,
    STREAMLINES.rh ? niivue.NVMesh.loadFromUrl({ url: STREAMLINES.rh, gl: nvSlices.gl, rgba255: RH_SURF.rgba255 }) : null,
  ])
  for (const m of [lhMesh, rhMesh]) if (m) nvSlices.addMesh(m)
  streamlineMeshes = { lh: lhMesh, rh: rhMesh }
  nvSlices.setMeshThicknessOn2D(STREAMLINE_THICKNESS_MM)
  applyStreamlineVisibility()
  console.timeEnd('ensureStreamlines')
  return streamlineMeshes
}

function applyStreamlineVisibility() {
  if (!streamlineMeshes) return
  const op = streamlinesVisible ? 1 : 0
  for (const m of [streamlineMeshes.lh, streamlineMeshes.rh]) if (m) nvSlices.setMeshProperty(m.id, 'opacity', op)
  nvSlices.drawScene()
}

// Per-streamline filtering: the streamline files are one streamline per vertex of
// the same ico6-sym mesh used everywhere else (LH/RH share vertex indexing —
// see ringSet's reuse across lh/rh matrices in selectVertex()), so a vertex ID
// is also that vertex's streamline index. NVMesh has no built-in "show only
// these streamline indices" call, but its dps/dpsThreshold mechanism (data-
// per-streamline + a cutoff, normally used to threshold streamlines by a
// scalar like FA) can be repurposed: give each streamline a 0/1 "selected"
// flag as its dps value and threshold at 0.5, so only flagged streamlines
// survive into the index buffer that updateFibers() rebuilds on every
// setMeshProperty call. Passing NaN as the threshold (its documented default)
// skips that filtering step entirely, i.e. shows every streamline.
function setStreamlineSelection(vertexIds) {
  if (!streamlineMeshes) return
  const selected = new Set(vertexIds)
  for (const m of [streamlineMeshes.lh, streamlineMeshes.rh]) {
    if (!m?.offsetPt0) continue
    const nStreamlines = m.offsetPt0.length - 1
    const flags = new Float32Array(nStreamlines)
    for (const v of selected) if (v >= 0 && v < nStreamlines) flags[v] = 1
    m.dps = [{ id: 'vertex-selection', vals: flags }]
    nvSlices.setMeshProperty(m.id, 'dpsThreshold', 0.5)
  }
}

function showAllStreamlines() {
  if (!streamlineMeshes) return
  for (const m of [streamlineMeshes.lh, streamlineMeshes.rh]) {
    if (m) nvSlices.setMeshProperty(m.id, 'dpsThreshold', NaN)
  }
}

// Driven by the "Streamlines" mode selector (All / Selected vertex) and
// re-applied on every vertex/rings selection change. A no-op until streamlines
// are actually loaded (streamlineMeshes is null until then).
function applyStreamlineSelection() {
  if (!streamlineMeshes) return
  const mode = document.getElementById('streamlineModeSel').value
  if (mode === 'all' || currentVertex === null) {
    showAllStreamlines()
  } else {
    setStreamlineSelection(selectedVertices)
  }
}

// Color selector: "direction" uses NiiVue's built-in start-to-end direction
// coloring (fiberColor 'Global', the NVMesh default); "fixed" recolors every
// streamline with a single user-chosen color via the color picker.
function hexToRgba255(hex) {
  const n = parseInt(hex.slice(1), 16)
  return new Uint8Array([(n >> 16) & 255, (n >> 8) & 255, n & 255, 255])
}
function applyStreamlineColor() {
  if (!streamlineMeshes) return
  const mode = document.getElementById('streamlineColorSel').value
  const picker = document.getElementById('streamlineColorPicker')
  picker.style.display = mode === 'fixed' ? '' : 'none'
  for (const m of [streamlineMeshes.lh, streamlineMeshes.rh]) {
    if (!m) continue
    if (mode === 'fixed') {
      m.rgba255 = hexToRgba255(picker.value)
      nvSlices.setMeshProperty(m.id, 'fiberColor', 'Fixed')
    } else {
      nvSlices.setMeshProperty(m.id, 'fiberColor', 'Global')
    }
  }
  nvSlices.drawScene()
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
  const r = await fetch(`${BASE_URL}/${hemi}_${TEMPLATE}_${metric}_matrix.f32${Q}`)
  matCache[key] = new Float32Array(await r.arrayBuffer())
  return matCache[key]
}

// ── normative (cohort) matrix cache ──────────────────────────────────────────
const normCache = {}

async function ensureNormativeMatrix(kind, metric, stat) {
  const key = `${kind}_${metric}_${stat}`
  if (normCache[key]) return normCache[key]
  const r = await fetch(`${BASE_URL}/normative_${kind}_${metric}_${stat}.f32${Q}`)
  normCache[key] = new Float32Array(await r.arrayBuffer())
  return normCache[key]
}

async function normativeRingStat(kind, metric, ringSet) {
  const info = NORMATIVE[metric]?.[kind]
  if (!info) return null

  // A lone vertex needs no cross-vertex aggregation, so the precomputed
  // per-vertex cohort mean/std is already exact — serve it directly rather
  // than round-tripping to the server.
  if (ringSet.length <= 1) {
    const nd = info.n_depths
    const vi = ringSet[0]
    const [meanMat, stdMat] = await Promise.all([
      ensureNormativeMatrix(kind, metric, 'mean'),
      ensureNormativeMatrix(kind, metric, 'std'),
    ])
    const mean = new Array(nd), sd = new Array(nd)
    for (let d = 0; d < nd; d++) {
      mean[d] = meanMat[vi*nd+d]
      sd[d]   = stdMat[vi*nd+d]
    }
    return { mean, sd, n: new Array(nd).fill(NORMATIVE[metric].n_subjects) }
  }

  // >1 vertex: the SD of each control subject's own vertex-averaged profile
  // is NOT the average of the per-vertex cohort SDs (mean-of-SDs != SD-of-
  // means), so this needs the raw per-subject stack — computed fresh from
  // the cohort h5 file on the server (see compute_normative_ring_stat).
  const r = await fetch(`/normative_ring?metric=${metric}&kind=${kind}&vertices=${ringSet.join(',')}`)
  if (!r.ok) return null
  return r.json()
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
    ? nvSlices.loadVolumes([{ url: VOL_URL, colormap: 'bone', opacity: 1 }])
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
// Instance callback (not opts) — NiiVue invokes this.onLocationChange(data).
// Show the crosshair position in both world (mm) and voxel coords, plus the
// shown volume's intensity value there.
nvSlices.onLocationChange = d => {
  const mm = d.mm, vox = d.vox
  const lines = []
  if (mm)  lines.push(`${mm[0].toFixed(1)},${mm[1].toFixed(1)},${mm[2].toFixed(1)} mm`)
  if (vox) lines.push(`${Math.round(vox[0])},${Math.round(vox[1])},${Math.round(vox[2])} vox`)
  const v = d.values && d.values[0]
  if (v && isFinite(v.value)) lines.push(`value=${(+v.value).toPrecision(4)}`)
  document.getElementById('pos-display').textContent = lines.join('\n')
  updateCutawayClipPlanes()   // keep the 3-D cutaway centered on the crosshair; no-op unless enabled
}

// ── 3-D cutaway (crosshair-centered clip planes) ──────────────────────────────
// NiiVue's 3-D panel is always a volume raycast — there's no built-in mode that
// shows just the three 2-D slices alone. Its multi-clip-plane cutaway
// (isClipPlanesCutaway) is the native building block that gets closest: up to 6
// clip planes are ANDed together in the raycaster, and cutaway mode removes only
// the one region where ALL of them agree, rather than the usual single-sided
// clip. Three axis-aligned planes positioned at the crosshair therefore carve
// away just the one octant nearest the crosshair, opening the render to reveal
// the orthogonal cut surfaces while the rest of the volume stays fully rendered.
let cutawayEnabled = false
let cutawayInverted = false
nvSlices.opts.isClipPlanesCutaway = true
// NiiVue's own C/P clip-plane hotkeys are bound to the orthoslice canvas itself
// (focused whenever it's clicked) and operate on a single freeform clip plane —
// they know nothing about our crosshair-synced 3-plane cutaway and would fight
// it (KeyP also collides with this app's Pivot@vertex shortcut). Blanked out
// here in favor of our own 'c' shortcut below, driven off the checkbox.
nvSlices.opts.clipPlaneHotKey = ''
nvSlices.opts.cycleClipPlaneHotKey = ''
// [azimuth, elevation] for axis-aligned planes — the same values NiiVue's own
// clip-plane presets use for RIGHT / ANTERIOR / SUPERIOR (see CLIP_PLANE_PRESETS
// in its source). depth is computed per-crosshair-position below.
const CUTAWAY_AZI_ELEV = [[90, 0], [180, 0], [0, 90]]
function updateCutawayClipPlanes() {
  if (!cutawayEnabled || !nvSlices.volumes.length) return
  const frac = nvSlices.scene.crosshairPos   // [x, y, z] in 0..1 volume-fraction space
  const depthAziElevs = CUTAWAY_AZI_ELEV.map(([azimuth, elevation]) => {
    // Same sph2cartDeg NiiVue itself uses to turn azimuth/elevation into a clip
    // normal, so depth = normal · (crosshair - center) lands the plane exactly
    // on the crosshair without having to hand-derive the axis/sign convention.
    const n = niivue.NVUtilities.sph2cartDeg(azimuth, elevation)
    const depth = n[0] * (frac[0] - 0.5) + n[1] * (frac[1] - 0.5) + n[2] * (frac[2] - 0.5)
    if (!cutawayInverted) return [depth, azimuth, elevation]
    // Invert = remove the opposite octant instead. Negating the clip normal
    // flips which side of each plane is cut away; for this azimuth/elevation
    // convention that's azimuth+180/elevation negated (the spherical antipode),
    // and the plane stays anchored at the same crosshair position by also
    // negating depth (verified algebraically against NiiVue's sph2cartDeg, not
    // just assumed — sph2cartDeg(azi+180, -elev) === -sph2cartDeg(azi, elev)).
    return [-depth, (azimuth + 180) % 360, -elevation]
  })
  nvSlices.setClipPlanes(depthAziElevs)
}
function disableCutawayClipPlanes() {
  nvSlices.setClipPlanes([[2, 0, 0], [2, 0, 0], [2, 0, 0]])   // depth=2 is NiiVue's "off" sentinel
}
document.getElementById('cutaway3DChk').addEventListener('change', function() {
  cutawayEnabled = this.checked
  if (cutawayEnabled) updateCutawayClipPlanes()
  else disableCutawayClipPlanes()
})
document.getElementById('cutawayInvertChk').addEventListener('change', function() {
  cutawayInverted = this.checked
  updateCutawayClipPlanes()   // no-op if cutaway isn't currently enabled
})
nvSlices.setSliceType(nvSlices.sliceTypeMultiplanar)
nvSlices.setRadiologicalConvention(true)
nvSlices.setCrosshairColor(ACCENT_YELLOW_RGBA)   // match selected-vertex color
nvSlices.setCrosshairWidth(0.5)                   // thinner than the default 1px
// Right-drag brightness/contrast: NiiVue's default right-button gesture
// (DRAG_MODE.contrast) draws a box and auto-windows to that box's intensity
// range — unlike the up/down=brightness, left/right=contrast drag every other
// neuroimaging viewer uses. DRAG_MODE.windowing is that familiar gesture
// (vertical = level/brightness, horizontal = window width/contrast); only
// rightButton is overridden here, so left-click crosshair placement and the
// scroll-to-zoom/pan bindings elsewhere are untouched. onIntensityChange
// (wired below to syncVolClipInputs) fires for this drag mode too, so the
// clip-min/max sidebar inputs stay in sync automatically.
nvSlices.setMouseEventConfig({ rightButton: niivue.DRAG_MODE.windowing })
// windowingGainFactor scales pixels-dragged -> intensity-units-changed (no
// dedicated setter; NiiVue reads opts.windowingGainFactor fresh on every drag
// move). Default is 2 (fast); dialed down here since a full-canvas drag was
// blowing past the intensity range almost immediately. Raise/lower to taste.
nvSlices.opts.windowingGainFactor = 0.4

// ── orthoslice volume selector ────────────────────────────────────────────────
// The dropdown chooses which volume the orthoslices show. It starts with just
// the discovered brain volume (already loaded above, served by URL) plus a
// trailing "other…" entry that opens the browser's file picker; each picked file
// is appended so volumes can be switched back and forth.
//
// To keep switching instant, every chosen volume is decoded + uploaded to the
// GPU exactly once and then kept RESIDENT in nvSlices.volumes. Switching just
// reorders the chosen volume to the background (index 0) and zeroes the others'
// opacity — no re-fetch, no re-decode, no re-upload. The world-space crosshair
// is preserved across the switch.
const volSel  = document.getElementById('volSel')
const volFile = document.getElementById('volFile')
// option value -> { name, url?|file?, blobUrl?, image?(NVImage), defCalMin?, defCalMax? }
const volumeRegistry = {}
let currentVolKey = null
let volSeq = 0
let orthoCmap = 'bone'   // colormap applied to whichever volume the orthoslices show

function addVolumeOption(desc, select) {
  const key = 'vol' + (volSeq++)
  volumeRegistry[key] = desc
  const opt = document.createElement('option')
  opt.value = key
  opt.textContent = desc.name
  volSel.insertBefore(opt, volSel.querySelector('option[value="__other__"]'))
  if (select) volSel.value = key
  return key
}

async function showVolume(key) {
  const desc = volumeRegistry[key]
  if (!desc) return
  if (key === currentVolKey && desc.image) return   // already displayed — nothing to do

  // Preserve the current crosshair in world mm (captured against the OLD
  // background) so the switch keeps the anatomical focus point.
  let mm = null
  if (nvSlices.volumes.length && typeof nvSlices.frac2mm === 'function') {
    try { mm = nvSlices.frac2mm([...nvSlices.scene.crosshairPos]) } catch (e) {}
  }

  // First selection of this volume: decode + upload once, then keep it resident
  // so re-selecting it later skips the expensive decode (the GL recomposite in
  // setVolume() below is unavoidable per switch, but the decode is not).
  if (!desc.image) {
    const item = { colormap: orthoCmap, opacity: 1 }
    if (desc.url) {
      item.url = desc.url
    } else if (desc.file) {
      if (!desc.blobUrl) desc.blobUrl = URL.createObjectURL(desc.file)
      item.url  = desc.blobUrl
      item.name = desc.file.name       // blob URLs carry no extension; let NiiVue infer the format
    }
    try {
      await nvSlices.addVolumeFromUrl(item)   // add without dropping the resident volumes
    } catch (e) {
      console.warn('[volume] failed to load', desc.name, e)
      alert('Could not load volume: ' + desc.name)
      return
    }
    desc.image     = nvSlices.volumes[nvSlices.volumes.length - 1]
    desc.defCalMin = desc.image.cal_min      // per-volume default window for the 'r' reset
    desc.defCalMax = desc.image.cal_max
  }

  // Bring the chosen volume to the background (index 0) and hide the rest. Use
  // NiiVue's official setVolume(): it updates the internal background reference
  // and frac<->vox transforms. Reordering nvSlices.volumes by hand does NOT, so
  // the next click crashed in convertFrac2Vox. setVolume() rebuilds the GL
  // texture itself, so there is no separate updateGLVolume() call.
  desc.image.colormap = orthoCmap                   // colormap follows the shown volume
  // Show only the chosen volume's pixels AND its colorbar; resident volumes keep
  // their own colormap but their colorbars stay hidden so they don't pile up.
  for (const v of nvSlices.volumes) {
    const shown = (v === desc.image)
    v.opacity = shown ? 1 : 0
    v.colorbarVisible = shown
  }
  if (nvSlices.volumes[0] !== desc.image) nvSlices.setVolume(desc.image, 0)
  else nvSlices.updateGLVolume()

  currentVolKey = key
  volSel.value = key
  defaultVolCalMin = desc.defCalMin
  defaultVolCalMax = desc.defCalMax
  nvSlices.setCrosshairColor(ACCENT_YELLOW_RGBA)    // re-assert crosshair styling
  nvSlices.setCrosshairWidth(0.5)
  if (mm && typeof nvSlices.mm2frac === 'function') {
    const frac = nvSlices.mm2frac([mm[0], mm[1], mm[2]])
    if (frac) nvSlices.scene.crosshairPos = [...frac]
  }
  // Refresh the position readout so its value line reflects the new volume.
  if (typeof nvSlices.createOnLocationChange === 'function') nvSlices.createOnLocationChange()
  nvSlices.drawScene()
  syncVolClipInputs()          // reflect the shown volume's color range in the clip boxes
}

// Seed the dropdown: the already-loaded brain volume (if any), then "other…".
// Its NVImage is already resident (from the startup loadVolumes), so link it
// directly rather than re-adding it.
if (VOL_URL) {
  const initName = VOLUMES[0].name || decodeURIComponent(VOL_URL.split('?')[0].split('/').pop())
  const img = nvSlices.volumes[0] || null
  currentVolKey = addVolumeOption({
    name: initName, url: VOL_URL, image: img,
    defCalMin: img ? img.cal_min : null, defCalMax: img ? img.cal_max : null,
  }, true)
}
{
  const other = document.createElement('option')
  other.value = '__other__'
  other.textContent = 'other…'
  volSel.appendChild(other)
}

volSel.addEventListener('change', () => {
  if (volSel.value === '__other__') {
    volSel.value = currentVolKey ?? ''   // revert; the real switch commits once a file is picked
    volFile.click()
    return
  }
  showVolume(volSel.value)
})

volFile.addEventListener('change', () => {
  const file = volFile.files && volFile.files[0]
  volFile.value = ''                     // reset so the same file can be re-picked later
  if (!file) return
  showVolume(addVolumeOption({ name: file.name, file }, true))
})

// ── orthoslice colormap selector ──────────────────────────────────────────────
// Options come straight from NiiVue's own colormap list, so every entry is valid.
// The choice is orthoslice-wide: it applies to the current background volume and
// is re-applied by showVolume() when you switch volumes.
const volCmapSel = document.getElementById('volCmapSel')
fillCmapSelect(volCmapSel, orthoCmap)   // same curated list as the surface overlays
volCmapSel.addEventListener('change', () => {
  orthoCmap = volCmapSel.value
  const bg = nvSlices.volumes[0]
  if (bg) { bg.colormap = orthoCmap; nvSlices.updateGLVolume(); nvSlices.drawScene() }
})

// ── orthoslice color clip (cal_min / cal_max) ─────────────────────────────────
// Clip the intensity range mapped through the colormap on the orthoslice
// background volume; the built-in colorbar reflects the range automatically.
const volClipMin = document.getElementById('volClipMin')
const volClipMax = document.getElementById('volClipMax')
function syncVolClipInputs() {
  const bg = nvSlices.volumes[0]
  if (!bg) return
  volClipMin.value = (+bg.cal_min).toPrecision(4)
  volClipMax.value = (+bg.cal_max).toPrecision(4)
}
function applyVolClip() {
  const bg = nvSlices.volumes[0]
  if (!bg) return
  const mn = parseFloat(volClipMin.value), mx = parseFloat(volClipMax.value)
  if (!isFinite(mn) || !isFinite(mx) || mx <= mn) { syncVolClipInputs(); return }  // ignore invalid, restore
  bg.cal_min = mn; bg.cal_max = mx
  nvSlices.updateGLVolume(); nvSlices.drawScene()
}
volClipMin.addEventListener('change', applyVolClip)
volClipMax.addEventListener('change', applyVolClip)
document.getElementById('volClipAuto').addEventListener('click', () => {
  const bg = nvSlices.volumes[0], desc = volumeRegistry[currentVolKey]
  if (!bg || !desc || desc.defCalMin == null) return
  bg.cal_min = desc.defCalMin; bg.cal_max = desc.defCalMax   // the volume's default (auto) window
  nvSlices.updateGLVolume(); nvSlices.drawScene()
  syncVolClipInputs()
})
syncVolClipInputs()          // initial fill from the startup volume

// Right-click-drag window/level changes cal_min/cal_max inside NiiVue (the
// colorbar updates immediately); mirror that same range into the clip boxes.
// NiiVue invokes the *instance* callback this.onIntensityChange(volume), not
// opts.onIntensityChange, so it must be assigned on the instance to fire.
nvSlices.onIntensityChange = () => syncVolClipInputs()

// ── depth control ─────────────────────────────────────────────────────────────
function setDepth(d) {
  currentDepth = d
  const mm = d * STEP_MM
  document.getElementById('depth-label').textContent = `${mm.toFixed(1)} mm`
  for (const nv of [nvLhL, nvRhL, nvAsym])
    for (const mesh of nv.meshes)
      if (mesh.layers?.length) nv.setMeshLayerProperty(mesh.id, 0, 'frame4D', d)
  refreshInvalidMasks(d)
  broadcastDwiCrosshair()
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

// Pin the Asymmetry plot's value axis (x) to the asym colormap limits so the
// plot and the surface color scale share the same range.
function applyAsymValueLimits() {
  if (!chartAsym) return
  Plotly.relayout(chartAsym, { 'xaxis.range': [currentAsymMin, currentAsymMax] })
}

function setAsymCLim(mn, mx) {
  currentAsymMin = mn; currentAsymMax = mx
  for (const mesh of nvAsym.meshes)
    if (mesh.layers?.length) {
      nvAsym.setMeshLayerProperty(mesh.id, 0, 'cal_min', mn)
      nvAsym.setMeshLayerProperty(mesh.id, 0, 'cal_max', mx)
    }
  applyAsymValueLimits()
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
// Build the gradient straight from NiiVue's interpolated colormap LUT so every
// registered colormap (built-in or our custom diverging ones) renders correctly
// and the bar always matches the surface. nvSlices.colormap(name, invert) returns
// the full 256-entry RGBA table with inversion already applied, so no separate
// per-colormap CSS table to keep in sync.
function cmapCss(name, invert) {
  let lut = null
  try { lut = nvSlices.colormap ? nvSlices.colormap(name, !!invert) : null } catch (e) {}
  if (lut && lut.length >= 8) {
    const n = lut.length / 4, STEPS = 16, stops = []
    for (let s = 0; s <= STEPS; s++) {
      const idx = Math.round(s / STEPS * (n - 1)) * 4
      stops.push(`rgb(${lut[idx]},${lut[idx+1]},${lut[idx+2]}) ${(s / STEPS * 100).toFixed(1)}%`)
    }
    return `linear-gradient(to right, ${stops.join(',')})`
  }
  return `linear-gradient(to ${invert ? 'left' : 'right'}, #333 0%, #ccc 100%)`
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
  applyAsymValueLimits()
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

// ── streamlines overlay on the orthoslices ────────────────────────────────────
{
  const btn = document.getElementById('loadStreamlinesBtn')
  const visChk = document.getElementById('streamlineVisibleChk')
  const modeSel = document.getElementById('streamlineModeSel')
  const colorSel = document.getElementById('streamlineColorSel')
  const colorPicker = document.getElementById('streamlineColorPicker')
  if (!STREAMLINES.lh && !STREAMLINES.rh) {
    btn.disabled = true
    btn.title = 'No streamlines (.tck) found for this subject'
    btn.style.opacity = 0.4
    visChk.parentElement.style.opacity = 0.4
    modeSel.parentElement.style.opacity = 0.4
    colorSel.parentElement.style.opacity = 0.4
  } else {
    btn.addEventListener('click', async () => {
      btn.disabled = true
      btn.textContent = 'Loading…'
      try {
        await ensureStreamlines()
        btn.textContent = 'Streamlines loaded'
        visChk.disabled = false
        modeSel.disabled = false
        colorSel.disabled = false
        applyStreamlineSelection()   // start filtered to whatever vertex is already selected
        applyStreamlineColor()
      } catch (e) {
        console.warn('[streamlines] failed to load', e)
        alert('Could not load streamlines: ' + e.message)
        btn.textContent = 'Load streamlines'
        btn.disabled = false
      }
    })
    visChk.addEventListener('change', function() {
      streamlinesVisible = this.checked
      applyStreamlineVisibility()
    })
    modeSel.addEventListener('change', applyStreamlineSelection)
    colorSel.addEventListener('change', () => {
      colorPicker.disabled = colorSel.value !== 'fixed'
      applyStreamlineColor()
    })
    colorPicker.addEventListener('input', applyStreamlineColor)
  }
}

// ── DWI-space companion tab ───────────────────────────────────────────────────
// "Open DWI space" launches /dwi (FA map + DWI-space streamlines, no sidebar —
// see make_dwi_html) in a second tab, then keeps its crosshair following this
// tab's vertex/depth selection over BroadcastChannel. Mostly one-way (T1 tab →
// DWI tab) and same-origin/same-browser only, so no server round-trip is
// needed; the DWI tab does its own vertex→point lookup once it receives a
// message (see placeCrosshairAtStreamlinePoint in _DWI_HTML — the DWI-space
// streamlines are the literal warp target of the ones here, so a (vertex,
// depth) pair indexes directly into that tab's own streamline points).
const dwiChannel = ('BroadcastChannel' in window) ? new BroadcastChannel('cortical-browser-dwi-crosshair') : null
// The one message that flows the other way: a freshly-opened DWI tab needs
// several awaits (fetch its page, load NiiVue from the CDN, load the FA
// volume and streamlines) before it's even listening. A broadcast fired right
// after window.open() below routinely beats that — BroadcastChannel doesn't
// queue messages for listeners that don't exist yet, so it's just lost. The
// DWI tab announces "dwi-ready" once its own listener is actually live; this
// re-sends the current selection in response, instead of guessing at timing.
if (dwiChannel) {
  dwiChannel.onmessage = ev => {
    if (ev.data?.type === 'dwi-ready') broadcastDwiCrosshair()
  }
}
let currentHemi = 'lh'   // hemisphere of the most recently selected vertex
function broadcastDwiCrosshair() {
  if (!dwiChannel || currentVertex === null) return
  // vertex is the crosshair anchor (always a single point); vertices is the
  // exact same selectedVertices array the main tab's own "Selected vertex"
  // streamline filter uses, so the DWI tab's "Selected vertex" mode
  // highlights the identical set — including a loaded vertex-ID list, if one
  // is active. Read from the cache rather than recomputed, so what's
  // broadcast can never drift from what selectVertex() actually applied.
  dwiChannel.postMessage({
    vertex: currentVertex, vertices: selectedVertices,
    depth: currentDepth, hemi: currentHemi,
  })
}
{
  const btn = document.getElementById('openDwiBtn')
  if (!DWI_AVAILABLE) {
    btn.disabled = true
    btn.title = 'No dwi/dti/fa.nii.gz (or other fa.nii.gz under dwi/) found for this subject'
    btn.style.opacity = 0.4
  } else {
    btn.addEventListener('click', () => {
      // Named target: repeat clicks focus the same tab instead of piling up new ones.
      window.open('/dwi', 'dwiSpaceTab')
      broadcastDwiCrosshair()   // in case that tab was already open and waiting
    })
  }
}

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

// Orthoslice interpolation: checked = smooth (linear), unchecked = nearest. Also
// toggled by the "i" keyboard shortcut, which flips this checkbox. setInterpolation
// takes isNearest, so pass the negation of "smooth", and it redraws itself.
document.getElementById('interpChk').addEventListener('change', function() {
  nvSlices.setInterpolation(!this.checked)
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
    document.getElementById('vtx-display-lh').textContent = '—, —, — mm'
    document.getElementById('vtx-display-rh').textContent = '—, —, — mm'
    document.getElementById('pos-display').textContent = ''
    resetPivot(nvLhL); resetPivot(nvRhL); resetPivot(nvAsym)
    for (const chart of [chartLH, chartRH, chartAsym]) {
      Plotly.restyle(chart, { x: [[], [], [], [], [], []], y: [[], [], [], [], [], []] }, [0, 1, 2, 3, 4, 5])
      Plotly.restyle(chart, { name: [chart.baseLabel] }, [0])
    }
    clearMultivariate()
  }
})

// ── initial depth + colorbars ─────────────────────────────────────────────────
setDepth(currentDepth)
refreshColorbars()

// ── neighbor-ring expansion (mirrors getNeighborRings in cortical_browser_2.m) ─
// Built lazily from the LH mesh topology and reused for RH/Asym since all three
// share the same surface template triangulation — only vertex coordinates differ.
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

// ── loaded vertex-ID list (supersedes interactive vertex/rings selection) ────
// When a .txt file is loaded via "Load vertex IDs", this array replaces the
// vertex set everywhere a selection currently feeds into (depth-profile
// aggregation, multivariate stats, streamline "Selected vertex" mode, and the
// DWI-space link) — see currentRingSet() below. Rings is bypassed entirely in
// this mode: the set is exactly the loaded IDs, not further expanded.
let loadedVertexIds = null

// Returns the vertex set to aggregate over for vertIdx: the loaded list if one
// is active, otherwise the normal neighbor-ring expansion. Pure/stateless —
// selectVertex() below is the only place that calls this and caches the
// result into selectedVertices.
function currentRingSet(vertIdx) {
  return loadedVertexIds || neighborRings(vertIdx, nRings)
}

// ── the current selection, exposed as one array regardless of how it was
// made (a single click, click+Rings, or a loaded vertex-ID list) ─────────────
// selectVertex() is the sole writer, right after it computes ringSet via
// currentRingSet(). Everything that needs "what's selected right now" —
// streamline filtering, the DWI-space broadcast, and the dump helpers below —
// reads this instead of recomputing it, so there's exactly one place selection
// state can get out of sync with what's actually on screen.
let selectedVertices = []

// Log the current selection to the browser devtools console. Also reachable
// as window.dumpSelectedVertices() from the console directly.
function dumpSelectedVertices() {
  console.log(`[selection] ${selectedVertices.length} vertex ID(s):`, selectedVertices)
  return selectedVertices
}
window.dumpSelectedVertices = dumpSelectedVertices

// Download the current selection as a .txt file — one vertex ID per line,
// the exact format "Load vertex IDs" reads back in, so a selection can be
// round-tripped (export, edit externally, re-import) or archived.
function downloadSelectedVertices() {
  if (!selectedVertices.length) { alert('No vertex selected'); return }
  const subj = document.querySelector('.subj')?.textContent || 'subject'
  const blob = new Blob([selectedVertices.join('\n') + '\n'], { type: 'text/plain' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href = url
  a.download = `${subj}_vertex_selection.txt`
  a.click()
  URL.revokeObjectURL(url)
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

// Per-depth mean ± sd across vertices, ignoring NaN ("no data": invalid or
// short-track depths). A depth with no valid samples yields NaN (→ a gap in
// the chart); sd needs ≥2 valid samples at that depth, else NaN (no band).
function meanStd(rows) {
  const n = rows.length, nd = rows[0].length
  const mean = new Array(nd).fill(0)
  const cnt  = new Array(nd).fill(0)
  for (const row of rows) for (let d = 0; d < nd; d++) {
    const v = row[d]
    if (Number.isFinite(v)) { mean[d] += v; cnt[d]++ }
  }
  for (let d = 0; d < nd; d++) mean[d] = cnt[d] ? mean[d] / cnt[d] : NaN
  if (n <= 1) return { mean, sd: null }
  const sd = new Array(nd).fill(0)
  for (const row of rows) for (let d = 0; d < nd; d++) {
    const v = row[d]
    if (Number.isFinite(v)) { const diff = v - mean[d]; sd[d] += diff*diff }
  }
  for (let d = 0; d < nd; d++) sd[d] = cnt[d] > 1 ? Math.sqrt(sd[d] / (cnt[d] - 1)) : NaN
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

  // Snap orthoslice crosshairs to vertex world position. Setting crosshairPos
  // directly doesn't fire onLocationChange (only user slice interaction does),
  // so call createOnLocationChange() to refresh the position readout.
  const vx=mesh.pts[vertIdx*3], vy=mesh.pts[vertIdx*3+1], vz=mesh.pts[vertIdx*3+2]
  if (nvSlices.volumes.length && typeof nvSlices.mm2frac === 'function') {
    const frac = nvSlices.mm2frac([vx, vy, vz])
    if (frac) {
      nvSlices.scene.crosshairPos = [...frac]
      if (typeof nvSlices.createOnLocationChange === 'function') nvSlices.createOnLocationChange()
      nvSlices.drawScene()
    }
  }

  selectedVertices  = currentRingSet(vertIdx)
  const ringSet     = selectedVertices
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
  applyStreamlineSelection()   // respects the mode selector; no-op if streamlines haven't been loaded yet
  currentHemi = (nvInst === nvRhL) ? 'rh' : 'lh'   // nvAsym shares LH geometry, counts as 'lh'
  broadcastDwiCrosshair()

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
    const loadingEl = document.getElementById('normativeLoading')
    loadingEl.style.display = ''
    try {
      const [normLh, normRh, normAsym] = await Promise.all([
        normativeRingStat('lh',   currentMetric, ringSet),
        normativeRingStat('rh',   currentMetric, ringSet),
        normativeRingStat('asym', currentMetric, ringSet),
      ])
      normStat = { lh: normLh, rh: normRh, asym: normAsym }
    } finally {
      loadingEl.style.display = 'none'
    }
  }

  setProfiles(meanStd(rowsOf(lhMat)), meanStd(rowsOf(rhMat)), meanStd(rowsOf(asymMat)), ringSet.length, lhArea, rhArea, normStat)
  // Both hemispheres' world coordinates for this vertex index, regardless of
  // which surface panel was actually clicked — the ico6_sym template shares
  // vertex indices across LH/RH, but the two hemispheres have distinct (mirror-
  // asymmetric) geometry, so their mm coordinates differ and both are worth showing.
  const fmtMm = (mesh, i) => mesh?.pts
    ? `${mesh.pts[i*3].toFixed(1)}, ${mesh.pts[i*3+1].toFixed(1)}, ${mesh.pts[i*3+2].toFixed(1)} mm`
    : '—, —, — mm'
  document.getElementById('vtx-display-lh').textContent = fmtMm(lhMesh, vertIdx)
  document.getElementById('vtx-display-rh').textContent = fmtMm(rhMesh, vertIdx)
  document.getElementById('vtxInput').value = vertIdx

  // Multivariate panels fetch independently so the profiles above render
  // immediately rather than waiting on the server-side Mahalanobis compute.
  // They aggregate over the same neighbor-ring set as the univariate charts.
  // Debounced (not fetched directly) so scanning quickly across several
  // vertices doesn't queue up a full Mahalanobis recompute for every one of
  // them — only the vertex the user settles on pays that cost.
  scheduleMultivariateUpdate(vertIdx, ringSet)
}

async function pickOnSurface(canvas, mouseX, mouseY, nvInst) {
  if (!currentMetric) return
  if (loadedVertexIds) return   // a loaded vertex-ID list supersedes interactive picking
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

// Nearest-vertex lookup for shift/ctrl-click-on-orthoslice picking. kind is
// 'wm' (white, shift-click) or 'pial' (ctrl-click) — restricted to a single
// contour mesh (real anatomical world coordinates, loaded on demand via
// ensureSliceContour) rather than whatever geometry the LH/RH panels
// currently show — inflated/very_inflated surfaces don't occupy real
// anatomical space, so "nearest" wouldn't mean anything there.
async function nearestSurfaceVertex(mm, kind) {
  const surf = await ensureSliceContour(kind)
  // ensureSliceContour() loads meshes at full opacity; normally it's only ever
  // called right after sliceContourVisible[kind] is set and immediately
  // followed by applySliceContourVisibility() (see toggleSliceContour()).
  // Called standalone here for picking, so re-assert its checkbox's actual
  // on/off state — otherwise a shift/ctrl-click would silently turn the
  // contour overlay visible even with its checkbox unchecked.
  applySliceContourVisibility(kind)
  let bestD2 = Infinity, bestIdx = -1, bestHemi = 'lh'
  for (const [hemi, mesh] of [['lh', surf.lh], ['rh', surf.rh]]) {
    if (!mesh?.pts) continue
    const pts = mesh.pts
    const n = pts.length / 3
    for (let i = 0; i < n; i++) {
      const dx = pts[i*3] - mm[0], dy = pts[i*3+1] - mm[1], dz = pts[i*3+2] - mm[2]
      const d2 = dx*dx + dy*dy + dz*dz
      if (d2 < bestD2) { bestD2 = d2; bestIdx = i; bestHemi = hemi }
    }
  }
  return bestIdx >= 0 ? { vertIdx: bestIdx, hemi: bestHemi } : null
}

// selectVertex() derives the orthoslice crosshair and every 3-D marker from
// nvInst.meshes[0].pts, i.e. whatever surface the LH/RH/Asym panels currently
// display — it has no notion of "the surface the vertex was actually picked
// from". So a pial pick made while the panels still show white would snap
// the crosshair (and every marker) to that vertex's WHITE position, not its
// pial one. Switch the panels to the picked kind first — the same lhSurfUrl/
// rhSurfUrl/asymSurfUrl + loadXPanel() reload used by the surface-type
// dropdowns (see their 'change' handlers below) — so everything selectVertex
// places ends up on the surface that was actually clicked.
async function selectVertexOnSurface(vertIdx, hemi, kind) {
  const surfType = SLICE_CONTOUR_SURF[kind]   // 'wm' -> 'white', 'pial' -> 'pial'
  const lhSel = document.getElementById('lhSurfSel')
  const rhSel = document.getElementById('rhSurfSel')
  const asymSel = document.getElementById('asymSurfSel')
  if (SURF_TYPES[surfType]?.lh) {
    lhSurfUrl = SURF_TYPES[surfType].lh
    asymSurfUrl = SURF_TYPES[surfType].lh
    lhVertexAreas = null   // geometry changed — per-vertex area must be recomputed
    if (lhSel)   lhSel.value = surfType
    if (asymSel) asymSel.value = surfType
  }
  if (SURF_TYPES[surfType]?.rh) {
    rhSurfUrl = SURF_TYPES[surfType].rh
    rhVertexAreas = null
    if (rhSel) rhSel.value = surfType
  }
  await Promise.all([loadLhPanel(currentMetric), loadRhPanel(currentMetric), loadAsymPanel(currentMetric)])
  await selectVertex(vertIdx, hemi === 'rh' ? nvRhL : nvLhL)
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

// Shift-click / ctrl-click on the orthoslices: select the nearest white
// (shift) or pial (ctrl) surface vertex to the clicked world position. A
// plain click still just moves the crosshair (NiiVue's own default behavior
// on gl-slices, untouched here); by the time our mouseup listener runs,
// NiiVue's own mousedown/mouseup handling has already updated
// nvSlices.scene.crosshairPos, so frac2mm on it gives exactly the clicked
// world position without needing to hook onLocationChange.
function setupOrthoslicePicker(canvasId) {
  const canvas = document.getElementById(canvasId)
  let downX=0, downY=0, downKind=null
  canvas.addEventListener('mousedown', e => {
    downX=e.clientX; downY=e.clientY
    downKind = e.shiftKey ? 'wm' : e.ctrlKey ? 'pial' : null
  })
  canvas.addEventListener('mouseup', async e => {
    if (!downKind) return
    const dx=e.clientX-downX, dy=e.clientY-downY
    if (dx*dx+dy*dy > 25) return   // treat as a drag, not a click
    if (typeof nvSlices.frac2mm !== 'function') return
    const mm = nvSlices.frac2mm([...nvSlices.scene.crosshairPos])
    if (!mm) return
    const hit = await nearestSurfaceVertex(mm, downKind)
    if (hit) await selectVertexOnSurface(hit.vertIdx, hit.hemi, downKind)
  })
}
setupOrthoslicePicker('gl-slices')

// ── vertex ID text entry ──────────────────────────────────────────────────────
document.getElementById('vtxInput').addEventListener('keydown', e => {
  if (e.key !== 'Enter') return
  if (loadedVertexIds) return   // superseded by the loaded vertex-ID list; input is also disabled
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

// ── loaded vertex-ID list ─────────────────────────────────────────────────────
// A plain .txt file, one non-negative integer vertex index per line. Once
// loaded it supersedes interactive selection everywhere (see currentRingSet
// above, and the pickOnSurface/vtxInput guards): the loaded list itself is
// the vertex set used for aggregation, Rings is bypassed, and the first ID
// in the file becomes the anchor vertex for the crosshair/markers/DWI link,
// same role currentVertex normally plays for a single interactive pick.
{
  const loadBtn   = document.getElementById('loadVertexIdsBtn')
  const saveBtn   = document.getElementById('saveVertexIdsBtn')
  const unloadBtn = document.getElementById('unloadVertexIdsBtn')
  const fileInput = document.getElementById('vertexIdsFile')
  const statusEl  = document.getElementById('vertexIdsStatus')
  const vtxInput  = document.getElementById('vtxInput')
  const ringsInputEl = document.getElementById('ringsInput')

  saveBtn.addEventListener('click', downloadSelectedVertices)

  function setLoadedUiState(loaded) {
    unloadBtn.disabled = !loaded
    vtxInput.disabled = loaded
    ringsInputEl.disabled = loaded
  }

  loadBtn.addEventListener('click', () => fileInput.click())

  fileInput.addEventListener('change', () => {
    const file = fileInput.files && fileInput.files[0]
    fileInput.value = ''   // reset so the same file can be re-picked later
    if (!file) return
    const reader = new FileReader()
    reader.onload = async () => {
      const lines = String(reader.result).split(/\r?\n/).map(s => s.trim()).filter(s => s.length)
      const ids = lines.map(Number)
      if (!ids.length || ids.some(n => !Number.isInteger(n) || n < 0)) {
        alert(`Could not parse ${file.name}: expected one non-negative integer vertex index per line`)
        return
      }
      const nVerts = nvLhL.meshes[0]?.pts.length / 3
      const inRange = Number.isFinite(nVerts) ? ids.filter(n => n < nVerts) : ids
      if (!inRange.length) {
        alert(`${file.name}: no vertex ID is within range for this surface (0-${nVerts - 1})`)
        return
      }
      if (inRange.length < ids.length) {
        console.warn(`[vertex IDs] dropped ${ids.length - inRange.length} out-of-range ID(s) from ${file.name}`)
      }
      loadedVertexIds = inRange
      setLoadedUiState(true)
      const dropped = ids.length - inRange.length
      statusEl.textContent = `${inRange.length} vertex ID${inRange.length === 1 ? '' : 's'} loaded from ${file.name}`
        + (dropped ? ` (${dropped} out of range, dropped)` : '')
      await selectVertex(inRange[0], nvLhL)
    }
    reader.onerror = () => alert(`Could not read ${file.name}`)
    reader.readAsText(file)
  })

  unloadBtn.addEventListener('click', () => {
    loadedVertexIds = null
    setLoadedUiState(false)
    statusEl.textContent = ''
  })
}

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
      Plotly.restyle(chart, { x: [[], [], []], y: [[], [], []] }, [3, 4, 5])
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

// ── show/hide multivariate (Mahalanobis/radar/z-score) panels ────────────────
// Off by default (see showMultivariate declaration): fetching/computing them
// on every vertex jump got expensive as the cohort grew, so they're opt-in.
document.getElementById('showMultivariateChk').addEventListener('change', function() {
  showMultivariate = this.checked
  document.getElementById('grid').classList.toggle('mv-hidden', !showMultivariate)
  if (showMultivariate) {
    if (currentVertex !== null) updateMultivariate(currentVertex, selectedVertices)
  } else {
    clearMultivariate()
  }
  // Rows 1-3 reclaim/cede the grid space row 4 just gave up or took back —
  // nudge NiiVue/Plotly's own resize observers to pick up the new cell sizes.
  window.dispatchEvent(new Event('resize'))
})
// Collapsed at startup to match showMultivariate's default-off state.
document.getElementById('grid').classList.toggle('mv-hidden', !showMultivariate)

// ── multivariate panel limits (radar/bar |z| and Mahalanobis depth) ──────────
document.getElementById('mvZlimInput').addEventListener('change', function() {
  const v = parseFloat(this.value)
  if (!isFinite(v) || v <= 0) { this.value = mvZlim; return }
  mvZlim = v
  if (mvCurrent) renderRadarBar(mvCurrent, currentDepth)
})
document.getElementById('mvMahalInput').addEventListener('change', function() {
  const v = parseFloat(this.value)
  if (!isFinite(v) || v <= 0) { this.value = mvMahalLim; return }
  mvMahalLim = v
  if (mvCurrent) renderMahalChart(mvCurrent)
})
if (!MV_AVAILABLE) {
  for (const id of ['showMultivariateChk','mvZlimInput','mvMahalInput']) {
    const el = document.getElementById(id)
    el.disabled = true
    el.parentElement.style.opacity = 0.4
  }
}

// Warn when this subject has TSF metrics the cohort normative file doesn't
// (e.g. newly added metrics computed per-subject before the cohort file was
// rebuilt to include them) — compute_multivariate can only use metrics both
// sides share, so these are silently dropped from Mahalanobis/radar/z-score
// without this notice.
if (MV_AVAILABLE) {
  const missing = Object.keys(METRICS).filter(m => !(m in NORMATIVE))
  if (missing.length) {
    const el = document.getElementById('mvMetricWarning')
    el.querySelector('#mvMetricWarningText').textContent =
      `⚠ No cohort normative data for: ${missing.join(', ')} — excluded from Mahalanobis/radar/z-score panels`
    el.style.display = 'block'
    el.querySelector('.mv-warn-close').addEventListener('click', () => { el.style.display = 'none' })
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
    syncVolClipInputs()
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

// Show the nth loaded orthoslice volume (1-based), in dropdown order; no-op if
// there's no volume at that position.
function showVolumeByIndex(n) {
  const opts = [...volSel.options].filter(o => o.value !== '__other__')
  if (opts[n - 1]) showVolume(opts[n - 1].value)
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
    case 'i': {   // toggle orthoslice smooth/nearest interpolation via its checkbox
      const chk = document.getElementById('interpChk')
      chk.checked = !chk.checked
      chk.dispatchEvent(new Event('change'))
      e.preventDefault()
      break
    }
    case 'c': {   // toggle the 3-D cutaway via its checkbox so the UI stays in sync
      const chk = document.getElementById('cutaway3DChk')
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
    // Orthoslice volume: 1-9 pick the nth loaded volume (dropdown order),
    // 0 opens the "other…" file picker.
    case '1': case '2': case '3': case '4': case '5':
    case '6': case '7': case '8': case '9':
      showVolumeByIndex(+e.key); e.preventDefault(); break
    case '0':          volFile.click(); e.preventDefault(); break
  }
})

// ── depth-profile charts (Plotly) ─────────────────────────────────────────────
// Depth runs down the y-axis (reversed autorange — pial surface at the top),
// the metric value runs along x. Each profile chart holds six traces, same
// roles the old Chart.js datasets played: 0 mean, 1/2 subject ±SD (dashed,
// hidden from the legend), 3 normative mean, 4/5 normative ±SD (4 is an
// invisible line, 5 fills back to it for the shaded band).
const PLOTLY_CONFIG = { displayModeBar: false, responsive: true, scrollZoom: false }

function depthProfileLayout() {
  return {
    paper_bgcolor: '#242424', plot_bgcolor: '#242424',
    font: { color: PLOT_TEXT, size: 10 },
    margin: { l: 46, r: 12, t: 30, b: 34 },
    showlegend: true,
    legend: { orientation: 'h', x: 0, y: 1.2, font: { size: 9, color: PLOT_TEXT }, groupclick: 'togglegroup',
              itemwidth: 30, tracegroupgap: 4 },
    dragmode: false,
    hovermode: 'closest',
    hoverdistance: 50,
    xaxis: { nticks: 5, color: PLOT_TEXT, gridcolor: '#303030', zerolinecolor: '#303030', tickfont: { size: 10 } },
    yaxis: { autorange: 'reversed', title: { text: 'Depth (mm)', font: { color: PLOT_TEXT } },
             nticks: 8, tickformat: '.1f', color: PLOT_TEXT, gridcolor: '#303030', zerolinecolor: '#303030',
             tickfont: { size: 10 } },
    shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 0, y1: 0,
               line: { color: ACCENT_YELLOW, width: 1.5, dash: 'dash' } }],
  }
}

function profileTraces(color, label, fillToZero) {
  return [
    { x: [], y: [], name: label, mode: 'lines+markers', legendgroup: 'subject',
      line: { color, width: 3, shape: 'spline', smoothing: 0.5 }, marker: { size: 1 },
      fill: fillToZero ? 'tozerox' : 'none', fillcolor: hexToRgba(color, 0.16),
      hovertemplate: '%{y:.1f} mm: %{x:.2g}<extra>%{fullData.name}</extra>' },
    { x: [], y: [], mode: 'lines', legendgroup: 'subject', line: { width: 0 }, showlegend: false, hoverinfo: 'skip' },
    { x: [], y: [], mode: 'lines', legendgroup: 'subject', line: { width: 0 }, fill: 'tonextx',
      fillcolor: hexToRgba(color, 0.18), showlegend: false, hoverinfo: 'skip' },
    { x: [], y: [], name: 'Normative', mode: 'lines', legendgroup: 'normative',
      line: { color: '#ffffff', width: 1.5 },
      hovertemplate: '%{y:.1f} mm: %{x:.2g}<extra>%{fullData.name}</extra>' },
    { x: [], y: [], mode: 'lines', legendgroup: 'normative', line: { width: 0 }, showlegend: false, hoverinfo: 'skip' },
    { x: [], y: [], mode: 'lines', legendgroup: 'normative', line: { width: 0 }, fill: 'tonextx',
      fillcolor: 'rgba(160,160,160,0.30)', showlegend: false, hoverinfo: 'skip' },
  ]
}

function makeChart(id, color, label, fillToZero = false) {
  const gd = document.getElementById(id)
  Plotly.newPlot(gd, profileTraces(color, label, fillToZero), depthProfileLayout(), PLOTLY_CONFIG)
  gd.baseLabel = label
  gd.addEventListener('click', e => setDepthFromChart(gd, e.clientY))
  return gd
}

// Click-anywhere-on-the-chart-to-set-depth: Plotly's own 'plotly_click' event
// only fires when a click lands on a plotted point, not on empty chart area,
// so this listens to the plain DOM click instead and converts its pixel
// position to a data value via the axis's p2d() (pixel-to-data) helper — the
// same private-internals approach chartToSvgString used to take for Chart.js
// (Plotly has no public API for "data value under this arbitrary pixel").
function setDepthFromChart(gd, clientY) {
  const fl = gd._fullLayout
  if (!fl) return
  const rect = gd.getBoundingClientRect()
  const yInPlotArea = (clientY - rect.top) - fl._size.t
  const mm = fl.yaxis.p2d(yInPlotArea)
  const sl = document.getElementById('depthSlider')
  const d  = Math.max(0, Math.min(+sl.max, Math.round(mm / STEP_MM)))
  sl.value = d
  setDepth(d)
}

function downloadChartSvg(gd, filename) {
  Plotly.downloadImage(gd, { format: 'svg', filename, width: gd._fullLayout.width, height: gd._fullLayout.height })
}

chartLH   = makeChart('chart-lh',   LH_COLOR, 'LH')
chartRH   = makeChart('chart-rh',   RH_COLOR, 'RH')
chartAsym = makeChart('chart-asym', '#8af5a6', 'Asymmetry', true)

for (const [btnId, chart, suffix] of [
  ['svgBtnLH',   chartLH,   'lh_depth_profile'],
  ['svgBtnRH',   chartRH,   'rh_depth_profile'],
  ['svgBtnAsym', chartAsym, 'asymmetry_profile'],
]) {
  document.getElementById(btnId).addEventListener('click', e => {
    e.stopPropagation()
    const subj = document.querySelector('.subj')?.textContent || 'subject'
    downloadChartSvg(chart, `${subj}_${currentMetric}_${suffix}`)
  })
}
applyAsymValueLimits()

// ── multivariate explorer charts (row 4) ─────────────────────────────────────
const mvFont = { size: 10, color: PLOT_TEXT }
const mvLegend = { orientation: 'h', x: 0, font: { size: 9, color: PLOT_TEXT }, itemwidth: 30, tracegroupgap: 4 }

// Mahalanobis distance vs depth — a mean line per hemisphere with a dashed
// ±SD band (mirroring the univariate profile charts; the band is only
// populated when >1 vertex is selected), plus the shared yellow depth
// reference line. Clicking sets the depth, like the profile charts.
function mahalSdBand(color, group) {
  return [
    { x: [], y: [], mode: 'lines', legendgroup: group, line: { width: 0 }, showlegend: false, hoverinfo: 'skip' },
    { x: [], y: [], mode: 'lines', legendgroup: group, line: { width: 0 }, fill: 'tonextx',
      fillcolor: hexToRgba(color, 0.18), showlegend: false, hoverinfo: 'skip' },
  ]
}
chartMahal = document.getElementById('chart-mahal')
Plotly.newPlot(chartMahal, [
  { x: [], y: [], name: 'LH', mode: 'lines+markers', legendgroup: 'lh',
    line: { color: LH_COLOR, width: 3 }, marker: { size: 1 } },
  ...mahalSdBand(LH_COLOR, 'lh'),
  { x: [], y: [], name: 'RH', mode: 'lines+markers', legendgroup: 'rh',
    line: { color: RH_COLOR, width: 3 }, marker: { size: 1 } },
  ...mahalSdBand(RH_COLOR, 'rh'),
], {
  paper_bgcolor: '#242424', plot_bgcolor: '#242424',
  font: mvFont,
  margin: { l: 46, r: 12, t: 30, b: 34 },
  showlegend: true,
  legend: { ...mvLegend, y: 1.2, groupclick: 'togglegroup' },
  dragmode: false, hovermode: 'closest',
  xaxis: { range: [0, mvMahalLim], title: { text: 'Mahalanobis distance', font: { color: PLOT_TEXT } },
           color: PLOT_TEXT, gridcolor: '#303030', tickfont: { size: 10 } },
  yaxis: { autorange: 'reversed', title: { text: 'Depth (mm)', font: { color: PLOT_TEXT } },
           nticks: 8, tickformat: '.1f', color: PLOT_TEXT, gridcolor: '#303030', tickfont: { size: 10 } },
  shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 0, y1: 0,
             line: { color: ACCENT_YELLOW, width: 1.5, dash: 'dash' } }],
}, PLOTLY_CONFIG)
chartMahal.addEventListener('click', e => setDepthFromChart(chartMahal, e.clientY))

// |z-score| radar — one polygon per hemisphere, one spoke per metric.
// Mean |z| polygon plus dashed +SD/−SD polygons (hidden from the legend),
// mirroring the band on the profile/Mahalanobis charts. Plotly's scatterpolar
// doesn't auto-close the polygon like Chart.js's radar did, so closeLoop()
// repeats the first point at the end of both r and theta.
const closeLoop = arr => (arr.length ? [...arr, arr[0]] : arr)
function radarSdBand(color, group) {
  return [
    { r: [], theta: [], type: 'scatterpolar', mode: 'lines', legendgroup: group,
      line: { color, width: 1, dash: 'dash' }, showlegend: false, hoverinfo: 'skip' },
    { r: [], theta: [], type: 'scatterpolar', mode: 'lines', legendgroup: group,
      line: { color, width: 1, dash: 'dash' }, showlegend: false, hoverinfo: 'skip' },
  ]
}
chartRadar = document.getElementById('chart-radar')
Plotly.newPlot(chartRadar, [
  { r: [], theta: [], type: 'scatterpolar', name: 'LH', mode: 'lines+markers', legendgroup: 'lh',
    line: { color: LH_COLOR, width: 2 }, marker: { size: 4 } },
  ...radarSdBand(LH_COLOR, 'lh'),
  { r: [], theta: [], type: 'scatterpolar', name: 'RH', mode: 'lines+markers', legendgroup: 'rh',
    line: { color: RH_COLOR, width: 2 }, marker: { size: 4 } },
  ...radarSdBand(RH_COLOR, 'rh'),
], {
  paper_bgcolor: '#242424',
  font: mvFont,
  margin: { l: 30, r: 30, t: 20, b: 20 },
  showlegend: true,
  legend: { ...mvLegend, y: 1.15, groupclick: 'togglegroup' },
  dragmode: false,
  polar: {
    bgcolor: '#242424',
    radialaxis: { range: [0, mvZlim], color: PLOT_TEXT, gridcolor: '#3a3a3a', tickfont: { size: 8 } },
    angularaxis: { color: PLOT_TEXT, gridcolor: '#3a3a3a', tickfont: { size: 10 } },
  },
}, PLOTLY_CONFIG)

// z-score horizontal bars — metrics on the y-axis, signed z on the x-axis.
// Bar alpha ramps from 0.1 at z=0 to 1.0 at |z|=mvZlim, so bars near zero read
// as faint and extreme deviations pop; it re-scales with the live |z| limit
// since zBarAlpha closes over the mutable mvZlim rather than a copied value.
// The across-vertex SD whisker is Plotly's native error_x — the old Chart.js
// version needed a hand-rolled canvas plugin (mvErrorBars) for this, since
// Chart.js has no built-in error bars.
const zBarAlpha = z => 0.1 + 0.9 * Math.min(Math.abs(z ?? 0), mvZlim) / mvZlim
chartZBar = document.getElementById('chart-zbar')
Plotly.newPlot(chartZBar, [
  { x: [], y: [], type: 'bar', orientation: 'h', name: 'LH', marker: { color: [] },
    error_x: { type: 'data', array: [], color: LH_COLOR, thickness: 1, width: 3 } },
  { x: [], y: [], type: 'bar', orientation: 'h', name: 'RH', marker: { color: [] },
    error_x: { type: 'data', array: [], color: RH_COLOR, thickness: 1, width: 3 } },
], {
  paper_bgcolor: '#242424', plot_bgcolor: '#242424',
  font: mvFont,
  margin: { l: 70, r: 15, t: 10, b: 34 },
  showlegend: true,
  legend: { ...mvLegend, y: 1.15 },
  dragmode: false,
  barmode: 'group',
  xaxis: { range: [-mvZlim, mvZlim], title: { text: 'Z-score', font: { color: PLOT_TEXT } },
           color: PLOT_TEXT, gridcolor: '#303030', tickfont: { size: 10 } },
  yaxis: { type: 'category', autorange: 'reversed', color: PLOT_TEXT, tickfont: { size: 9 }, automargin: true },
  shapes: [{ type: 'line', xref: 'x', x0: 0, x1: 0, yref: 'paper', y0: 0, y1: 1,
             line: { color: '#888888', width: 1 } }],
}, PLOTLY_CONFIG)

// If there's no cohort data, flag the panels so they read as unavailable.
if (!MV_AVAILABLE) {
  for (const id of ['clabel-mahal','clabel-radar','clabel-zbar']) {
    const el = document.getElementById(id)
    el.textContent += ' — no cohort data'
    el.parentElement.style.opacity = 0.5
  }
}

for (const [btnId, chart, suffix] of [
  ['svgBtnMahal', chartMahal, 'mahalanobis_distance'],
  ['svgBtnRadar', chartRadar, 'zscore_radar'],
  ['svgBtnZBar',  chartZBar,  'zscore_bars'],
]) {
  document.getElementById(btnId).addEventListener('click', e => {
    e.stopPropagation()
    const subj = document.querySelector('.subj')?.textContent || 'subject'
    downloadChartSvg(chart, `${subj}_${currentMetric}_${suffix}`)
  })
}

const mvLabel = (base, n) => (n > 1 ? `${base} (n=${n})` : base)

// Mahalanobis-by-depth: mean line per hemisphere plus dashed ±SD band across
// the selected vertex + neighbor-ring set (the band appears only for n>1).
function renderMahalChart(data) {
  const xs   = arr => arr.map(v => (v == null ? null : v))
  const ys   = arr => arr.map((_, i) => i * data.step_mm)
  const band = (mean, sd, sign) => mean.map((m, i) => (m == null || !sd || sd[i] == null) ? null : m + sign * sd[i])
  const setHemi = (base, hemi, name) => {
    const depth = ys(hemi.mahal)
    Plotly.restyle(chartMahal, {
      x: [xs(hemi.mahal), band(hemi.mahal, hemi.mahal_sd, +1), band(hemi.mahal, hemi.mahal_sd, -1)],
      y: [depth, depth, depth],
    }, [base, base + 1, base + 2])
    Plotly.restyle(chartMahal, { name: mvLabel(name, data.n_vertices) }, [base])
  }
  setHemi(0, data.lh, 'LH')
  setHemi(3, data.rh, 'RH')
  Plotly.relayout(chartMahal, {
    'xaxis.range': [0, mvMahalLim],
    'shapes[0].y0': currentDepth * STEP_MM,
    'shapes[0].y1': currentDepth * STEP_MM,
  })
}

// Radar (mean |z| ± SD across vertices) and horizontal bars (mean signed z ±
// SD via whiskers) at one depth. Per-metric gaps (null) are left in place
// rather than dropping the whole hemisphere, so partially-valid vertices show.
function renderRadarBar(data, depth) {
  const d = Math.max(0, Math.min(data.n_depths - 1, depth))
  const at = arr => (arr && arr[d]) ? arr[d] : []

  const setRadar = (base, hemi, name) => {
    const mean = at(hemi.absz), sd = at(hemi.absz_sd)
    const plus  = mean.map((m, i) => (m == null || sd[i] == null) ? null : m + sd[i])
    const minus = mean.map((m, i) => (m == null || sd[i] == null) ? null : Math.max(0, m - sd[i]))
    Plotly.restyle(chartRadar, {
      r: [closeLoop(mean), closeLoop(plus), closeLoop(minus)],
      theta: [closeLoop(data.metrics), closeLoop(data.metrics), closeLoop(data.metrics)],
    }, [base, base + 1, base + 2])
    Plotly.restyle(chartRadar, { name: mvLabel(name, data.n_vertices) }, [base])
  }
  setRadar(0, data.lh, 'LH')
  setRadar(3, data.rh, 'RH')
  Plotly.relayout(chartRadar, { 'polar.radialaxis.range': [0, mvZlim] })

  const zColor = (arr, color) => arr.map(v => (v == null ? color : hexToRgba(color, zBarAlpha(v))))
  Plotly.restyle(chartZBar, {
    y: [data.metrics, data.metrics],
    x: [at(data.lh.z), at(data.rh.z)],
    'marker.color': [zColor(at(data.lh.z), LH_COLOR), zColor(at(data.rh.z), RH_COLOR)],
    'error_x.array': [at(data.lh.z_sd), at(data.rh.z_sd)],
    name: [mvLabel('LH', data.n_vertices), mvLabel('RH', data.n_vertices)],
  }, [0, 1])
  Plotly.relayout(chartZBar, { 'xaxis.range': [-mvZlim, mvZlim] })
}

function clearMultivariate() {
  clearTimeout(mvDebounceTimer)
  mvCurrent = null
  Plotly.restyle(chartMahal, { x: [[], [], [], [], [], []], y: [[], [], [], [], [], []] }, [0, 1, 2, 3, 4, 5])
  Plotly.restyle(chartRadar, { r: [[], [], [], [], [], []], theta: [[], [], [], [], [], []] }, [0, 1, 2, 3, 4, 5])
  Plotly.restyle(chartZBar,  { x: [[], []], y: [[], []], 'error_x.array': [[], []] }, [0, 1])
}

// Fetch (once per vertex + ring count) and render all three multivariate
// panels. ringSet mirrors the neighbor-ring set used by the univariate charts,
// so both sets of panels aggregate over exactly the same vertices.
async function updateMultivariate(vertIdx, ringSet) {
  if (!MV_AVAILABLE || !showMultivariate) return
  const verts = (ringSet && ringSet.length) ? ringSet : [vertIdx]
  const key = `${vertIdx}:${nRings}`
  const loadingEl = document.getElementById('multivariateLoading')
  try {
    let data = mvCache[key]
    if (!data) {
      loadingEl.style.display = ''
      const r = await fetch(`/mahal?vertex=${vertIdx}&vertices=${verts.join(',')}`)
      if (!r.ok) return
      data = await r.json()
      mvCache[key] = data
    }
    if (!showMultivariate) return   // toggled off while the fetch was in flight
    mvCurrent = data
    renderMahalChart(data)
    renderRadarBar(data, currentDepth)
  } catch (e) {
    console.warn('[multivariate] fetch/render failed', e)
  } finally {
    loadingEl.style.display = 'none'
  }
}

// Debounced trigger for vertex-jump-driven updates: only the vertex the user
// settles on (mouse stops moving/clicking for MV_DEBOUNCE_MS) pays for the
// Mahalanobis recompute, so scanning quickly across several vertices doesn't
// queue up one full fetch+compute per vertex passed through.
const MV_DEBOUNCE_MS = 250
let mvDebounceTimer = null
function scheduleMultivariateUpdate(vertIdx, ringSet) {
  clearTimeout(mvDebounceTimer)
  if (!MV_AVAILABLE || !showMultivariate) return
  mvDebounceTimer = setTimeout(() => updateMultivariate(vertIdx, ringSet), MV_DEBOUNCE_MS)
}

function updateDepthMarker(mm) {
  if (!chartLH) return
  for (const chart of [chartLH, chartRH, chartAsym, chartMahal]) {
    if (!chart?._fullLayout) continue
    Plotly.relayout(chart, { 'shapes[0].y0': mm, 'shapes[0].y1': mm })
  }
  // The radar/bar panels show a single depth, so they move with the marker too.
  if (mvCurrent) renderRadarBar(mvCurrent, currentDepth)
}

function setProfiles(lhStat, rhStat, asymStat, count, lhArea, rhArea, normStat) {
  // Non-finite (NaN "no data", or a band edge built from one) → null so the
  // chart draws a gap at that depth rather than a spurious point.
  const xs = vals => vals.map(v => Number.isFinite(v) ? v : null)
  const depthsFor = vals => vals.map((_, i) => i * STEP_MM)
  const entries = [
    [chartLH,   lhStat,   lhArea,  normStat?.lh],
    [chartRH,   rhStat,   rhArea,  normStat?.rh],
    [chartAsym, asymStat, null,    normStat?.asym],
  ]
  for (const [chart, stat, area, norm] of entries) {
    let label = chart.baseLabel
    if (count > 1) label += ` (nVert=${count})`
    if (area != null) label += ` [${area.toFixed(1)} mm²]`

    const depth = depthsFor(stat.mean)
    const mean  = xs(stat.mean)
    const hasSd = count > 1 && stat.sd
    const plus  = hasSd ? xs(stat.mean.map((m, i) => m + stat.sd[i])) : []
    const minus = hasSd ? xs(stat.mean.map((m, i) => m - stat.sd[i])) : []
    const sdDepth = hasSd ? depth : []

    const normDepth = norm ? depthsFor(norm.mean) : []
    const normMean  = norm ? xs(norm.mean) : []
    const normPlus  = norm ? xs(norm.mean.map((m, i) => m + norm.sd[i])) : []
    const normMinus = norm ? xs(norm.mean.map((m, i) => m - norm.sd[i])) : []
    const normLabel = norm ? `Normative (nSubj=${Math.max(...norm.n)})` : 'Normative'

    Plotly.restyle(chart, {
      x: [mean, plus, minus, normMean, normPlus, normMinus],
      y: [depth, sdDepth, sdDepth, normDepth, normDepth, normDepth],
    }, [0, 1, 2, 3, 4, 5])
    Plotly.restyle(chart, { name: [label, normLabel] }, [0, 3])
  }
  updateDepthMarker(currentDepth * STEP_MM)
}

// ── resizable rows + double-click maximize ───────────────────────────────────
// NiiVue/Chart panels auto-resize to their cells (NiiVue via ResizeObserver,
// Chart via responsive), so adjusting the grid tracks is all that's needed.
{
  const gridEl = document.getElementById('grid')
  const gridRowFr = [1, 1, 1, 1]                       // content-row weights (fr)
  const applyGridRows = () => {
    for (let i = 0; i < 4; i++) gridEl.style.setProperty(`--gr${i+1}`, gridRowFr[i] + 'fr')
  }
  applyGridRows()

  // Current rendered pixel height of content row n (1..4), read off a panel in it.
  const rowPx = n => {
    const el = gridEl.querySelector('.grow' + n)
    return el ? el.getBoundingClientRect().height : 0
  }

  // Drag a gutter: repartition just the two rows it sits between, in fr units so
  // the result still scales with the window afterwards.
  for (const g of gridEl.querySelectorAll('.rgutter')) {
    g.addEventListener('pointerdown', e => {
      e.preventDefault()
      const ai = +g.dataset.above - 1, bi = +g.dataset.below - 1
      const aPx0 = rowPx(ai + 1), bPx0 = rowPx(bi + 1)
      const pairPx = aPx0 + bPx0, pairFr = gridRowFr[ai] + gridRowFr[bi]
      if (pairPx <= 0 || pairFr <= 0) return
      const pxPerFr = pairPx / pairFr, startY = e.clientY, MIN = 40
      g.setPointerCapture(e.pointerId)
      const onMove = ev => {
        const aPx = Math.max(MIN, Math.min(pairPx - MIN, aPx0 + (ev.clientY - startY)))
        gridRowFr[ai] = aPx / pxPerFr
        gridRowFr[bi] = (pairPx - aPx) / pxPerFr
        applyGridRows()
      }
      const onUp = () => {
        g.removeEventListener('pointermove', onMove)
        g.removeEventListener('pointerup', onUp)
        window.dispatchEvent(new Event('resize'))
      }
      g.addEventListener('pointermove', onMove)
      g.addEventListener('pointerup', onUp)
    })
  }

  // A corner button on each panel toggles maximize (fill the grid) / restore.
  // A button — not a canvas gesture — so it never triggers NiiVue's click/
  // double-click behavior (vertex pick, crosshair move, brightness reset).
  const toggleMaximize = cell => {
    const wasMax = cell.classList.contains('maxed')
    gridEl.querySelectorAll('.cell.maxed').forEach(c => c.classList.remove('maxed'))
    gridEl.classList.toggle('has-max', !wasMax)
    if (!wasMax) cell.classList.add('maxed')
    for (const b of gridEl.querySelectorAll('.maxbtn')) {
      const maxed = b.parentElement.classList.contains('maxed')
      b.textContent = maxed ? '⤡' : '⤢'
      b.title = maxed ? 'Restore panel' : 'Maximize panel'
    }
    requestAnimationFrame(() => window.dispatchEvent(new Event('resize')))
  }
  for (const cell of gridEl.querySelectorAll('.cell')) {
    const btn = document.createElement('button')
    btn.className = 'maxbtn'; btn.type = 'button'
    btn.textContent = '⤢'; btn.title = 'Maximize panel'
    btn.addEventListener('click', e => { e.stopPropagation(); e.preventDefault(); toggleMaximize(cell) })
    cell.appendChild(btn)
  }
}

window._nvSurf  = [nvLhL, nvRhL, nvAsym]
window._nvSlice = nvSlices
