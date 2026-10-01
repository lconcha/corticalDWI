import * as niivue from "__NIIVUE_CDN__"

const FA_URL      = "__FA_URL__"
const STREAMLINES = __STREAMLINES_JSON__   // {lh: url, rh: url}
const STEP_MM     = __STEP_MM__
const statusEl = document.getElementById('status')

// Mirrors main.js's theme handling (see CHART_THEME there) — kept independent
// since this is a separate page/script, synced only via the 'cbTheme'
// localStorage key (set on first load, and live via the 'storage' event below
// if the main tab's theme is changed while this tab stays open).
const SLIC_BACK_DARK  = [0.04, 0.04, 0.04, 1]
const SLIC_BACK_LIGHT = [0.8980, 0.9137, 0.9412, 1]   // Nord5 #E5E9F0
// "dark" and "nord-dark" share ACCENT_DARK's canvas look (see CHART_THEME in
// main.js); only the crosshair color differs between them.
const ACCENT = { dark: '#F5C842', light: '#5E81AC', 'nord-dark': '#88C0D0' }
const currentTheme = () => document.documentElement.getAttribute('data-theme') || 'dark'
const isLightTheme = () => currentTheme() === 'light'
const hexToRgba01 = hex => {
  const n = parseInt(hex.slice(1), 16)
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255, 1]
}
const accentRgba = () => hexToRgba01(ACCENT[currentTheme()])

const nv = new niivue.Niivue({
  backColor: isLightTheme() ? SLIC_BACK_LIGHT : SLIC_BACK_DARK, show3Dcrosshair: true,
  meshThicknessOn2D: 2, multiplanarLayout: 'row',
  isColorbar: true, showColorbarBorder: false,
  multiplanarShowRender: niivue.SHOW_RENDER.NEVER,   // just the 3 orthogonal slices, no 3-D volume panel
})
await new Promise(r => requestAnimationFrame(r))
await nv.attachTo('gl-dwi')
// attachTo() hardcodes canvas.parentElement.style.backgroundColor = "black" —
// an inline style, which beats any CSS class (including #canvas-wrap's themed
// background) regardless of specificity. Clear it so the CSS var takes over.
if (nv.canvas?.parentElement) nv.canvas.parentElement.style.backgroundColor = ''

let dwiCmap = 'lipari'   // colormap applied to whichever volume the orthoslices show; follows switches
if (FA_URL) await nv.loadVolumes([{ url: FA_URL, colormap: dwiCmap, opacity: 1 }])
nv.setSliceType(nv.sliceTypeMultiplanar)
nv.setRadiologicalConvention(true)
nv.setCrosshairColor(accentRgba())
nv.setCrosshairWidth(0.5)

// Live-sync if the main tab's theme toggle changes while this tab stays open.
// 'storage' only fires in *other* tabs than the one that wrote the key, which
// is exactly what's needed here — no feedback loop back to the main tab.
window.addEventListener('storage', e => {
  if (e.key !== 'cbTheme' || !(e.newValue in ACCENT)) return
  document.documentElement.setAttribute('data-theme', e.newValue)
  nv.opts.backColor = [...(isLightTheme() ? SLIC_BACK_LIGHT : SLIC_BACK_DARK)]
  nv.setCrosshairColor(accentRgba())
  if (nv.canvas?.parentElement) nv.canvas.parentElement.style.backgroundColor = ''
  nv.drawScene()
  // See the matching comment in main.js's applyNiivueTheme(): belt-and-suspenders
  // full repaint in case anything needs more than a bare drawScene().
  requestAnimationFrame(() => window.dispatchEvent(new Event('resize')))
})
// Right-drag brightness/contrast — same gesture override as the main tab's
// orthoslices: NiiVue's default right-button gesture draws a box and
// auto-windows to it, instead of the up/down=level, left/right=width drag
// every other neuroimaging viewer uses.
nv.setMouseEventConfig({ rightButton: niivue.DRAG_MODE.windowing })
// windowingGainFactor is intensity-units-per-pixel-dragged, NOT a fraction of
// the volume's range — NiiVue adds pixelsDragged*gainFactor straight onto
// cal_min/cal_max in the volume's own native units (global_min/global_max
// only clamp the result afterward, they don't scale the gain). So copying the
// main tab's flat 0.4 here is wrong: brain.nii.gz is FreeSurfer-normalized to
// roughly 0-255, but FA is bounded to roughly 0-1 by definition — the same
// absolute 0.4/pixel blows past FA's entire range in ~2 pixels of drag.
// Scale by this volume's own reported range instead, calibrated to the same
// 0.4-per-~255-range rate the main tab uses, so the two tabs feel the same
// regardless of what units the loaded volume happens to be in. Recalculated
// on every volume switch (see showVolume below) since a newly-loaded volume
// can have a completely different range.
function calibrateWindowingGain() {
  const bg = nv.volumes[0]
  if (!bg) return
  const RANGE_FRACTION_PER_PIXEL = 0.4 / 255   // main tab's calibration, as a fraction of range
  const range = (bg.global_max ?? 1) - (bg.global_min ?? 0)
  nv.opts.windowingGainFactor = RANGE_FRACTION_PER_PIXEL * range
}
calibrateWindowingGain()

