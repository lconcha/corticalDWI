import * as niivue from "__NIIVUE_CDN__"

// ── injected by Python ──────────────────────────────────────────────────────
const BASE_URL   = "__BASE_URL__"
const IS_SCALAR  = __IS_SCALAR_JSON__
const N_VERTS    = { lh: __N_VERTS_LH__, rh: __N_VERTS_RH__ }

const LH_RGBA = [102, 179, 255, 255]
const RH_RGBA = [255, 133, 77, 255]
const SURF_CFG = { backColor: [0.06, 0.06, 0.06, 1], show3Dcrosshair: false }

const nvLh = new niivue.Niivue(SURF_CFG)
const nvRh = new niivue.Niivue(SURF_CFG)

await new Promise(r => requestAnimationFrame(r))
await Promise.all([nvLh.attachTo('gl-lh'), nvRh.attachTo('gl-rh')])

await Promise.all([
  nvLh.loadMeshes([{ url: `${BASE_URL}/surf/lh.surf.gii`, rgba255: new Uint8Array(LH_RGBA) }]),
  nvRh.loadMeshes([{ url: `${BASE_URL}/surf/rh.surf.gii`, rgba255: new Uint8Array(RH_RGBA) }]),
])

// ── surface vertex picking ──────────────────────────────────────────────────
// Software-rasterization pick, mirroring NiiVue's own orthographic camera
// transform exactly (see cortical_browser's main.js, same function) — NiiVue
// itself doesn't expose a mesh vertex-pick API, so every triangle is pushed
// through the same model/view transform the GPU uses and rasterized here;
// nearest-to-camera wins among any triangle whose 2D shape contains the click,
// which respects occlusion the way a GPU depth buffer would.
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
    const z2 = y1*sx + z0*cx
    const mx = -x1
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
    if (w0 < -1e-6 || w1 < -1e-6 || w2 < -1e-6) continue
    const depth = w0*szArr[i0] + w1*szArr[i1] + w2*szArr[i2]
    if (depth < bestDepth) {
      bestDepth = depth
      bestVert = (w0 >= w1 && w0 >= w2) ? i0 : (w1 >= w2 ? i1 : i2)
    }
  }
  return bestVert
}

async function pickOnSurface(canvas, mouseX, mouseY, nvInst, hemi) {
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
  if (vertIdx < 0) return
  await onVertexPicked(hemi, vertIdx)
}

function setupSurfacePicker(canvasId, nvInst, hemi) {
  const canvas = document.getElementById(canvasId)
  let downX = 0, downY = 0
  canvas.addEventListener('mousedown', e => { downX = e.clientX; downY = e.clientY })
  canvas.addEventListener('mouseup', e => {
    const dx = e.clientX - downX, dy = e.clientY - downY
    if (dx*dx + dy*dy > 25) return   // a drag (rotate/pan), not a click
    pickOnSurface(canvas, e.clientX, e.clientY, nvInst, hemi)
  })
  canvas.addEventListener('wheel', e => {
    e.preventDefault(); e.stopImmediatePropagation()
    const factor = e.deltaY < 0 ? 1.1 : 1/1.1
    const cur = nvInst.scene.volScaleMultiplier || 1
    nvInst.scene.volScaleMultiplier = Math.max(0.05, Math.min(100, cur * factor))
    nvInst.drawScene()
  }, { capture: true, passive: false })
}
setupSurfacePicker('gl-lh', nvLh, 'lh')
setupSurfacePicker('gl-rh', nvRh, 'rh')