// ── colormap + color-clip controls, kept in sync with the built-in colorbar ──
// Same pattern as the main tab's volCmapSel/volClipMin/volClipMax: NiiVue's
// own colorbar (isColorbar above) redraws itself from cal_min/cal_max/colormap,
// so these controls just read/write those three fields and it follows along.
// Declared at top level (not nested in an if-block) so showVolume() below can
// call them too — a function declared inside a block is block-scoped in a
// module, invisible outside it.
const cmapSel = document.getElementById('dwiCmapSel')
const clipMin = document.getElementById('dwiClipMin')
const clipMax = document.getElementById('dwiClipMax')
function syncClipInputs() {
  const bg = nv.volumes[0]
  if (!bg) return
  clipMin.value = (+bg.cal_min).toPrecision(4)
  clipMax.value = (+bg.cal_max).toPrecision(4)
}
function applyClip() {
  const bg = nv.volumes[0]
  if (!bg) return
  const mn = parseFloat(clipMin.value), mx = parseFloat(clipMax.value)
  if (!isFinite(mn) || !isFinite(mx) || mx <= mn) { syncClipInputs(); return }   // ignore invalid, restore
  bg.cal_min = mn; bg.cal_max = mx
  nv.updateGLVolume(); nv.drawScene()
}
clipMin.addEventListener('change', applyClip)
clipMax.addEventListener('change', applyClip)
if (nv.volumes.length) {
  const cmaps = (nv.colormaps ? nv.colormaps() : ['gray']).filter(n => !/^ct[-_]/i.test(n)).sort()
  cmapSel.innerHTML = cmaps.map(n =>
    `<option value="${n}"${n === dwiCmap ? ' selected' : ''}>${n}</option>`).join('')
  cmapSel.addEventListener('change', () => {
    dwiCmap = cmapSel.value
    const bg = nv.volumes[0]
    if (bg) { bg.colormap = dwiCmap; nv.updateGLVolume(); nv.drawScene() }
  })
  syncClipInputs()
  // Right-drag windowing changes cal_min/cal_max inside NiiVue directly (the
  // colorbar updates itself); mirror that range into the boxes too, same as
  // the main tab's nvSlices.onIntensityChange -> syncVolClipInputs.
  nv.onIntensityChange = () => syncClipInputs()
} else {
  cmapSel.disabled = true
  clipMin.disabled = true
  clipMax.disabled = true
}

// ── orthoslice volume selector ────────────────────────────────────────────
// Same registry pattern as the main tab's volSel/volFile/showVolume: each
// option is decoded+uploaded once on first selection, then kept resident (as
// a hidden, zero-opacity volume) so switching back to it later is instant.
const volSel  = document.getElementById('dwiVolSel')
const volFile = document.getElementById('dwiVolFile')
const volumeRegistry = {}   // key -> { name, url?|file?, blobUrl?, image?(NVImage) }
let currentVolKey = null
let volSeq = 0

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

  // Preserve the crosshair in world mm across the switch.
  let mm = null
  if (nv.volumes.length) {
    try { mm = nv.frac2mm([...nv.scene.crosshairPos]) } catch (e) {}
  }

  // First selection of this volume: decode + upload once, then keep it resident.
  if (!desc.image) {
    const item = { colormap: dwiCmap, opacity: 1 }
    if (desc.url) {
      item.url = desc.url
    } else if (desc.file) {
      if (!desc.blobUrl) desc.blobUrl = URL.createObjectURL(desc.file)
      item.url  = desc.blobUrl
      item.name = desc.file.name   // blob URLs carry no extension; let NiiVue infer the format
    }
    try {
      await nv.addVolumeFromUrl(item)   // add without dropping the resident volumes
    } catch (e) {
      console.warn('[volume] failed to load', desc.name, e)
      alert('Could not load volume: ' + desc.name)
      return
    }
    desc.image = nv.volumes[nv.volumes.length - 1]
    desc.defCalMin = desc.image.cal_min   // per-volume default window for the 'r' reset
    desc.defCalMax = desc.image.cal_max
  }

  desc.image.colormap = dwiCmap   // colormap follows the shown volume
  // Show only the chosen volume's pixels AND its colorbar; resident volumes
  // keep their own colormap but their colorbars stay hidden so they don't pile up.
  for (const v of nv.volumes) {
    const shown = (v === desc.image)
    v.opacity = shown ? 1 : 0
    v.colorbarVisible = shown
  }
  if (nv.volumes[0] !== desc.image) nv.setVolume(desc.image, 0)
  else nv.updateGLVolume()

  currentVolKey = key
  volSel.value = key
  nv.setCrosshairColor(accentRgba())
  nv.setCrosshairWidth(0.5)
  if (mm) {
    const frac = nv.mm2frac([mm[0], mm[1], mm[2]])
    if (frac) nv.scene.crosshairPos = [...frac]
  }
  if (typeof nv.createOnLocationChange === 'function') nv.createOnLocationChange()
  nv.drawScene()
  syncClipInputs()
  calibrateWindowingGain()   // the new volume can have a totally different intensity range
}