// ── picked-vertex marker (yellow sphere) ────────────────────────────────────
// Built by hand (icosahedron, one subdivision) rather than loaded from a
// file — NiiVue has no "add a sphere primitive" call, but its public
// addMesh()/NVMesh API happily takes any pts/tris mesh we hand it, so a
// small sphere mesh dropped at the picked vertex's coordinates and recolored
// yellow works exactly like any other loaded mesh (see NVMesh/addMesh in
// NiiVue's own source — not documented, found by reading the bundled JS).
function buildIcosphere(radius) {
  const t = (1 + Math.sqrt(5)) / 2
  const verts = [
    [-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0],
    [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
    [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1],
  ].map(v => { const l = Math.hypot(...v); return [v[0]/l, v[1]/l, v[2]/l] })
  const faces = [
    [0,11,5],[0,5,1],[0,1,7],[0,7,10],[0,10,11],
    [1,5,9],[5,11,4],[11,10,2],[10,7,6],[7,1,8],
    [3,9,4],[3,4,2],[3,2,6],[3,6,8],[3,8,9],
    [4,9,5],[2,4,11],[6,2,10],[8,6,7],[9,8,1],
  ]
  const pts = new Float32Array(verts.length * 3)
  verts.forEach((v, i) => { pts[i*3] = v[0]*radius; pts[i*3+1] = v[1]*radius; pts[i*3+2] = v[2]*radius })
  const tris = new Uint32Array(faces.length * 3)
  faces.forEach((f, i) => { tris[i*3] = f[0]; tris[i*3+1] = f[1]; tris[i*3+2] = f[2] })
  return { pts, tris }
}

const YELLOW = new Uint8Array([255, 221, 0, 255])
const markerMesh = { lh: null, rh: null }
const markerVertex = { lh: null, rh: null }

function showVertexMarker(hemi, vertex) {
  if (markerVertex[hemi] === vertex) return
  const nvInst = hemi === 'lh' ? nvLh : nvRh
  const surf = nvInst.meshes[0]   // surface mesh is always loaded first, see loadMeshes() above
  if (!surf?.pts) return
  const cx = surf.pts[vertex*3], cy = surf.pts[vertex*3+1], cz = surf.pts[vertex*3+2]
  if (markerMesh[hemi]) { nvInst.removeMesh(markerMesh[hemi]); markerMesh[hemi] = null }
  const { pts, tris } = buildIcosphere(1.6)
  for (let i = 0; i < pts.length; i += 3) { pts[i] += cx; pts[i+1] += cy; pts[i+2] += cz }
  const marker = new niivue.NVMesh(pts, tris, 'vertex-marker', YELLOW, 1, true, nvInst.gl)
  nvInst.addMesh(marker)
  nvInst.drawScene()
  markerMesh[hemi] = marker
  markerVertex[hemi] = vertex
}

// ── controls ─────────────────────────────────────────────────────────────────
const metricSel    = document.getElementById('metricSel')
const covariateSel = document.getElementById('covariateSel')
const depthWrap    = document.getElementById('depthWrap')
const depthRange   = document.getElementById('depthRange')
const depthVal     = document.getElementById('depthVal')
const statusEl     = document.getElementById('status')
const vertexHemiSel = document.getElementById('vertexHemiSel')
const vertexInput   = document.getElementById('vertexInput')
const vertexGoBtn   = document.getElementById('vertexGoBtn')

let lastPick = null   // { hemi, vertex }

function updateVertexInputBounds() {
  vertexInput.max = N_VERTS[vertexHemiSel.value] - 1
}
updateVertexInputBounds()
vertexHemiSel.addEventListener('change', updateVertexInputBounds)

function goToVertexInput() {
  const hemi = vertexHemiSel.value
  const v = Number(vertexInput.value)
  if (!Number.isInteger(v) || v < 0 || v >= N_VERTS[hemi]) {
    statusEl.textContent = `invalid vertex id for ${hemi} — must be an integer in [0, ${N_VERTS[hemi] - 1}]`
    return
  }
  onVertexPicked(hemi, v)
}
vertexInput.addEventListener('keydown', e => { if (e.key === 'Enter') goToVertexInput() })
vertexGoBtn.addEventListener('click', goToVertexInput)

function currentMetricIsScalar() {
  return !!IS_SCALAR[Number(metricSel.value)]
}

function refreshDepthUI() {
  const scalar = currentMetricIsScalar()
  depthWrap.style.display = scalar ? 'none' : 'flex'
  if (scalar) depthRange.value = 0
}
refreshDepthUI()
depthRange.addEventListener('input', () => { depthVal.textContent = depthRange.value; refetch() })
metricSel.addEventListener('change', () => { refreshDepthUI(); refetch() })
covariateSel.addEventListener('change', refetch)

function refetch() {
  if (lastPick) onVertexPicked(lastPick.hemi, lastPick.vertex)
}

async function onVertexPicked(hemi, vertex) {
  lastPick = { hemi, vertex }
  vertexHemiSel.value = hemi
  vertexInput.value = vertex
  showVertexMarker(hemi, vertex)
  const covariate = covariateSel.value
  if (!covariate) {
    statusEl.textContent = `${hemi} vertex ${vertex} — no covariate fit available ` +
      `(run cortical_zscore_tsf.py --stats-only --adjust-for <col> first)`
    return
  }
  const depth = currentMetricIsScalar() ? 0 : Number(depthRange.value)
  statusEl.textContent = `loading ${hemi} vertex ${vertex}…`
  const url = `${BASE_URL}/vertex?hemi=${hemi}&metric=${metricSel.value}&depth=${depth}` +
              `&covariate=${encodeURIComponent(covariate)}&vertex=${vertex}`
  let data
  try {
    const r = await fetch(url)
    if (!r.ok) throw new Error(await r.text())
    data = await r.json()
  } catch (e) {
    statusEl.textContent = `${hemi} vertex ${vertex} — error: ${e.message}`
    return
  }
  renderScatter(data)
  const depthTxt = currentMetricIsScalar() ? '' : ` depth ${depth}`
  statusEl.textContent = `${hemi} vertex ${vertex}${depthTxt} — n=${data.fit.n ?? 0}`
}

function fmtP(p) {
  if (p == null) return '—'
  return p < 1e-4 ? p.toExponential(2) : p.toFixed(4)
}
function fmtNum(v, d = 3) { return v == null ? '—' : v.toFixed(d) }

function renderScatter(data) {
  const { x, y, fit, metric, covariate } = data
  const traces = [{
    x, y, mode: 'markers', type: 'scatter', name: 'cohort subjects',
    marker: { color: '#66B3FF', size: 7, opacity: 0.85 },
    hovertemplate: `${covariate}: %{x}<br>${metric}: %{y}<extra></extra>`,
  }]
  if (fit.a != null && fit.b != null && x.length) {
    const xmin = Math.min(...x), xmax = Math.max(...x)
    traces.push({
      x: [xmin, xmax], y: [fit.a + fit.b * xmin, fit.a + fit.b * xmax],
      mode: 'lines', type: 'scatter', name: 'fitted model',
      line: { color: '#F5C842', width: 2 },
    })
  }
  const title = fit.a == null
    ? `${metric} vs ${covariate} — fit unavailable at this vertex/depth (n=${fit.n})`
    : `${metric} vs ${covariate}<br>` +
      `<span style="font-size:11px;color:#8a9099">slope=${fmtNum(fit.b)}  intercept=${fmtNum(fit.a)}  ` +
      `residual SD=${fmtNum(fit.rs)}  n=${fit.n}  p(slope)=${fmtP(fit.p)}</span>`
  Plotly.react('scatter', traces, {
    title: { text: title, font: { size: 13, color: '#d7dadd' } },
    xaxis: { title: covariate, color: '#8a9099', gridcolor: '#2a2e33' },
    yaxis: { title: metric,    color: '#8a9099', gridcolor: '#2a2e33' },
    paper_bgcolor: '#101214', plot_bgcolor: '#101214',
    font: { color: '#d7dadd' },
    margin: { t: 60, r: 20, b: 50, l: 60 },
    showlegend: true, legend: { font: { color: '#d7dadd' } },
  }, { responsive: true })
}

Plotly.newPlot('scatter', [], {
  paper_bgcolor: '#101214', plot_bgcolor: '#101214', font: { color: '#8a9099' },
  annotations: [{ text: 'click a vertex to see cohort data here', showarrow: false,
                  xref: 'paper', yref: 'paper', x: 0.5, y: 0.5, font: { size: 13 } }],
})