// Seed the dropdown: the already-loaded FA map (if any) links directly to its
// resident NVImage rather than re-adding it, then "other…" for arbitrary files.
if (FA_URL) {
  const img = nv.volumes[0] || null
  currentVolKey = addVolumeOption({
    name: 'fa.nii.gz', url: FA_URL, image: img,
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
  volFile.value = ''   // reset so the same file can be re-picked later
  if (!file) return
  showVolume(addVolumeOption({ name: file.name, file }, true))
})

// Show the nth loaded orthoslice volume (1-based), in dropdown order; 0 opens
// the "other…" file picker. Same shortcuts as the main tab's orthoslices.
function showVolumeByIndex(n) {
  const opts = [...volSel.options].filter(o => o.value !== '__other__')
  if (opts[n - 1]) showVolume(opts[n - 1].value)
}

// ── orthoslice zoom (Ctrl + scroll) ───────────────────────────────────────
let sliceZoom = 1
document.getElementById('gl-dwi').addEventListener('wheel', e => {
  if (!e.ctrlKey) return
  e.preventDefault(); e.stopImmediatePropagation()
  sliceZoom = Math.max(0.3, Math.min(8, sliceZoom * (e.deltaY < 0 ? 1.1 : 1/1.1)))
  nv.scene.pan2Dxyzmm[3] = sliceZoom; nv.drawScene()
}, {capture:true, passive:false})

// Reset the orthoslices: viewport (zoom + pan) and the shown volume's default
// window — same shortcut and behavior as the main tab's resetSliceView().
function resetDwiView() {
  sliceZoom = 1
  nv.scene.pan2Dxyzmm = [0, 0, 0, 1]
  const bg = nv.volumes[0], desc = volumeRegistry[currentVolKey]
  if (bg && desc && desc.defCalMin != null) {
    bg.cal_min = desc.defCalMin; bg.cal_max = desc.defCalMax
    nv.updateGLVolume()
    syncClipInputs()
  }
  nv.drawScene()
}

document.addEventListener('keydown', e => {
  const t = e.target
  if (t && (t.tagName === 'INPUT' || t.tagName === 'SELECT' ||
            t.tagName === 'TEXTAREA' || t.isContentEditable)) return
  if (e.ctrlKey || e.metaKey || e.altKey) return
  switch (e.key.toLowerCase()) {
    case '1': case '2': case '3': case '4': case '5':
    case '6': case '7': case '8': case '9':
      showVolumeByIndex(+e.key); e.preventDefault(); break
    case '0': volFile.click(); e.preventDefault(); break
    case 'r': resetDwiView(); e.preventDefault(); break
  }
})

// Same per-hemisphere accent colors as the main tab's Streamlines overlay.
const streamMeshes = {}
const [lhMesh, rhMesh] = await Promise.all([
  STREAMLINES.lh ? niivue.NVMesh.loadFromUrl({ url: STREAMLINES.lh, gl: nv.gl, rgba255: [102, 179, 255, 255] }) : null,
  STREAMLINES.rh ? niivue.NVMesh.loadFromUrl({ url: STREAMLINES.rh, gl: nv.gl, rgba255: [255, 133, 77, 255] }) : null,
])
for (const m of [lhMesh, rhMesh]) if (m) nv.addMesh(m)
streamMeshes.lh = lhMesh
streamMeshes.rh = rhMesh

let streamVisible = true       // "Streamlines: on/off" button
let streamMode = 'selected'    // 'selected' | 'all' — "Mode" button
let lastVertices = null        // most recent neighbor-ring set from the main tab (null until first sync)

// Same dps/dpsThreshold selection trick as the main tab's Streamlines section
// (see cortical_browser.py's setStreamlineSelection): flag the given vertex
// IDs' streamlines and threshold everything else out, rather than replacing
// the whole tractogram. Takes an array so "Selected vertex" mode can show the
// synced neighbor-ring set, not just the single primary vertex.
function setStreamlineSelection(mesh, vertexIds) {
  if (!mesh?.offsetPt0) return
  const n = mesh.offsetPt0.length - 1
  const flags = new Float32Array(n)
  for (const v of vertexIds) if (v >= 0 && v < n) flags[v] = 1
  mesh.dps = [{ id: 'vertex-selection', vals: flags }]
  nv.setMeshProperty(mesh.id, 'dpsThreshold', 0.5)
}
function showAllStreamlines() {
  for (const m of [streamMeshes.lh, streamMeshes.rh]) if (m) nv.setMeshProperty(m.id, 'dpsThreshold', NaN)
}
function applyStreamlineVisibility() {
  const op = streamVisible ? 1 : 0
  for (const m of [streamMeshes.lh, streamMeshes.rh]) if (m) nv.setMeshProperty(m.id, 'opacity', op)
  nv.drawScene()
}
// Re-applied whenever the mode button is clicked locally, or a fresh sync
// message arrives — mirrors the main tab's applyStreamlineSelection().
function applyStreamlineDisplay() {
  if (streamMode === 'all' || !lastVertices) showAllStreamlines()
  else {
    setStreamlineSelection(streamMeshes.lh, lastVertices)
    setStreamlineSelection(streamMeshes.rh, lastVertices)
  }
}

// The DWI-space streamlines are the exact warp target of the T1-space ones
// loaded in the main tab: point i of streamline v here IS the DWI-space
// location of point i of streamline v there. So a (vertex, depth) pair
// selected in T1 space indexes directly into this mesh's own pts/offsetPt0 —
// no coordinate transform needed, just the same lookup the main tab's
// streamline-selection feature already does.
function placeCrosshairAtStreamlinePoint(mesh, vertex, depth) {
  if (!mesh?.offsetPt0 || !nv.volumes.length) return null
  const start = mesh.offsetPt0[vertex]
  const end   = mesh.offsetPt0[vertex + 1]
  if (start === undefined || end === undefined || end <= start) return null
  const idx = start + Math.max(0, Math.min(end - start - 1, depth))
  const xyz = [mesh.pts[idx * 3], mesh.pts[idx * 3 + 1], mesh.pts[idx * 3 + 2]]
  const frac = nv.mm2frac(xyz)
  if (!frac) return null
  nv.scene.crosshairPos = [...frac]
  if (typeof nv.createOnLocationChange === 'function') nv.createOnLocationChange()
  nv.drawScene()
  return xyz
}

const dwiChannel = ('BroadcastChannel' in window) ? new BroadcastChannel('cortical-browser-dwi-crosshair') : null
if (dwiChannel) {
  dwiChannel.onmessage = ev => {
    const { vertex, vertices, depth, hemi } = ev.data || {}
    if (!Number.isInteger(vertex)) return
    lastVertices = Array.isArray(vertices) && vertices.length ? vertices : [vertex]
    const primary = (hemi === 'rh' ? streamMeshes.rh : streamMeshes.lh) || streamMeshes.lh || streamMeshes.rh
    const xyz = primary ? placeCrosshairAtStreamlinePoint(primary, vertex, depth || 0) : null
    applyStreamlineDisplay()
    statusEl.textContent = xyz
      ? `vertex ${vertex} (${hemi || 'lh'}) · depth ${((depth || 0) * STEP_MM).toFixed(1)} mm · ${xyz[0].toFixed(1)},${xyz[1].toFixed(1)},${xyz[2].toFixed(1)} mm`
      : `vertex ${vertex}: no streamline point at that depth`
  }
  // Announce readiness now that the listener above is actually live — the
  // main tab responds by re-sending its current selection. Without this, a
  // selection made in the main tab just before this tab finished loading
  // (the common case: pick a vertex, then click "Open DWI space") would be
  // silently lost, since BroadcastChannel doesn't queue messages for
  // listeners that don't exist yet.
  dwiChannel.postMessage({ type: 'dwi-ready' })
} else {
  statusEl.textContent = "this browser doesn't support BroadcastChannel — can't sync with the main tab"
}

// ── streamline show/hide + all-vs-selected buttons ───────────────────────────
{
  const visBtn  = document.getElementById('dwiStreamVisBtn')
  const modeBtn = document.getElementById('dwiStreamModeBtn')
  if (!streamMeshes.lh && !streamMeshes.rh) {
    visBtn.disabled = true
    modeBtn.disabled = true
    visBtn.title = modeBtn.title = 'No DWI-space streamlines found for this subject'
  } else {
    visBtn.addEventListener('click', () => {
      streamVisible = !streamVisible
      visBtn.textContent = `Streamlines: ${streamVisible ? 'on' : 'off'}`
      applyStreamlineVisibility()
    })
    modeBtn.addEventListener('click', () => {
      streamMode = streamMode === 'selected' ? 'all' : 'selected'
      modeBtn.textContent = `Mode: ${streamMode}`
      applyStreamlineDisplay()
    })
  }
}
