import * as niivue from "__NIIVUE_CDN__"

// ── injected by Python ────────────────────────────────────────────────────────
const VOLUMES  = __VOLUMES_JSON__
const SURFS    = __SURFS_JSON__
const SURF_TYPES = __SURF_TYPES_JSON__
const STREAMLINES = __STREAMLINES_JSON__
const DWI_AVAILABLE = __DWI_AVAILABLE_JSON__
const NORMATIVE = __NORMATIVE_JSON__
const METRICS  = __METRICS_JSON__
// Metrics that also have per-vertex z-score tsf siblings (cortical_zscore_tsf.py),
// with their own symmetric (signed) cal ranges — see zscore_cal_range() in Python.
const ZSCORE   = __ZSCORE_JSON__
const BASE_URL = "__BASE_URL__"
// Per-launch cache-buster: appended to every /data/ fetch so an immutable-cached
// file from a previous subject (same port, same URL) can't leak into this one.
const CACHE_BUST = "__CACHE_BUST__"
const Q = CACHE_BUST ? `?v=${CACHE_BUST}` : ''
const TEMPLATE = "__TEMPLATE__"
const STEP_MM  = __STEP_MM__

// Selected-vertex accent color, shared across the vertex box (CSS --accent-yellow)
// and, in dark theme, the orthoslice crosshair and plots' depth reference line
// (both of those follow the theme — see accentRgba()/CT below).
const ACCENT_YELLOW = '#F5C842'

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
// Half-width "dead zone" around zero shown as solid white/neutral on the
// bwr/cwr/gwr diverging colormaps (0 disables — plain two-stop gradient).
// Independent per panel group, same as the min/max limits they pair with.
let currentClimThresh = 0, currentAsymThresh = 0
// Orthoslice surface contours are off by default and lazily loaded per kind.
let nRings = 0
let currentVertex = null
let pivotAtVertex = false
// Multiplier on the selected-vertex/neighbor-ring marker spheres' base
// radius (itself a fraction of the mesh bounding radius — see placeMarker)
// — adjustable via the '>'/'<' shortcuts, applied uniformly so the
// neighbor spheres (always 30% of the seed's radius) scale right along
// with the main one.
let vertexSphereScale = 1
// Hidden feature (Alt+Shift+V / Alt+Shift+N — see promptVertexMarkerColor/
// promptNeighborMarkerColor): [r,g,b] (0-255) override for the selected-
// vertex / neighbor-ring marker spheres, otherwise hardcoded to 'warm'
// (yellow) / 'gray' (white) — see markerConnectomeJSON/neighborConnectomeJSON.
// null means "use the default colormap", not "any override yet applied".
let vertexMarkerColorOverride = null
let neighborMarkerColorOverride = null
// Hidden feature (Alt+Shift+L / Alt+Shift+R / Alt+Shift+W — see
// promptLhSurfColor/promptRhSurfColor/setAllSurfacesWhite): [r,g,b]
// (0-255) override for each hemisphere's surface base tint — the color a
// vertex shows through at wherever the data overlay doesn't cover it (e.g.
// opacity < 1, or an explicit "no data" mask), normally LH_SURF/RH_SURF.
// rgba255 (the same blue/orange used for the LH/RH plot lines). null means
// "use the default", not "any override yet applied". The Asym panel always
// mirrors the LH override, same as it already shares LH's geometry and
// "no data" mask color (MASK_CMAP_FOR) — see applyLhSurfColor.
let lhSurfColorOverride = null
let rhSurfColorOverride = null
let showNormative = false
// Z-score mode: surfaces/profiles read the metric's _zscore tsf siblings
// instead of its raw values. Per-metric (hasZscore), not global — see
// updateZscoreToggleAvailability().
let showZscore = false
function hasZscore(metric) { return !!(metric && ZSCORE[metric]) }
// The stats (n_depths/cal ranges) that currently drive the surfaces/plots:
// the metric's own in raw mode, its z-score sibling's in z-score mode.
function activeMetricInfo(metric) {
  return (showZscore && hasZscore(metric)) ? ZSCORE[metric] : METRICS[metric]
}
// Collapse-depth mode: the lh/rh/asym surfaces show one value per vertex
// (the mean across every depth) instead of a depth-indexed frame — works for
// whatever's currently displayed, z-scored or raw (see meanPerVertex). The
// depth-profile plots are untouched: they stay depth-resolved, and the depth
// slider/+-/plot-click still move their reference marker — setDepth() just
// stops pushing that depth onto the surfaces (frame4D) while this is on.
let collapseDepth = false
function canCollapseDepth(metric) { return !!metric }
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

// ── Plotly chart theming ─────────────────────────────────────────────────────
// Unlike LH_COLOR/RH_COLOR above (which must stay tied 1:1 to the 3-D mesh
// color), the *plotted* hemisphere/asymmetry colors need a darker, more
// saturated variant on a light background to stay legible — chartColorFor()
// derives that variant by hue, so the plot line still reads as "the same
// color" as the surface. (The 3-D/orthoslice canvases' own backColor is themed
// separately, see SURF_CFG/SLIC_CFG/applyNiivueTheme() further down.)
function hexToHsl(hex) {
  const n = parseInt(hex.slice(1), 16)
  const r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min
  let h = 0
  if (d !== 0) {
    switch (max) {
      case r: h = ((g - b) / d) % 6; break
      case g: h = (b - r) / d + 2; break
      default: h = (r - g) / d + 4
    }
    h *= 60
    if (h < 0) h += 360
  }
  const l = (max + min) / 2
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1))
  return [h, s, l]
}
function hslToHex(h, s, l) {
  const c = (1 - Math.abs(2 * l - 1)) * s
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1))
  const m = l - c / 2
  const [r, g, b] =
    h < 60  ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] :
    h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x]
  const toHex = v => Math.round((v + m) * 255).toString(16).padStart(2, '0')
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`
}
function chartColorFor(hex, light) {
  if (!light) return hex
  const [h, s] = hexToHsl(hex)
  return hslToHex(h, Math.max(s, 0.7), 0.38)
}
const ASYM_BASE_COLOR = '#8af5a6'

const CHART_THEME = {
  dark:  { bg: '#242424', text: PLOT_TEXT, grid: '#303030', gridPolar: '#3a3a3a',
           zero: '#888888', accent: ACCENT_YELLOW,
           normative: '#ffffff', normativeFill: 'rgba(160,160,160,0.30)' },
  light: { bg: '#FFFFFF', text: '#2E3440', grid: '#D8DEE9', gridPolar: '#D8DEE9',
           zero: '#4C566A', accent: '#5E81AC',
           normative: '#3B4252', normativeFill: 'rgba(76,86,106,0.18)' },
  // Nord Dark reuses "dark"'s canvas/chart look wholesale (same rationale as
  // the CSS --cell-bg/--chart-bg not being overridden for it) — nord8
  // (#88C0D0, the signature "Nord blue") is the only thing that changes here.
  'nord-dark': { bg: '#242424', text: PLOT_TEXT, grid: '#303030', gridPolar: '#3a3a3a',
                 zero: '#888888', accent: '#88C0D0',
                 normative: '#ffffff', normativeFill: 'rgba(160,160,160,0.30)' },
}
// Defaults to 'dark' when unset, matching the CSS :root default and the
// pre-paint script in <head> (no stored localStorage value = plain dark).
const currentTheme = () => document.documentElement.getAttribute('data-theme') || 'dark'
// Only "light" needs the pastel hemisphere/asym colors darkened for
// contrast (see chartColorFor) and a light NiiVue canvas — "dark" and
// "nord-dark" both keep the original near-black canvas look.
const isLightTheme = () => currentTheme() === 'light'
const hexToRgba01 = hex => {
  const n = parseInt(hex.slice(1), 16)
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255, 1]
}
const accentRgba = () => hexToRgba01(CHART_THEME[currentTheme()].accent)
let CT = CHART_THEME[currentTheme()]
let chartLhColor   = chartColorFor(LH_COLOR, isLightTheme())
let chartRhColor   = chartColorFor(RH_COLOR, isLightTheme())
let chartAsymColor = chartColorFor(ASYM_BASE_COLOR, isLightTheme())

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
// backColor is read live on every redraw (NiiVue's clearBounds() does
// gl.clearColor(...opts.backColor) each frame), so it's just as easy to flip
// on a theme change as any CSS variable — see applyNiivueTheme() below.
const SURF_BACK_DARK  = [0.06, 0.06, 0.06, 1]
const SURF_BACK_LIGHT = [0.9255, 0.9373, 0.9569, 1]   // Nord6 #ECEFF4
const SLIC_BACK_DARK  = [0.04, 0.04, 0.04, 1]
const SLIC_BACK_LIGHT = [0.8980, 0.9137, 0.9412, 1]   // Nord5 #E5E9F0
const SURF_CFG = { backColor: isLightTheme() ? SURF_BACK_LIGHT : SURF_BACK_DARK, show3Dcrosshair: false }
const SLIC_CFG = {
  backColor: isLightTheme() ? SLIC_BACK_LIGHT : SLIC_BACK_DARK, show3Dcrosshair: true,
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
// attachTo() hardcodes canvas.parentElement.style.backgroundColor = "black" —
// an inline style, which beats any CSS class (including our themed .cell
// background) regardless of specificity tricks. Clear it so .cell's
// var(--cell-bg) takes over; it's barely visible for the surface panels
// (the mesh render fills almost the whole canvas) but very visible around
// the orthoslice panel's .cfoot toolbar, which sits outside the canvas.
for (const nv of [nvLhL, nvRhL, nvAsym, nvSlices]) {
  if (nv.canvas?.parentElement) nv.canvas.parentElement.style.backgroundColor = ''
}

// ── custom diverging colormaps ────────────────────────────────────────────────
// Every diverging colormap is defined by its own 256-entry BASE LUT —
// color0 -> white/neutral -> color1, centered at index 127.5 — either our
// own hand-rolled 2-color gradient (bwr/gwr/cwr) or one sampled straight
// from matplotlib (MPL_DIVERGING_HEX below). buildDivergingCmap() and
// buildOneSidedDivergingCmap() then remap that SAME base shape across any
// data range + significance threshold, regardless of which kind it is.

// 256-entry base LUT from two endpoint colors through white — this is all
// bwr/gwr/cwr ever were before matplotlib's richer colormaps were added.
function twoColorBaseLUT(r0, g0, b0, r1, g1, b1) {
  const R = [], G = [], B = []
  for (let i = 0; i < 256; i++) {
    const t = i / 255
    if (t <= 0.5) {
      const s = t * 2
      R.push(r0 + s * (255 - r0)); G.push(g0 + s * (255 - g0)); B.push(b0 + s * (255 - b0))
    } else {
      const s = (t - 0.5) * 2
      R.push(255 - s * (255 - r1)); G.push(255 - s * (255 - g1)); B.push(255 - s * (255 - b1))
    }
  }
  return { R, G, B }
}
// 256 RGB samples (as a 1536-char "rrggbb"-per-entry hex string) taken
// straight from each matplotlib diverging colormap — generated once via
// `cmap(np.linspace(0, 1, 256))` in a local Python/matplotlib shell and
// pasted in statically here, so there's no runtime Python dependency.
const MPL_DIVERGING_HEX = {
  PiYG: '8e015290025492035594045797055999065a9b075c9d085e9f095fa10a61a40b63a60c65a80d66aa0e68ac0f6aae106bb1116db3126fb51370b71472b91574bb1675bd1777c01879c2197ac41a7cc51d7ec62080c72482c82884c92b86ca2f88cb3289cc368bcd3a8dce3d8fcf4191d04493d14895d24c97d34f99d4539bd5579dd65a9fd75ea1d861a2d965a4da69a6db6ca8dc70aadd73acde77aedf79b0df7cb1e07eb3e181b5e283b7e286b8e388bae48bbce58dbee590bfe692c1e795c3e897c4e89ac6e99cc8ea9fcaeba1cbeba3cdeca6cfeda8d1eeabd2eeadd4efb0d6f0b2d7f1b5d9f1b7daf2b8dbf2badcf3bcddf3bddef4bfdff4c1dff5c2e0f5c4e1f5c6e2f6c7e3f6c9e3f7cbe4f7cce5f8cee6f8d0e7f9d1e8f9d3e8fad4e9fad6eafbd8ebfbd9ecfcdbedfcddedfddeeefde0effde1effde2f0fce3f0fce4f0fce5f1fce5f1fbe6f1fbe7f2fbe8f2fbe9f2faeaf2faebf3faecf3faedf3f9eef4f9eef4f9eff4f9f0f5f9f1f5f8f2f5f8f3f6f8f4f6f8f5f6f7f6f7f7f7f7f7f7f6f6f7f5f5f7f3f5f7f2f4f7f0f3f7eff3f6edf2f6ecf1f6eaf1f6e8f0f6e7eff6e5eff6e4eef6e2edf6e1edf6dfecf6deebf6dcebf6dbeaf5d9e9f5d8e9f5d6e8f5d5e7f5d3e7f5d2e6f5d0e4f4cde2f3cae1f3c7dff2c4ddf1c1dbf0bfd9f0bcd8efb9d6eeb6d4edb3d2ecb0d0ecadcfebaacdeaa7cbe9a4c9e8a2c7e89fc6e79cc4e699c2e596c0e593bee490bde38dbbe28ab9e187b7e085b5df82b2dd7fb0dc7daeda7aacd977a9d874a7d672a5d56fa3d36ca1d26a9ed0679ccf649acd6198cc5f95cb5c93c95991c8578fc6548cc5518ac34f88c24c86c04983bf4681bd447fbc417dba407bb93e79b73d77b53c75b43b73b23971b0386faf376dad366bac3469aa3367a83266a73164a52f62a32e60a22d5ea02c5c9e2a5a9d29589b285699275498255296245094234e93224c91214b8f21498d20488c20468a2045881f43861f42841f40831e3f811e3d7f1e3c7d1d3a7b1d397a1d37781c36761c34741c33721c31711b306f1b2e6d1b2d6b1a2b691a2a681a286619276419',
  PRGn: '40004b42024d44034f4605524807544b08564d0a584f0c5a510d5d530f5f5510615712635914655c15685e176a60196c621a6e641c70661e73681f756a21776c23796f247b71267e732880752982772b84782e857931877b34887c368a7e398c7f3c8d803f8f824190834492844793864a95874c97894f988a529a8b559b8d579d8e5a9e8f5da09160a29262a39465a59568a6966ba8986da99970ab9b72ac9c74ae9e76af9f78b1a17ab2a37cb3a47fb5a681b6a783b8a985b9ab87bbac89bcae8bbdb08dbfb18fc0b391c2b493c3b695c4b897c6b99ac7bb9cc9bc9ecabea0cbc0a2cdc1a4cec3a6cfc4a8d0c6aad1c7abd2c9add3caafd4cbb1d5cdb3d6ceb5d7d0b7d8d1b8d9d3badad4bcdbd6bedcd7c0ddd8c2dedac3dfdbc5e0ddc7e1dec9e2e0cbe3e1cde4e3cee5e4d0e6e6d2e7e7d4e8e8d5e9e8d7e9e9d8eaead9eaeadbebebdcecebdeececdfedede0edede2eeeee3eeefe4efefe6f0f0e7f0f0e9f1f1eaf1f2ebf2f2edf3f3eef3f4eff4f4f1f4f5f2f5f5f4f6f6f5f6f7f6f7f6f7f6f5f7f5f4f6f3f3f6f2f2f6f1f1f5efeff5eeeef5ecedf5ebecf4eaebf4e8e9f4e7e8f4e5e7f3e4e6f3e3e5f3e1e4f2e0e2f2dee1f2dde0f2dbdff1dadef1d9ddf1d7dbf1d6daf0d4d9f0d3d7efd1d5eecfd3eecdd1edcbcfecc9cdebc7cbeac5c9e9c3c7e9c1c5e8bfc3e7bdc1e6bbbfe5b9bde4b7bbe4b5b9e3b3b7e2b1b5e1afb3e0adb1e0abafdfa9addea7abdda5a9dca3a7dba1a5da9fa2d89c9fd79a9cd59799d39596d19293d09090ce8d8dcc8b8aca8987c88684c78481c5817ec37f7bc17c78c07a75be7772bc756fba726cb97069b76d66b56b63b36860b2665db0635aae6158ac5f55aa5e53a85c50a65a4ea3594ba157499f55469d54449b524199513f974f3c954d3a924c37904a358e48328c47308a452e88432b864229844026823e247f3d217d3b1f7b391c79381a7736197535187334177133166f32156d31146b3013692f12672e11652d10632b0f612a0e5f290d5c280c5a270b58260a5625085424075223065022054e20044c1f034a1e02481d01461c00441b',
  BrBG: '5430055631055833055b34065d35065f3606613806633906663a07683c076a3d076c3e076e40077141087342087543087745087946087c47097e4909804a09824b09844c09874e0a894f0a8b500a8d520b8f540c91560d93580f955910975b12995d139b5f149d61169f6317a16518a3671aa5691ba76a1da96c1eab6e1fad7021af7222b17423b37625b57826b77928b97b29bb7d2abd7f2cbf812dc08430c28633c38936c48b3ac58e3dc79040c89343c99546ca9849cc9a4ccd9d50cea053cfa256d1a559d2a75cd3aa5fd4ac62d6af65d7b169d8b46cd9b76fdbb972dcbc75ddbe78dec17bdfc37ee0c481e1c684e2c787e3c989e4ca8ce5cc8fe6cd92e7cf94e8d097e8d29ae9d39dead59febd6a2ecd8a5edd9a8eedbaaefdcadf0deb0f1dfb3f1e1b5f2e2b8f3e4bbf4e5bef5e7c0f6e8c3f6e9c5f6e9c7f6eac9f6eacbf6ebcdf6ebcff6ecd1f6ecd3f6edd5f6edd7f6eed9f6eedbf5efdcf5efdef5f0e0f5f0e2f5f1e4f5f1e6f5f2e8f5f2eaf5f3ecf5f3eef5f4f0f5f4f2f5f5f4f4f5f5f2f4f4f0f4f3eff3f3edf3f2ebf3f2e9f2f1e7f2f0e6f1f0e4f1efe2f0eee0f0eedef0edddefeddbefecd9eeebd7eeebd5edead4ede9d2ede9d0ece8ceece8ccebe7cbebe6c9eae6c7eae5c4e9e4c1e8e2bfe7e1bce5dfb9e4deb6e3ddb4e2dbb1e1daaee0d8abdfd7a8ddd5a6dcd4a3dbd3a0dad19dd9d09ad8ce98d7cd95d6cc92d4ca8fd3c98dd2c78ad1c687d0c584cfc381cec27fccc07ccabe79c8bc76c6ba73c3b870c1b66dbfb46abdb267bbb064b9ae61b7ac5eb5aa5bb3a858b0a755aea552aca34faaa14da89f4aa69d47a49b44a299419f973e9d953b9b9338999135978f33958d31938b2f91892d8f872b8d85298b83278a8225888023867e21847c1f827a1d80781a7e76187c74167a7210746c0e726a0c71690a6f67086d65066b6304696102675f01655d01645b016259016058015f56015d54015b52015a5001584f01564d01554b015349015147005046004e44004c42004b4000493e00483d00463b004439004337004135003f34003e32003c30',
  PuOr: '7f3b08813c08833d08853e088740088941088b42088d43078f44079145079346079548079749079a4a079c4b079e4c07a04d07a24e07a44f07a65107a85206aa5306ac5406ae5506b05606b25706b45906b65a07b75c07b95e08bb5f08bd6109be630ac0640ac2660bc4680bc6690cc76b0cc96d0dcb6e0dcd700ece720fd0730fd27510d47610d57811d77a11d97b12db7d12dc7f13de8013e08214e18417e2861ae3881de58a20e68d23e78f27e8912ae9932dea9530eb9733ed9936ee9b39ef9e3cf0a03ff1a242f2a446f3a649f4a84cf6aa4ff7ac52f8ae55f9b158fab35bfbb55efcb761fdb965fdba68fdbc6bfdbd6efdbf72fdc175fdc278fdc47bfdc57ffdc782fdc885fdca88fdcc8cfecd8ffecf92fed095fed299fed39cfed59ffed7a2fed8a6fedaa9fedbacfeddaffedeb3fee0b6fee1b9fde2bbfde3befde4c0fde5c3fce5c5fce6c8fce7cafce8cdfbe9cffbead2fbebd5faecd7faeddafaeedcfaeedff9efe1f9f0e4f9f1e6f9f2e9f8f3ecf8f4eef8f5f1f7f6f3f7f7f6f6f6f7f5f5f6f4f4f6f3f3f5f2f2f5f0f1f4eff0f4eeeef3ededf3ebecf3eaebf2e9eaf2e8e9f1e7e8f1e5e7f0e4e5f0e3e4efe2e3efe1e2eedfe1eedee0eddddfeddcddecdadcecd9dbebd8daebd7d8ead5d6e9d4d4e8d2d3e7d1d1e6cfcfe5cecde4cccbe3cbc9e2c9c8e1c8c6e0c6c4dfc5c2dec3c0ddc2bedcc0bddbbfbbdabdb9d9bcb7d8bab5d7b9b3d6b7b1d5b6b0d4b4aed3b3acd2b1aad1afa8d0ada6ceaba3cda9a1cba79fcaa59dc8a39bc7a198c59f96c49d94c29b92c19990bf988dbe968bbc9489bb9287b99085b88e82b68c80b58a7eb3887cb2867ab08475af8275ad8073ac7e70ab7d6da97b6aa87967a67764a57661a4745ea2725ba170589f6f559e6d529c6b4f9b6a4c9a684998664697644395634094613d935f3a915d37905c348e5a318d582e8c572b8a5528895326875225845023824f22804d207d4c1f7b4a1d78491c76471a7445187144176f42156c41146a3f12683e11653c0f633b0e61390c5e380b5c3609593508573306553205523003502f024d2d004b',
  RdGy: '67001f6a011f6d02207003207304217605217906227c07227f0823810823840924870a248a0b258d0c25900d26930e26960f279910279c11279f1228a21328a51429a81529ab162aae172ab1182bb3192cb41c2db61f2eb72230b82531ba2832bb2a34bd2d35be3036bf3338c13639c2383ac43b3cc53e3dc6413ec84440c94741cb4942cc4c44ce4f45cf5246d05548d25849d35a4ad55d4cd6604dd7634fd86551da6853db6b55dc6e57dd7059de735cdf765ee17860e27b62e37e64e48066e58368e6866ae8896ce98b6eea8e70eb9172ec9374ee9677ef9979f09c7bf19e7df2a17ff3a481f4a683f5a886f5aa89f5ac8bf6af8ef6b191f6b394f7b596f7b799f7b99cf8bb9ef8bda1f8bfa4f9c2a7f9c4a9f9c6acfac8affacab1fbccb4fbceb7fbd0b9fcd3bcfcd5bffcd7c2fdd9c4fddbc7fddcc9fddecbfddfcefde1d0fde2d2fde3d4fee5d6fee6d9fee8dbfee9ddfeebdffeece1feede4feefe6fef0e8fef2eafef3ecfef4effef6f1fff7f3fff9f5fffaf7fffbfafffdfcfffefefefefefdfdfdfcfcfcfbfbfbfafafaf8f8f8f7f7f7f6f6f6f5f5f5f3f3f3f2f2f2f1f1f1f0f0f0efefefedededecececebebebeaeaeae9e9e9e7e7e7e6e6e6e5e5e5e4e4e4e2e2e2e1e1e1e0e0e0dfdfdfdddddddcdcdcdadadad9d9d9d7d7d7d6d6d6d4d4d4d3d3d3d1d1d1d0d0d0cecececdcdcdcbcbcbcacacac8c8c8c7c7c7c5c5c5c4c4c4c2c2c2c1c1c1bfbfbfbebebebcbcbcbbbbbbb9b9b9b7b7b7b5b5b5b3b3b3b1b1b1afafafadadadabababa9a9a9a7a7a7a5a5a5a3a3a3a1a1a19f9f9f9d9d9d9b9b9b9999999797979595959393939191918f8f8f8d8d8d8b8b8b8989898787878585858282828080807e7e7e7c7c7c7979797777777575757373737070706e6e6e6c6c6c6969696767676565656363636060605e5e5e5c5c5c5a5a5a5757575555555353535050504e4e4e4c4c4c4a4a4a4848484646464444444242424040403e3e3e3c3c3c3a3a3a3838383636363434343232323030302e2e2e2c2c2c2a2a2a2828282626262424242222222020201e1e1e1c1c1c1a1a1a',
  RdBu: '67001f6a011f6d02207003207304217605217906227c07227f0823810823840924870a248a0b258d0c25900d26930e26960f279910279c11279f1228a21328a51429a81529ab162aae172ab1182bb3192cb41c2db61f2eb72230b82531ba2832bb2a34bd2d35be3036bf3338c13639c2383ac43b3cc53e3dc6413ec84440c94741cb4942cc4c44ce4f45cf5246d05548d25849d35a4ad55d4cd6604dd7634fd86551da6853db6b55dc6e57dd7059de735cdf765ee17860e27b62e37e64e48066e58368e6866ae8896ce98b6eea8e70eb9172ec9374ee9677ef9979f09c7bf19e7df2a17ff3a481f4a683f5a886f5aa89f5ac8bf6af8ef6b191f6b394f7b596f7b799f7b99cf8bb9ef8bda1f8bfa4f9c2a7f9c4a9f9c6acfac8affacab1fbccb4fbceb7fbd0b9fcd3bcfcd5bffcd7c2fdd9c4fddbc7fddcc9fdddcbfcdecdfcdfcffce0d0fce2d2fbe3d4fbe4d6fbe5d8fbe6dafae7dcfae8defae9dffaeae1f9ebe3f9ede5f9eee7f9efe9f9f0ebf8f1edf8f2eff8f3f0f8f4f2f7f5f4f7f6f6f6f7f7f5f6f7f3f5f6f2f5f6f0f4f6eff3f5edf2f5ecf2f5eaf1f5e9f0f4e7f0f4e6eff4e4eef4e3edf3e1edf3e0ecf3deebf2ddebf2dbeaf2dae9f2d8e9f1d7e8f1d5e7f1d4e6f1d2e6f0d1e5f0cfe4efcce2efcae1eec7e0edc5dfecc2ddecc0dcebbddbeabbdaeab8d8e9b6d7e8b3d6e8b1d5e7aed3e6acd2e5a9d1e5a7d0e4a5cee3a2cde3a0cce29dcbe19bc9e098c8e096c7df93c6de90c4dd8dc2dc8ac0db87beda84bcd981bad87eb8d77bb6d678b4d575b2d471b0d36eaed26bacd168abd065a9cf62a7ce5fa5cd5ca3cb59a1ca569fc9529dc84f9bc74c99c64997c54695c44393c34291c2408fc13f8ec03e8cbf3c8abe3b88be3a87bd3885bc3783bb3681ba3480b9337eb8327cb7307ab62f79b52e77b52c75b42b73b32a71b22870b1276eb0266caf246aae2369ad2267ac2065ab1f63a81e61a51d5fa21c5c9f1b5a9c1a589919569618549317529015508d144e8a134c8712498411478110457e0f437b0e41790d3f760c3d730a3b7009386d08366a073467063264053061',
  RdYlBu: 'a50026a70226a90426ab0626ad0826af0926b10b26b30d26b50f26b71126b91326bb1526bd1726be1827c01a27c21c27c41e27c62027c82227ca2427cc2627ce2827d02927d22b27d42d27d62f27d83128d93429da362adb382bdc3b2cdd3d2dde402ee0422fe14430e24731e34933e44c34e54e35e65036e75337e95538ea5739eb5a3aec5c3bed5f3cee613eef633ff16640f26841f36b42f46d43f47044f57245f57547f57748f67a49f67c4af67f4bf7814cf7844ef8864ff88950f88c51f98e52f99153f99355fa9656fa9857fa9b58fb9d59fba05bfba35cfca55dfca85efcaa5ffdad60fdaf62fdb164fdb366fdb567fdb769fdb96bfdbb6dfdbd6ffdbf71fdc173fdc374fdc576fdc778fec87afeca7cfecc7efece7ffed081fed283fed485fed687fed889feda8afedc8cfede8efee090fee192fee294fee496fee597fee699fee79bfee99dfeea9ffeeba1feeca2feeda4feefa6fff0a8fff1aafff2acfff3adfff5affff6b1fff7b3fff8b5fffab7fffbb9fffcbafffdbcfffebefeffc0fdfec2fcfec5fbfdc7fafdc9f8fccbf7fccef6fbd0f5fbd2f3fbd4f2fad6f1fad9f0f9dbeff9ddedf8dfecf8e2ebf7e4eaf7e6e9f6e8e7f6ebe6f5ede5f5efe4f4f1e2f4f4e1f3f6e0f3f8def2f7dcf1f7daf0f6d8eff6d6eef5d4edf4d1ecf4cfebf3cdeaf3cbe9f2c9e8f2c7e7f1c5e6f0c3e5f0c1e4efbfe3efbde2eebbe1edb9e0edb6dfecb4deecb2ddebb0dceaaedbeaacdae9aad8e9a8d6e8a6d5e7a3d3e6a1d1e59fd0e49dcee39bcce299cae197c9e094c7df92c5de90c3dd8ec2dc8cc0db8abeda87bdd985bbd983b9d881b7d77fb6d67db4d57ab2d478b0d376afd274add172abd070a9cf6ea6ce6da4cc6ba2cb69a0ca679ec9659bc86399c76297c66095c45e93c35c90c25a8ec1588cc0578abf5588be5385bd5183bb4f81ba4d7fb94b7db84a7ab74878b64676b54574b34471b2436fb1426cb0416aaf4167ad4065ac3f62ab3e60aa3e5ea83d5ba73c59a63b56a53a54a43a51a2394fa1384ca0374a9f36479e36459c35429b34409a333d99333b97323896313695',
  RdYlGn: 'a50026a70226a90426ab0626ad0826af0926b10b26b30d26b50f26b71126b91326bb1526bd1726be1827c01a27c21c27c41e27c62027c82227ca2427cc2627ce2827d02927d22b27d42d27d62f27d83128d93429da362adb382bdc3b2cdd3d2dde402ee0422fe14430e24731e34933e44c34e54e35e65036e75337e95538ea5739eb5a3aec5c3bed5f3cee613eef633ff16640f26841f36b42f46d43f47044f57245f57547f57748f67a49f67c4af67f4bf7814cf7844ef8864ff88950f88c51f98e52f99153f99355fa9656fa9857fa9b58fb9d59fba05bfba35cfca55dfca85efcaa5ffdad60fdaf62fdb163fdb365fdb567fdb768fdb96afdbb6cfdbd6dfdbf6ffdc171fdc372fdc574fdc776fec877feca79fecc7bfece7cfed07efed27ffed481fed683fed884feda86fedc88fede89fee08bfee18dfee28ffee491fee593fee695fee797fee999feea9bfeeb9dfeec9ffeeda1feefa3fff0a6fff1a8fff2aafff3acfff5aefff6b0fff7b2fff8b4fffab6fffbb8fffcbafffdbcfffebefeffbefdfebcfbfdbafafdb8f8fcb6f7fcb4f5fbb2f4fab0f2faaef1f9aceff8aaeef8a8ecf7a6ebf7a3e9f6a1e8f59fe6f59de5f49be3f399e2f397e0f295dff293ddf191dcf08fdaf08dd9ef8bd7ee8ad5ed88d3ec87d1ec86cfeb85cdea83cbe982c9e881c7e77fc5e67ec3e67dc1e57bbfe47abde379bbe278b9e176b7e075b5df74b3df72b1de71afdd70addc6fabdb6da9da6ca7d96ba5d86aa2d76aa0d6699dd5699bd46998d36896d26893d16891d0688ecf678ccd6789cc6787cb6784ca6682c9667fc8667dc7657ac66578c56575c46573c26470c1646ec0646bbf6469be6366bd6363bc6260ba625db9615ab76057b65f54b45f51b35e4eb15d4bb05c48ae5c45ad5b42ac5a3faa593ca95939a75836a65733a45630a3562da1552aa054279f53249d53219c521e9a511b995019975018954f17934e16914d15904c148e4b138c4a128a491188481086470f84460e82450d80440c7f430b7d420a7b4109794008773f07753e06733d05713c04703b036e3a026c39016a38006837',
  coolwarm: '3b4cc03c4ec23d50c33e51c53f53c64055c84257c94358cb445acc455cce465ecf485fd14961d24a63d34b64d54c66d64e68d84f69d9506bda516ddb536edd5470de5572df5673e05875e15977e35a78e45b7ae55d7ce65e7de75f7fe86180e96282ea6384eb6485ec6687ed6788ee688aef6a8bef6b8df06c8ff16e90f26f92f37093f37295f47396f57597f67699f6779af7799cf87a9df87b9ff97da0f97ea1fa80a3fa81a4fb82a6fb84a7fc85a8fc86a9fc88abfd89acfd8badfd8caffe8db0fe8fb1fe90b2fe92b4fe93b5fe94b6ff96b7ff97b8ff98b9ff9abbff9bbcff9dbdff9ebeff9fbfffa1c0ffa2c1ffa3c2fea5c3fea6c4fea7c5fea9c6fdaac7fdabc8fdadc9fdaec9fcafcafcb1cbfcb2ccfbb3cdfbb5cdfab6cefab7cff9b9d0f9bad0f8bbd1f8bcd2f7bed2f6bfd3f6c0d4f5c1d4f4c3d5f4c4d5f3c5d6f2c6d6f1c7d7f0c9d7f0cad8efcbd8eeccd9edcdd9eccedaebcfdaead1dae9d2dbe8d3dbe7d4dbe6d5dbe5d6dce4d7dce3d8dce2d9dce1dadce0dbdcdedcdddddddcdcdedcdbdfdbd9e0dbd8e1dad6e2dad5e3d9d3e4d9d2e5d8d1e6d7cfe7d7cee8d6cce9d5cbead5c9ead4c8ebd3c6ecd3c5edd2c3edd1c2eed0c0efcfbfefcebdf0cdbbf1cdbaf1ccb8f2cbb7f2cab5f2c9b4f3c8b2f3c7b1f4c6aff4c5adf5c4acf5c2aaf5c1a9f5c0a7f6bfa6f6bea4f6bda2f7bca1f7ba9ff7b99ef7b89cf7b79bf7b599f7b497f7b396f7b194f7b093f7af91f7ad90f7ac8ef7aa8cf7a98bf7a889f7a688f6a586f6a385f6a283f5a081f59f80f59d7ef59c7df49a7bf4987af39778f39577f39475f29274f29072f18f71f18d6ff08b6ef08a6cef886bee8669ee8468ed8366ec8165ec7f63eb7d62ea7b60e97a5fe9785de8765ce7745be67259e57058e46e56e36c55e36b54e26952e16751e0654fdf634ede614ddd5f4bdc5d4ada5a49d95847d85646d75445d65244d55042d44e41d24b40d1493fd0473dcf453ccd423bcc403acb3e38ca3b37c83836c73635c53334c43032c32e31c12b30c0282fbe242ebd1f2dbb1b2cba162bb8122ab70d28b50927b40426',
  seismic: '00004c00004f00005200005500005800005a00005d00006000006300006600006800006b00006e00007100007400007600007900007c00007f00008200008400008700008a00008d00009000009200009500009800009b00009e0000a00000a30000a60000a90000ac0000ae0000b10000b40000b70000ba0000bc0000bf0000c20000c50000c80000ca0000cd0000d00000d30000d60000d80000db0000de0000e10000e40000e60000e90000ec0000ef0000f20000f40000f70000fa0000fd0101ff0505ff0909ff0d0dff1111ff1515ff1919ff1d1dff2121ff2525ff2929ff2d2dff3131ff3535ff3939ff3d3dff4141ff4545ff4949ff4d4dff5151ff5555ff5959ff5d5dff6161ff6565ff6969ff6d6dff7171ff7575ff7979ff7d7dff8181ff8585ff8989ff8d8dff9191ff9595ff9999ff9d9dffa1a1ffa5a5ffa9a9ffadadffb1b1ffb5b5ffb9b9ffbdbdffc1c1ffc5c5ffc9c9ffcdcdffd1d1ffd5d5ffd9d9ffddddffe1e1ffe5e5ffe9e9ffededfff1f1fff5f5fff9f9fffdfdfffffdfdfff9f9fff5f5fff1f1ffededffe9e9ffe5e5ffe1e1ffddddffd9d9ffd5d5ffd1d1ffcdcdffc9c9ffc5c5ffc1c1ffbdbdffb9b9ffb5b5ffb1b1ffadadffa9a9ffa5a5ffa1a1ff9d9dff9999ff9595ff9191ff8d8dff8989ff8585ff8181ff7d7dff7979ff7575ff7171ff6d6dff6969ff6565ff6161ff5d5dff5959ff5555ff5151ff4d4dff4949ff4545ff4141ff3d3dff3939ff3535ff3131ff2d2dff2929ff2525ff2121ff1d1dff1919ff1515ff1111ff0d0dff0909ff0505ff0101fe0000fc0000fa0000f80000f60000f40000f20000f00000ee0000ec0000ea0000e80000e60000e30000e20000e00000de0000dc0000da0000d80000d60000d30000d20000d00000ce0000cc0000ca0000c80000c60000c30000c20000c00000be0000bc0000ba0000b80000b60000b30000b20000b00000ae0000ac0000aa0000a80000a60000a30000a20000a000009e00009c00009a00009800009600009300009200009000008e00008c00008a0000880000860000840000820000800000',
}
function hexBaseLUT(hex) {
  const R = [], G = [], B = []
  for (let i = 0; i < 256; i++) {
    const o = i * 6
    R.push(parseInt(hex.substr(o, 2), 16))
    G.push(parseInt(hex.substr(o + 2, 2), 16))
    B.push(parseInt(hex.substr(o + 4, 2), 16))
  }
  return { R, G, B }
}
// Linear-interpolated sample at a fractional index into a 256-entry base LUT.
function sampleBaseLUT(lut, idx) {
  const i0 = Math.max(0, Math.min(255, Math.floor(idx)))
  const i1 = Math.min(255, i0 + 1)
  const f = idx - i0
  return [
    lut.R[i0] + f * (lut.R[i1] - lut.R[i0]),
    lut.G[i0] + f * (lut.G[i1] - lut.G[i0]),
    lut.B[i0] + f * (lut.B[i1] - lut.B[i0]),
  ]
}
// color0/color1 endpoints for our own 3 hand-rolled diverging colormaps —
// every other diverging name comes from MPL_DIVERGING_HEX instead. Lowercased
// for the matplotlib ones (vs. e.g. "RdBu") to match this app's own naming
// convention and sort predictably alongside bwr/gwr/cwr and NiiVue's own
// built-ins (all lowercase).
const CUSTOM_DIVERGING_RGB = {
  bwr: [0,   0, 255, 255,   0,   0],  // blue-white-red
  gwr: [0, 180,   0, 255,   0,   0],  // green-white-red
  cwr: [0, 200, 200, 255,   0,   0],  // cyan-white-red
}
const DIVERGING_LUTS = {}
for (const [name, rgb] of Object.entries(CUSTOM_DIVERGING_RGB)) DIVERGING_LUTS[name] = twoColorBaseLUT(...rgb)
for (const [name, hex] of Object.entries(MPL_DIVERGING_HEX)) DIVERGING_LUTS[name.toLowerCase()] = hexBaseLUT(hex)
const DIVERGING_NAMES = Object.keys(DIVERGING_LUTS).sort()

// lo/hi are the data range this LUT gets mapped across (cal_min/cal_max);
// thresh is a half-width "dead zone" around zero held flat white — e.g.
// lo=-7, hi=7, thresh=2.29 squeezes the base LUT's whole lower-half
// trajectory into -7..-2.29, holds flat white from -2.29 to +2.29, then
// squeezes its upper-half trajectory into +2.29..+7. thresh=0 (the default)
// collapses the dead zone to nothing, exactly reproducing the base LUT
// (remapped only for an asymmetric [lo, hi]) — this is also what every
// pre-threshold/pre-matplotlib version of this function always produced.
function buildDivergingCmap(baseLUT, lo = -1, hi = 1, thresh = 0) {
  const span = hi - lo || 1e-9
  let fracNeg = Math.min(1, Math.max(0, (-thresh - lo) / span))
  let fracPos = Math.min(1, Math.max(0, (thresh - lo) / span))
  if (fracPos < fracNeg) fracPos = fracNeg   // thresh wider than [lo, hi]: no ramp, all white
  const center = (baseLUT.R.length - 1) / 2
  const R = [], G = [], B = [], A = []
  for (let i = 0; i < 256; i++) {
    const t = i / 255
    let r, g, b
    if (t <= fracNeg) {
      const s = fracNeg > 0 ? t / fracNeg : 0
      ;[r, g, b] = sampleBaseLUT(baseLUT, s * center)
    } else if (t >= fracPos) {
      const s = fracPos < 1 ? (t - fracPos) / (1 - fracPos) : 1
      ;[r, g, b] = sampleBaseLUT(baseLUT, center + s * (baseLUT.R.length - 1 - center))
    } else {
      r = 255; g = 255; b = 255
    }
    R.push(Math.round(r)); G.push(Math.round(g)); B.push(Math.round(b))
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
const CUSTOM_CMAPS = {}
for (const name of DIVERGING_NAMES) CUSTOM_CMAPS[name] = buildDivergingCmap(DIVERGING_LUTS[name])
CUSTOM_CMAPS.flat_lh = buildFlatCmap(...((LH_SURF?.rgba255 ?? [102, 179, 255]).slice(0, 3)))
CUSTOM_CMAPS.flat_rh = buildFlatCmap(...((RH_SURF?.rgba255 ?? [255, 133, 77]).slice(0, 3)))
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

// Rebuilds one of the diverging colormaps for the given data range +
// threshold and re-registers it on just the given NiiVue instances — each
// instance keeps its own colormap registry, so the LH/RH "Data" panels and
// the Asym panel can show the same-named colormap shaped by independent
// ranges/thresholds at once. No-op for any other colormap name (sequential
// colormaps like viridis have no zero to center a dead zone on). Re-applies
// 'colormap' on every affected layer afterward so already-rendered meshes
// pick up the new LUT immediately, not just the next time it's selected.
function refreshDivergingCmap(nvList, name, lo, hi, thresh) {
  if (!DIVERGING_LUTS[name]) return
  const lut = buildDivergingCmap(DIVERGING_LUTS[name], lo, hi, thresh)
  for (const nv of nvList) {
    nv.addColormap(name, lut)
    for (const mesh of nv.meshes)
      if (mesh.layers?.length) nv.setMeshLayerProperty(mesh.id, 0, 'colormap', name)
  }
}

// One-sided variant for an UNSIGNED magnitude (the collapse-depth z-score
// mode's "mean |z|"/"mean |LH-RH z|" overlay — see applyCollapsedOverlays):
// data only ever runs lo..hi (lo is usually, but not necessarily, 0 — the
// range is user-editable same as everywhere else), so only the base LUT's
// upper/"positive" half (its center..255 trajectory) is used, white‑out dead
// zone retained. Using the full two-sided buildDivergingCmap here would be
// wrong — it'd paint the lower-half colors at the LOW (not negative)
// extreme of this axis, which doesn't mean anything for a magnitude that's
// never negative.
function buildOneSidedDivergingCmap(baseLUT, lo, hi, thresh = 0) {
  const span = (hi - lo) || 1e-9
  const fracThresh = Math.min(1, Math.max(0, (thresh - lo) / span))
  const center = (baseLUT.R.length - 1) / 2
  const R = [], G = [], B = [], A = []
  for (let i = 0; i < 256; i++) {
    const t = i / 255
    let r, g, b
    if (t <= fracThresh) {
      r = 255; g = 255; b = 255
    } else {
      const s = fracThresh < 1 ? (t - fracThresh) / (1 - fracThresh) : 1
      ;[r, g, b] = sampleBaseLUT(baseLUT, center + s * (baseLUT.R.length - 1 - center))
    }
    R.push(Math.round(r)); G.push(Math.round(g)); B.push(Math.round(b))
    A.push(255)
  }
  return { R, G, B, A }
}

function refreshOneSidedDivergingCmap(nvList, name, lo, hi, thresh) {
  if (!DIVERGING_LUTS[name]) return
  const lut = buildOneSidedDivergingCmap(DIVERGING_LUTS[name], lo, hi, thresh)
  for (const nv of nvList) {
    nv.addColormap(name, lut)
    for (const mesh of nv.meshes)
      if (mesh.layers?.length) nv.setMeshLayerProperty(mesh.id, 0, 'colormap', name)
  }
}

// Colormaps for scalar data, shared by BOTH the surface data overlays (cmapSel)
// and the orthoslice volume (volCmapSel) so the two menus are identical. Built
// from NiiVue's full registered set (so lipari, navia, etc. are all included),
// plus our own diverging colormaps (registered above) — useful on the LH/RH
// (and, via the shared list, the volume) panels for signed data like z-scores,
// not just the asymmetry-index menu (cmapAsymSel), which keeps its own
// separate, asym-only list. Only the CT-specific clinical maps and the
// flat_lh/flat_rh masks (internal-only — flag "no data" vertices, never a
// real user choice) are excluded.
const MASK_CMAP_NAMES = new Set(['flat_lh', 'flat_rh'])
const SURFACE_CMAPS = (nvSlices.colormaps ? nvSlices.colormaps() : ['gray'])
  .filter(n => !/^ct[-_]/i.test(n) && !MASK_CMAP_NAMES.has(n))
  .sort()
// divergingOnly restricts the list to bwr/cwr/gwr — used in z-score mode,
// where every metric shows signed data and a sequential (non-zero-centered)
// colormap like viridis wouldn't make sense.
function fillCmapSelect(sel, selected, divergingOnly = false) {
  const names = divergingOnly ? DIVERGING_NAMES : SURFACE_CMAPS
  sel.innerHTML = names.map(n =>
    `<option value="${n}"${n === selected ? ' selected' : ''}>${n}</option>`).join('')
}
fillCmapSelect(document.getElementById('cmapSel'), currentCmap)

// cmapAsymSel's options are static HTML (it has its own small, asym-only
// list — see the comment above SURFACE_CMAPS), so unlike cmapSel this just
// hides the non-diverging ones instead of rebuilding the list.
function filterAsymCmapOptions(divergingOnly) {
  for (const opt of document.getElementById('cmapAsymSel').options)
    opt.hidden = divergingOnly && !DIVERGING_NAMES.includes(opt.value)
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
  yokeRecordAll()
}

// ── view yoking (wb_view-style) ────────────────────────────────────────────────
// Rotating one of the three surface panels rotates the other two along with
// it — same feature as Connectome Workbench's "Yoking". LH and Asym (which
// renders on LH geometry) share azimuth 1:1; RH is mirrored — its initial
// az=270 vs LH/Asym's az=90 above is itself a 180deg mirror image, since LH
// and RH are mirror images of each other, so a yoked turntable rotation has
// to run in opposite directions on each side to keep showing the same
// anatomical view (both lateral, or both medial) at once, matching
// Workbench's own documented behavior for surface yoking. Elevation (tilt)
// is shared as-is, not mirrored — tilting up/down doesn't swap lateral/
// medial correspondence.
const YOKE_PANELS = [nvLhL, nvRhL, nvAsym]
const YOKE_SIGN = new Map([[nvLhL, 1], [nvAsym, 1], [nvRhL, -1]])
const yokeLastAzEl = new Map()
let yokeEnabled = false
let yokeApplying = false   // guards re-entrancy while this drives the other two panels

function yokeRecordAll() {
  for (const nv of YOKE_PANELS) yokeLastAzEl.set(nv, [nv.scene.renderAzimuth, nv.scene.renderElevation])
}

// Shortest signed distance from `from` to `to` on a 0-360 circle. NiiVue
// normalizes azimuth into [0, 360) on every drag tick (CameraController.
// normalizeAzimuth), so a naive subtraction breaks right at the wrap (e.g.
// 359 -> 1 is really +2, not -358).
function azimuthDelta(to, from) {
  let d = (to - from) % 360
  if (d > 180) d -= 360
  if (d < -180) d += 360
  return d
}

// Hooked onto each panel's onAzimuthElevationChange, which NiiVue fires on
// every drag-rotation tick (and on arrow-key nudges while a panel has
// focus). Always keeps yokeLastAzEl current, even while yoking is off, so
// turning it on mid-session starts from a correct baseline.
function onYokedAzElChange(nv, az, el) {
  if (!yokeEnabled || yokeApplying) { yokeLastAzEl.set(nv, [az, el]); return }
  const [prevAz, prevEl] = yokeLastAzEl.get(nv) ?? [az, el]
  const dAz = azimuthDelta(az, prevAz) * YOKE_SIGN.get(nv)   // canonical (unmirrored) delta
  const dEl = el - prevEl
  if (dAz || dEl) {
    yokeApplying = true
    for (const other of YOKE_PANELS) {
      if (other === nv) continue
      const newAz = ((other.scene.renderAzimuth + dAz * YOKE_SIGN.get(other)) % 360 + 360) % 360
      setCam(other, newAz, other.scene.renderElevation + dEl)
    }
    yokeApplying = false
  }
  yokeRecordAll()
}
for (const nv of YOKE_PANELS) nv.onAzimuthElevationChange = (az, el) => onYokedAzElChange(nv, az, el)

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
// metric labels look like dti/fa; files/URLs use the '/'-free id (dti__fa), see metric_id() in cortical_io.py
const metricId = m => m.replace(/\//g, '__')

function layerDataFor(hemi, metric) {
  const info = metric ? activeMetricInfo(metric) : null
  if (!info) return []
  const suffix = (showZscore && hasZscore(metric)) ? '_zscore' : ''
  return [{ url: `${BASE_URL}/${hemi}_${TEMPLATE}_${metricId(metric)}${suffix}.func.gii${Q}`,
            colormap: currentCmap, colormapInvert: dataInvert,
            opacity: layerOpacity, cal_min: currentClimMin, cal_max: currentClimMax }]
}
function layerAsymFor(metric) {
  const info = metric ? activeMetricInfo(metric) : null
  if (!info) return []
  const suffix = (showZscore && hasZscore(metric)) ? '_zscore' : ''
  return [{ url: `${BASE_URL}/asym_${TEMPLATE}_${metricId(metric)}${suffix}.func.gii${Q}`,
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
// Raw mask-values layer injection, factored out of applyInvalidMask so the
// collapse-depth overlay (applyCollapsedOverlays below) can reuse it with a
// differently-computed mask (NaN in the collapsed array, not NaN at one depth).
function applyMaskLayer(nv, mask, cmapName) {
  const mesh = nv.meshes[0]
  if (!mesh?.layers?.length || !mask) return
  mesh.layers[1] = {
    values: mask, nFrame4D: 1, frame4D: 0,
    colormap: cmapName, colormapNegative: 'winter', useNegativeCmap: false,
    colormapInvert: false, colormapType: 0, colormapLabel: null,
    isTransparentBelowCalMin: true, isAdditiveBlend: false, colorbarVisible: false,
    outlineBorder: 0, opacity: 1, cal_min: 0.5, cal_max: 1,
    cal_minNeg: NaN, cal_maxNeg: NaN, global_min: 0, global_max: 1,
  }
  mesh.updateMesh(nv.gl)
}
function invalidMaskAtDepth(matArray, nd, depth) {
  const nVerts = matArray.length / nd
  const mask = new Float32Array(nVerts)
  for (let vi = 0; vi < nVerts; vi++) mask[vi] = Number.isNaN(matArray[vi * nd + depth]) ? 1 : 0
  return mask
}
function invalidMaskFromArray(arr) {
  const mask = new Float32Array(arr.length)
  for (let i = 0; i < arr.length; i++) mask[i] = Number.isNaN(arr[i]) ? 1 : 0
  return mask
}
const MASK_CMAP_FOR = { lh: 'flat_lh', rh: 'flat_rh', asym: 'flat_lh' }   // nvAsym shares LH geometry/base color
function refreshInvalidMasks(depth) {
  if (!currentMetric || collapseDepth) return   // collapse-depth masks are set by applyCollapsedOverlays instead
  const zscore = showZscore && hasZscore(currentMetric)
  const nd = activeMetricInfo(currentMetric).n_depths
  for (const [hemi, nv] of [['lh', nvLhL], ['rh', nvRhL], ['asym', nvAsym]]) {
    const mat = matCache[`${hemi}_${currentMetric}${zscore ? '_zscore' : ''}`]
    if (mat) applyMaskLayer(nv, invalidMaskAtDepth(mat, nd, depth), MASK_CMAP_FOR[hemi])
  }
}

// ── collapse-depth overlay (mean across depth, per vertex) ───────────────────
// Computed client-side from whichever matrices are already in matCache (the
// signed _zscore ones in z-score mode, the plain raw ones otherwise — both
// already fetched for the depth-profile plots), so no server round-trip is
// needed. Applied via the same raw-layer-injection NiiVue accepts for the
// mask layer (applyMaskLayer above) — bypasses layerDataFor/layerAsymFor's
// URL-based loadMeshes path entirely, since there's no per-depth frame to
// point a URL at.
//
// z-score mode averages |z| (magnitude): opposite-signed deviations at
// different depths would otherwise cancel toward 0 and hide a real
// abnormality. Raw mode averages the plain value — ordinary cortical metrics
// (FA, T1w intensity, ...) have no such cancellation risk, and this is just
// "the average value down the column" — except the raw asym panel, which is
// already a signed (LH-RH)/mean ratio; it's plain-averaged too (consistent
// with "average whatever's currently shown"), so it keeps its own diverging
// colormap/range rather than switching to the data colormap the way the
// unsigned z-score case does (see asymUnsigned below).
function meanPerVertex(matArray, nd, useAbs) {
  const nVerts = matArray.length / nd
  const out = new Float32Array(nVerts)
  for (let vi = 0; vi < nVerts; vi++) {
    let sum = 0, count = 0
    for (let d = 0; d < nd; d++) {
      const v = matArray[vi * nd + d]
      if (!Number.isNaN(v)) { sum += useAbs ? Math.abs(v) : v; count++ }
    }
    out[vi] = count > 0 ? sum / count : NaN
  }
  return out
}
// 98th-percentile cal max (clip range, matches the server's zscore_cal_range
// convention) and the true max (for global_max) of a collapsed array. Only
// used in z-score mode — raw mode reuses the already-computed
// currentClimMin/Max / currentAsymMin/Max instead (see applyCollapsedOverlays).
function collapsedRangeStats(arr, pct = 98) {
  const finite = []
  for (const v of arr) if (Number.isFinite(v)) finite.push(v)
  if (!finite.length) return { calMax: 1, trueMax: 1 }
  finite.sort((a, b) => a - b)
  const idx = Math.min(finite.length - 1, Math.floor((pct / 100) * finite.length))
  return { calMax: finite[idx] || 1, trueMax: finite[finite.length - 1] || 1 }
}
function applyCollapsedDataLayer(nv, values, cmap, invert, calMin, calMax, globalMin, globalMax) {
  const mesh = nv.meshes[0]
  if (!mesh?.layers?.length) return
  mesh.layers[0] = {
    values, nFrame4D: 1, frame4D: 0,
    colormap: cmap, colormapNegative: 'winter', useNegativeCmap: false,
    colormapInvert: invert, colormapType: 0, colormapLabel: null,
    isTransparentBelowCalMin: false, isAdditiveBlend: false, colorbarVisible: true,
    outlineBorder: 0, opacity: layerOpacity, cal_min: calMin, cal_max: calMax,
    cal_minNeg: NaN, cal_maxNeg: NaN, global_min: globalMin, global_max: globalMax,
  }
  mesh.updateMesh(nv.gl)
}
// Last-computed collapsed cal ranges (z-score mode only — see above), used by
// refreshColorbars() to label the sidebar swatches — lh/rh share one range
// (mirrors the per-depth zscore mode's shared currentClimMin/Max), asym gets
// its own (mirrors currentAsymMin/Max).
let collapseClimMax = 1, collapseAsymClimMax = 1
function applyCollapsedOverlays() {
  if (!currentMetric) return
  const zscore = showZscore && hasZscore(currentMetric)
  const nd = activeMetricInfo(currentMetric).n_depths
  const suffix = zscore ? '_zscore' : ''
  const lhMat   = matCache[`lh_${currentMetric}${suffix}`]
  const rhMat   = matCache[`rh_${currentMetric}${suffix}`]
  const asymMat = matCache[`asym_${currentMetric}${suffix}`]
  const lhCollapsed   = lhMat   ? meanPerVertex(lhMat, nd, zscore)   : null
  const rhCollapsed   = rhMat   ? meanPerVertex(rhMat, nd, zscore)   : null
  const asymCollapsed = asymMat ? meanPerVertex(asymMat, nd, zscore) : null

  // The collapsed raw asym ratio is signed, same as the regular (non-collapsed)
  // raw asym panel — keeps its own diverging colormap/range. Only the z-score
  // case (unsigned mean |diff|) switches to the data colormap.
  let dataMin, dataMax, dataGMin, dataGMax, asymCmap, asymInv, asymMin, asymMax, asymGMin, asymGMax
  if (zscore) {
    // collapseClimMax/collapseAsymClimMax are the collapsed data's own
    // stats — kept for the Auto button (see climAuto/asymAuto) to fit the
    // range to what this metric's mean |z| actually looks like, but no
    // longer force-applied: the range is user-editable here exactly like
    // every other mode (Data/Asym min/max/Auto), not auto-overridden.
    const lhStats   = lhCollapsed   ? collapsedRangeStats(lhCollapsed)   : null
    const rhStats   = rhCollapsed   ? collapsedRangeStats(rhCollapsed)   : null
    const asymStats = asymCollapsed ? collapsedRangeStats(asymCollapsed) : null
    collapseClimMax = Math.max(lhStats?.calMax || 0, rhStats?.calMax || 0) || 1
    collapseAsymClimMax = asymStats?.calMax || 1
    dataMin = currentClimMin; dataMax = currentClimMax
    dataGMin = 0; dataGMax = Math.max(lhStats?.trueMax || 0, rhStats?.trueMax || 0) || 1
    asymCmap = currentCmap; asymInv = dataInvert
    asymMin = currentAsymMin; asymMax = currentAsymMax
    asymGMin = 0; asymGMax = asymStats?.trueMax || 1
    // Unsigned magnitude (never negative) — use only the colormap's
    // positive/"hot" half, not the full two-sided diverging shape, or the
    // cool end would wrongly paint the low (not negative) extreme of this
    // axis. Asym uses currentCmap here (see asymCmap above) but its own
    // range/threshold (asymMin/asymMax/currentAsymThresh), independent of
    // the Data panel's.
    refreshOneSidedDivergingCmap([nvLhL, nvRhL], currentCmap, dataMin, dataMax, currentClimThresh)
    refreshOneSidedDivergingCmap([nvAsym], currentCmap, asymMin, asymMax, currentAsymThresh)
  } else {
    dataMin = currentClimMin; dataMax = currentClimMax
    dataGMin = currentClimMin; dataGMax = currentClimMax
    asymCmap = currentCmapAsym; asymInv = asymInvert
    asymMin = currentAsymMin; asymMax = currentAsymMax
    asymGMin = currentAsymMin; asymGMax = currentAsymMax
  }

  if (lhCollapsed) {
    applyCollapsedDataLayer(nvLhL, lhCollapsed, currentCmap, dataInvert, dataMin, dataMax, dataGMin, dataGMax)
    applyMaskLayer(nvLhL, invalidMaskFromArray(lhCollapsed), MASK_CMAP_FOR.lh)
  }
  if (rhCollapsed) {
    applyCollapsedDataLayer(nvRhL, rhCollapsed, currentCmap, dataInvert, dataMin, dataMax, dataGMin, dataGMax)
    applyMaskLayer(nvRhL, invalidMaskFromArray(rhCollapsed), MASK_CMAP_FOR.rh)
  }
  if (asymCollapsed) {
    applyCollapsedDataLayer(nvAsym, asymCollapsed, asymCmap, asymInv, asymMin, asymMax, asymGMin, asymGMax)
    applyMaskLayer(nvAsym, invalidMaskFromArray(asymCollapsed), MASK_CMAP_FOR.asym)
  }
  refreshColorbars()
}

// Effective base tint for each hemisphere — lhSurfColorOverride/
// rhSurfColorOverride if the hidden Alt+Shift+L/R/W feature has set one,
// else the default LH_SURF/RH_SURF.rgba255 (same fallback chain as
// CUSTOM_CMAPS.flat_lh/flat_rh's initial registration above).
function lhSurfRgb() { return lhSurfColorOverride ?? (LH_SURF?.rgba255?.slice(0, 3) ?? [102, 179, 255]) }
function rhSurfRgb() { return rhSurfColorOverride ?? (RH_SURF?.rgba255?.slice(0, 3) ?? [255, 133, 77]) }

async function loadLhPanel(metric) {
  if (!LH_SURF || !lhSurfUrl) return
  console.time('loadLhPanel')
  markerMeshes.delete(nvLhL); neighborMeshes.delete(nvLhL)
  await nvLhL.loadMeshes([{ url: lhSurfUrl, rgba255: new Uint8Array([...lhSurfRgb(), 255]), layers: layerDataFor('lh', metric) }])
  disableTransparentBelowCalMin(nvLhL)
  applyShader(nvLhL, currentShader)
  console.timeEnd('loadLhPanel')
}

async function loadRhPanel(metric) {
  if (!RH_SURF || !rhSurfUrl) return
  console.time('loadRhPanel')
  markerMeshes.delete(nvRhL); neighborMeshes.delete(nvRhL)
  await nvRhL.loadMeshes([{ url: rhSurfUrl, rgba255: new Uint8Array([...rhSurfRgb(), 255]), layers: layerDataFor('rh', metric) }])
  disableTransparentBelowCalMin(nvRhL)
  applyShader(nvRhL, currentShader)
  console.timeEnd('loadRhPanel')
}

async function loadAsymPanel(metric) {
  if (!LH_SURF || !asymSurfUrl) return
  console.time('loadAsymPanel')
  markerMeshes.delete(nvAsym); neighborMeshes.delete(nvAsym)
  await nvAsym.loadMeshes([{ url: asymSurfUrl, rgba255: new Uint8Array([...lhSurfRgb(), 255]), layers: layerAsymFor(metric) }])
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

// ── native white-surface coordinates (cached, for the anatomical crosshair) ───
// Only the subject's own white/pial surfaces have vertex coordinates that
// correspond to the orthoslice volume. inflated/very_inflated are the same
// subject's geometry but artificially expanded for visualization; the
// average_white/average_pial surface types are a DIFFERENT subject's geometry
// entirely (the shared fsaverage_sym template, see
// cortical_resample_fsaverage_sym_to_ico6.sh) despite the name. All surface
// types share the same ico6_sym vertex indexing though, so whenever a click
// lands on a non-safe surface type, the clicked vertex ID is looked up in
// this subject's own white surface instead — fetched lazily (once, promise-
// cached so concurrent callers share one fetch) and never rendered, just used
// for its .pts array.
const SAFE_SURF_TYPES = new Set(['white', 'pial'])
const whitePtsPromise = { lh: null, rh: null }
function ensureWhitePts(hemi) {
  if (whitePtsPromise[hemi]) return whitePtsPromise[hemi]
  const url = SURF_TYPES.white?.[hemi]
  if (!url) return Promise.resolve(null)
  whitePtsPromise[hemi] = niivue.NVMesh.loadFromUrl({ url, gl: nvLhL.gl }).then(m => m.pts)
  return whitePtsPromise[hemi]
}
// World coordinates for vertex `i` on the panel whose surface-type dropdown
// is `surfSelId` — corrected to this subject's white surface if that panel's
// current type isn't in SAFE_SURF_TYPES. `fallbackPts` (the panel's own live,
// possibly-distorted mesh.pts) is used if the white surface hasn't loaded yet
// or isn't available for this subject at all. `corrected` tells the caller
// whether a substitution actually happened, so callers that display the
// coordinates (not just use them internally, like the crosshair) can flag it.
async function anatomicalPts(surfSelId, hemi, fallbackPts, i) {
  const curType = document.getElementById(surfSelId).value
  if (!SAFE_SURF_TYPES.has(curType)) {
    const wpts = await ensureWhitePts(hemi)
    if (wpts) return { pt: [wpts[i * 3], wpts[i * 3 + 1], wpts[i * 3 + 2]], corrected: true }
  }
  return { pt: [fallbackPts[i * 3], fallbackPts[i * 3 + 1], fallbackPts[i * 3 + 2]], corrected: false }
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

async function ensureMatrix(hemi, metric, zscore = false) {
  const suffix = zscore ? '_zscore' : ''
  const key = `${hemi}_${metric}${suffix}`
  if (matCache[key]) return matCache[key]
  const r = await fetch(`${BASE_URL}/${hemi}_${TEMPLATE}_${metricId(metric)}${suffix}_matrix.f32${Q}`)
  matCache[key] = new Float32Array(await r.arrayBuffer())
  return matCache[key]
}

// ── normative (cohort) matrix cache ──────────────────────────────────────────
const normCache = {}

async function ensureNormativeMatrix(kind, metric, stat) {
  const key = `${kind}_${metric}_${stat}`
  if (normCache[key]) return normCache[key]
  const r = await fetch(`${BASE_URL}/normative_${kind}_${metricId(metric)}_${stat}.f32${Q}`)
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
  const r = await fetch(`/normative_ring?metric=${encodeURIComponent(metric)}&kind=${kind}&vertices=${ringSet.join(',')}`)
  if (!r.ok) return null
  return r.json()
}

async function loadMatrices(metric) {
  const tasks = [
    ensureMatrix('lh',   metric),
    ensureMatrix('rh',   metric),
    ensureMatrix('asym', metric),
  ]
  if (hasZscore(metric)) {
    tasks.push(
      ensureMatrix('lh',   metric, true),
      ensureMatrix('rh',   metric, true),
      ensureMatrix('asym', metric, true),
    )
  }
  await Promise.all(tasks)
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
  const v = d.values && d.values[0]
  document.getElementById('pos-mm').textContent  = mm  ? Array.from(mm.slice(0, 3), x => x.toFixed(1)).join(', ') + ' mm' : '—, —, — mm'
  document.getElementById('pos-vox').textContent = vox ? Array.from(vox.slice(0, 3), x => Math.round(x)).join(', ') : '—, —, —'
  document.getElementById('pos-val').textContent = (v && isFinite(v.value)) ? (+v.value).toPrecision(4) : '—'
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
nvSlices.setCrosshairColor(accentRgba())   // match selected-vertex accent
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
  nvSlices.setCrosshairColor(accentRgba())    // re-assert crosshair styling
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
  // In collapse-depth mode the surfaces show one depth-independent value per
  // vertex (see applyCollapsedOverlays) — depth selection still drives the
  // depth-profile plots' reference marker below, but must not touch frame4D
  // or recompute the per-depth invalid mask here.
  if (!collapseDepth) {
    for (const nv of [nvLhL, nvRhL, nvAsym])
      for (const mesh of nv.meshes)
        if (mesh.layers?.length) nv.setMeshLayerProperty(mesh.id, 0, 'frame4D', d)
    refreshInvalidMasks(d)
  }
  broadcastDwiCrosshair()
  updateDepthMarker(mm)
}

document.getElementById('depthSlider').oninput = e => setDepth(+e.target.value)

// Step cortical depth by ±1, clamped to the current metric's range, keeping the
// slider in sync. Used by the +/- keyboard shortcuts.
function stepDepth(delta) {
  if (!currentMetric) return
  const nd = activeMetricInfo(currentMetric).n_depths
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
  // In collapse-depth + z-score mode, the LH/RH surfaces show an unsigned
  // "mean |z|" overlay — no negative side, so its colormap needs the
  // one-sided builder (white up to the cutoff, color only above it) instead
  // of the normal two-sided diverging shape. See applyCollapsedOverlays.
  if (collapsedAsymUnsigned()) {
    refreshOneSidedDivergingCmap([nvLhL, nvRhL], currentCmap, mn, mx, currentClimThresh)
  } else {
    refreshDivergingCmap([nvLhL, nvRhL], currentCmap, mn, mx, currentClimThresh)
  }
  applyDataValueLimits()
  refreshColorbars()
}

// In z-score mode, pin the LH/RH plots' value axis (x) to the (symmetric,
// zero-centered) data CLim — same role as applyAsymValueLimits() for the
// asym plot — instead of setProfiles()'s usual auto-fit-to-data range, which
// would recenter on whatever the current vertex/ring happens to show and
// lose the at-a-glance "0 = no deviation" reading z-scores depend on.
function applyDataValueLimits() {
  if (!chartLH || !chartRH) return
  if (!(showZscore && hasZscore(currentMetric))) return
  for (const c of [chartLH, chartRH]) Plotly.relayout(c, { 'xaxis.range': [currentClimMin, currentClimMax] })
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
  // See setDataCLim's matching branch — the asym surface shows the same
  // kind of unsigned "mean |LH-RH z|" overlay in this mode (using
  // currentCmap, not currentCmapAsym — see applyCollapsedOverlays), so it
  // needs the one-sided colormap too, with its own range/threshold.
  if (collapsedAsymUnsigned()) {
    refreshOneSidedDivergingCmap([nvAsym], currentCmap, mn, mx, currentAsymThresh)
  } else {
    refreshDivergingCmap([nvAsym], currentCmapAsym, mn, mx, currentAsymThresh)
  }
  applyAsymValueLimits()
  refreshColorbars()
}

// True only for the one collapse-depth case where the asym panel is unsigned
// (mean |LH-RH z|) and therefore shares the main data colormap — the raw
// collapse-depth asym value (mean of the signed (LH-RH)/mean ratio) stays
// signed, same as the regular per-depth raw asym panel, and keeps its own
// diverging colormap/range. See applyCollapsedOverlays.
function collapsedAsymUnsigned() {
  return collapseDepth && showZscore && hasZscore(currentMetric)
}

function setDataCmap(cmap, invert) {
  currentCmap = cmap; dataInvert = invert
  for (const nv of [nvLhL, nvRhL])
    for (const mesh of nv.meshes)
      if (mesh.layers?.length) {
        nv.setMeshLayerProperty(mesh.id, 0, 'colormap', cmap)
        nv.setMeshLayerProperty(mesh.id, 0, 'colormapInvert', invert)
      }
  refreshDivergingCmap([nvLhL, nvRhL], cmap, currentClimMin, currentClimMax, currentClimThresh)
  if (collapsedAsymUnsigned()) {
    for (const mesh of nvAsym.meshes)
      if (mesh.layers?.length) {
        nvAsym.setMeshLayerProperty(mesh.id, 0, 'colormap', cmap)
        nvAsym.setMeshLayerProperty(mesh.id, 0, 'colormapInvert', invert)
      }
  }
  refreshColorbars()
}

function setAsymCmap(cmap, invert) {
  currentCmapAsym = cmap; asymInvert = invert
  // No-op on the live mesh while the asym panel is in its unsigned
  // collapse-depth z-score state (the UI control is also disabled then —
  // see updateCollapseCmapControlsEnabled) — still records the chosen
  // values so they take effect immediately once that state ends.
  if (!collapsedAsymUnsigned()) {
    for (const mesh of nvAsym.meshes)
      if (mesh.layers?.length) {
        nvAsym.setMeshLayerProperty(mesh.id, 0, 'colormap', cmap)
        nvAsym.setMeshLayerProperty(mesh.id, 0, 'colormapInvert', invert)
      }
    refreshDivergingCmap([nvAsym], cmap, currentAsymMin, currentAsymMax, currentAsymThresh)
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
// Build CSS gradient stops straight from a {R,G,B,A} LUT (same shape
// buildDivergingCmap returns).
function lutToCss(lut, invert) {
  const n = lut.R.length, STEPS = 16, stops = []
  for (let s = 0; s <= STEPS; s++) {
    let idx = Math.round(s / STEPS * (n - 1))
    if (invert) idx = n - 1 - idx
    stops.push(`rgb(${lut.R[idx]},${lut.G[idx]},${lut.B[idx]}) ${(s / STEPS * 100).toFixed(1)}%`)
  }
  return `linear-gradient(to right, ${stops.join(',')})`
}

// For diverging colormaps, build the LUT fresh from this panel's own
// lo/hi/thresh — the shared per-NiiVue-instance registry (see
// refreshDivergingCmap) can only hold one shape per name at a time, which
// isn't enough when the Data and Asym panels pick the same diverging
// colormap but different ranges/thresholds. Every other (sequential,
// built-in) colormap doesn't have that problem, so those still read
// straight from nvSlices.colormap(), which returns the full 256-entry RGBA
// table with inversion already applied.
function cmapCss(name, invert, lo, hi, thresh, oneSided) {
  if (DIVERGING_LUTS[name] && lo !== undefined && hi !== undefined) {
    const lut = oneSided
      ? buildOneSidedDivergingCmap(DIVERGING_LUTS[name], lo, hi, thresh || 0)
      : buildDivergingCmap(DIVERGING_LUTS[name], lo, hi, thresh || 0)
    return lutToCss(lut, !!invert)
  }
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
  const zscore = showZscore && hasZscore(currentMetric)
  const collapsedUnsigned = collapseDepth && zscore   // see applyCollapsedOverlays
  let dataLabel, asymLabel, dataMin, dataMax, asymCmap, asymInv, asymMin, asymMax, asymThresh
  if (collapsedUnsigned) {
    dataLabel = currentMetric + ' mean |z|'
    asymLabel = `${currentMetric} mean |LH−RH z|`
    dataMin = currentClimMin; dataMax = currentClimMax
    asymCmap = currentCmap; asymInv = dataInvert   // asym panel shows currentCmap here, see collapsedAsymUnsigned()
    asymMin = currentAsymMin; asymMax = currentAsymMax
    asymThresh = currentAsymThresh
  } else if (collapseDepth) {
    dataLabel = currentMetric + ' mean'
    asymLabel = `${currentMetric} mean asymmetry`
    dataMin = currentClimMin; dataMax = currentClimMax
    asymCmap = currentCmapAsym; asymInv = asymInvert
    asymMin = currentAsymMin; asymMax = currentAsymMax
    asymThresh = currentAsymThresh
  } else {
    dataLabel = currentMetric + (zscore ? ' (z-score)' : '')
    asymLabel = zscore ? `${currentMetric} LH−RH z-score` : `${currentMetric} asymmetry`
    dataMin = currentClimMin; dataMax = currentClimMax
    asymCmap = currentCmapAsym; asymInv = asymInvert
    asymMin = currentAsymMin; asymMax = currentAsymMax
    asymThresh = currentAsymThresh
  }
  const pairs = [
    ['lh',   currentCmap, dataInvert, dataMin, dataMax, dataLabel, currentClimThresh],
    ['rh',   currentCmap, dataInvert, dataMin, dataMax, dataLabel, currentClimThresh],
    ['asym', asymCmap,    asymInv,    asymMin, asymMax, asymLabel, asymThresh],
  ]
  for (const [id, cmap, inv, mn, mx, title, thresh] of pairs) {
    const g = document.getElementById(`cbgrad-${id}`)
    const l = document.getElementById(`cblbl-${id}-min`)
    const r = document.getElementById(`cblbl-${id}-max`)
    const t = document.getElementById(`cbtitle-${id}`)
    if (g) g.style.background = cmapCss(cmap, inv, mn, mx, thresh, collapsedUnsigned)
    if (l) l.textContent = fmt(mn)
    if (r) r.textContent = fmt(mx)
    if (t) t.textContent = title || ''
  }
}

// ── CLim input fields initialisation ─────────────────────────────────────────
const climMinEl    = document.getElementById('climMin')
const climMaxEl    = document.getElementById('climMax')
const asymMinEl    = document.getElementById('asymMin')
const asymMaxEl    = document.getElementById('asymMax')
const climThreshEl = document.getElementById('climThresh')
const asymThreshEl = document.getElementById('asymThresh')
const climThreshDefaultTitle = climThreshEl.title
const asymThreshDefaultTitle = asymThreshEl.title

function initClimInputs(info) {
  climMinEl.value = info.cal_min.toFixed(4)
  climMaxEl.value = info.cal_max.toFixed(4)
  asymMinEl.value = info.cal_min_asym.toFixed(4)
  asymMaxEl.value = info.cal_max_asym.toFixed(4)
  currentClimMin = info.cal_min; currentClimMax = info.cal_max
  currentAsymMin = info.cal_min_asym; currentAsymMax = info.cal_max_asym
  refreshDivergingCmap([nvLhL, nvRhL], currentCmap, currentClimMin, currentClimMax, currentClimThresh)
  if (!collapsedAsymUnsigned())
    refreshDivergingCmap([nvAsym], currentCmapAsym, currentAsymMin, currentAsymMax, currentAsymThresh)
  applyDataValueLimits()
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

// ── diverging-colormap threshold ("dead zone" around zero) ───────────────────
// Negative/blank input is treated as 0 (threshold disabled, plain gradient) —
// mirrors how the min/max fields already just ignore non-finite input.
climThreshEl.addEventListener('change', () => {
  const t = parseFloat(climThreshEl.value)
  currentClimThresh = (isFinite(t) && t > 0) ? t : 0
  setDataCLim(currentClimMin, currentClimMax)
})
asymThreshEl.addEventListener('change', () => {
  const t = parseFloat(asymThreshEl.value)
  currentAsymThresh = (isFinite(t) && t > 0) ? t : 0
  setAsymCLim(currentAsymMin, currentAsymMax)
})

document.getElementById('climAuto').addEventListener('click', () => {
  if (!currentMetric) return
  // The collapsed "mean |z|" overlay's own range (collapseClimMax, from the
  // actual collapsed data — see applyCollapsedOverlays) fits it far better
  // than the per-depth z-score stats below: it's unsigned (starts at 0) and
  // on a different scale (a mean across depths is naturally smaller than any
  // single depth's z).
  const [mn, mx] = collapsedAsymUnsigned() ? [0, collapseClimMax] : (() => {
    const info = activeMetricInfo(currentMetric)
    return [info.cal_min, info.cal_max]
  })()
  climMinEl.value = mn.toFixed(4)
  climMaxEl.value = mx.toFixed(4)
  setDataCLim(mn, mx)
})
document.getElementById('asymAuto').addEventListener('click', () => {
  if (!currentMetric) return
  const [mn, mx] = collapsedAsymUnsigned() ? [0, collapseAsymClimMax] : (() => {
    const info = activeMetricInfo(currentMetric)
    return [info.cal_min_asym, info.cal_max_asym]
  })()
  asymMinEl.value = mn.toFixed(4)
  asymMaxEl.value = mx.toFixed(4)
  setAsymCLim(mn, mx)
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

// ── theme-colored logo ────────────────────────────────────────────────────────
// A single logo.svg, recolored per theme rather than swapped for a second
// file: an <img>'s SVG is opaque to page CSS (var(--accent) can't reach
// inside it), so instead this fetches the raw SVG text once, string-replaces
// its one accent color (#f5c842 — used only by the "Cortical Browser" text
// and the two rule lines; the brain icon's grays/colorful dots are untouched)
// with the active theme's --accent, and points the <img> at a blob URL of
// the result. Re-run on every theme change, same as applyChartTheme/
// applyNiivueTheme below.
const LOGO_SOURCE_COLOR = /#f5c842/gi
let logoSvgText = null
let logoObjectUrl = null
async function applyLogoTheme() {
  const img = document.getElementById('appLogo')
  if (!img) return
  if (logoSvgText === null) {
    try {
      logoSvgText = await (await fetch(img.getAttribute('src'))).text()
    } catch (e) {
      console.warn('[logo] fetch failed:', e.message)
      return
    }
  }
  const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#F5C842'
  const blob = new Blob([logoSvgText.replace(LOGO_SOURCE_COLOR, accent)], { type: 'image/svg+xml' })
  if (logoObjectUrl) URL.revokeObjectURL(logoObjectUrl)   // the previous theme's blob is no longer referenced
  logoObjectUrl = URL.createObjectURL(blob)
  img.src = logoObjectUrl
}
applyLogoTheme()

// ── theme selector ────────────────────────────────────────────────────────────
// Only the sidebar chrome (CSS variables) reacts to this — the 3-D/orthoslice/
// Plotly panels keep their fixed dark palette, so no reload or redraw is needed.
{
  const themeSel = document.getElementById('themeSel')
  themeSel.value = document.documentElement.getAttribute('data-theme') || 'dark'
  themeSel.addEventListener('change', () => {
    document.documentElement.setAttribute('data-theme', themeSel.value)
    try { localStorage.setItem('cbTheme', themeSel.value) } catch (e) {}
    applyChartTheme()
    applyNiivueTheme()
    applyLogoTheme()
  })
}

// ── z-score toggle ───────────────────────────────────────────────────────────
// Enabled/disabled per metric (not globally): follows the Metric dropdown,
// auto-unchecking if the newly selected metric has no z-scored tsf files.
function updateZscoreToggleAvailability(metric) {
  const chk   = document.getElementById('zscoreChk')
  const label = document.getElementById('zscoreLabel')
  const available = hasZscore(metric)
  chk.disabled = !available
  label.style.opacity = available ? '' : 0.4
  label.title = available
    ? 'Show per-vertex z-scores against the cohort norm instead of raw values'
    : 'No z-scored TSF files for this metric'
  if (!available && showZscore) {
    showZscore = false
    chk.checked = false
  }
}
updateZscoreToggleAvailability(currentMetric)

// z-score mode shows signed, unitless data for every metric alike, so it
// gets one fixed default range/threshold/colormap instead of each metric's
// own computed cal_min/cal_max — and whatever cmap/limits were active in
// raw mode are saved here and restored exactly on the way back out, rather
// than recomputed, so z-score tweaks never leak into (or get lost from) the
// raw-mode view.
const ZSCORE_DEFAULT_CMAP   = 'cwr'
const ZSCORE_DEFAULT_MIN    = -3
const ZSCORE_DEFAULT_MAX    = 3
const ZSCORE_DEFAULT_THRESH = 2.3
let savedRawState = null

function saveRawState() {
  savedRawState = {
    cmap: currentCmap, cmapAsym: currentCmapAsym,
    climMin: currentClimMin, climMax: currentClimMax, climThresh: currentClimThresh,
    asymMin: currentAsymMin, asymMax: currentAsymMax, asymThresh: currentAsymThresh,
  }
}

function applyZscoreModeDefaults() {
  fillCmapSelect(document.getElementById('cmapSel'), ZSCORE_DEFAULT_CMAP, true)
  filterAsymCmapOptions(true)
  document.getElementById('cmapAsymSel').value = ZSCORE_DEFAULT_CMAP
  setDataCmap(ZSCORE_DEFAULT_CMAP, dataInvert)
  setAsymCmap(ZSCORE_DEFAULT_CMAP, asymInvert)
  currentClimThresh = ZSCORE_DEFAULT_THRESH
  currentAsymThresh = ZSCORE_DEFAULT_THRESH
  climMinEl.value = ZSCORE_DEFAULT_MIN.toFixed(4)
  climMaxEl.value = ZSCORE_DEFAULT_MAX.toFixed(4)
  climThreshEl.value = ZSCORE_DEFAULT_THRESH
  asymMinEl.value = ZSCORE_DEFAULT_MIN.toFixed(4)
  asymMaxEl.value = ZSCORE_DEFAULT_MAX.toFixed(4)
  asymThreshEl.value = ZSCORE_DEFAULT_THRESH
  setDataCLim(ZSCORE_DEFAULT_MIN, ZSCORE_DEFAULT_MAX)
  setAsymCLim(ZSCORE_DEFAULT_MIN, ZSCORE_DEFAULT_MAX)
}

function restoreRawState() {
  const s = savedRawState
  fillCmapSelect(document.getElementById('cmapSel'), s ? s.cmap : currentCmap, false)
  filterAsymCmapOptions(false)
  if (!s) return
  document.getElementById('cmapAsymSel').value = s.cmapAsym
  setDataCmap(s.cmap, dataInvert)
  setAsymCmap(s.cmapAsym, asymInvert)
  currentClimThresh = s.climThresh
  currentAsymThresh = s.asymThresh
  climMinEl.value = s.climMin.toFixed(4)
  climMaxEl.value = s.climMax.toFixed(4)
  climThreshEl.value = s.climThresh
  asymMinEl.value = s.asymMin.toFixed(4)
  asymMaxEl.value = s.asymMax.toFixed(4)
  asymThreshEl.value = s.asymThresh
  setDataCLim(s.climMin, s.climMax)
  setAsymCLim(s.asymMin, s.asymMax)
}

document.getElementById('zscoreChk').addEventListener('change', async function() {
  if (!currentMetric) { this.checked = false; return }
  showZscore = this.checked
  updateCollapseDepthToggleAvailability(currentMetric)
  updateCollapseCmapControlsEnabled()
  if (showZscore) { saveRawState(); applyZscoreModeDefaults() }
  else restoreRawState()

  const info = activeMetricInfo(currentMetric)
  const nd = info.n_depths
  const sl = document.getElementById('depthSlider')
  sl.max = nd - 1
  if (currentDepth > nd - 1) currentDepth = nd - 1
  sl.value = currentDepth

  await Promise.all([loadAllSurfaces(currentMetric), loadMatrices(currentMetric)])
  if (collapseDepth) applyCollapsedOverlays()
  setDepth(currentDepth)
  if (currentVertex !== null) await selectVertex(currentVertex, nvLhL)
})

// ── collapse-depth toggle ────────────────────────────────────────────────────
// Works for any metric, z-scored or not (see meanPerVertex) — the only time
// it's disabled is when there's no metric at all to collapse.
function updateCollapseDepthToggleAvailability(metric) {
  const chk   = document.getElementById('collapseDepthChk')
  const label = document.getElementById('collapseDepthLabel')
  const available = canCollapseDepth(metric)
  chk.disabled = !available
  label.style.opacity = available ? '' : 0.4
  label.title = available
    ? 'Show the mean value across all depths per vertex instead of one depth-slice (depth-profile plots stay depth-resolved)'
    : 'No metric selected'
  if (!available && collapseDepth) {
    collapseDepth = false
    chk.checked = false
  }
}
// collapsedAsymUnsigned() (despite its name) is the one mode where BOTH
// panels switch to an unsigned "mean |z|"/"mean |LH-RH z|" overlay (see
// applyCollapsedOverlays) and the asym surface follows the main data
// colormap instead of its own — cmapAsymSel/cmapAsymInv are disabled then
// so picking an asym colormap that silently has no effect isn't confusing.
// Min/max/± all stay enabled, same as every other mode: the range is
// user-editable here too (collapseClimMax/collapseAsymClimMax are only a
// sensible Auto-button target, not an override — see applyCollapsedOverlays
// and climAuto/asymAuto), and ± is the one-sided colormap's significance
// cutoff (white below it, color only above — see
// refreshOneSidedDivergingCmap), now independent per panel same as the
// range is.
//
// This function (despite its name) also gates the white-cutoff (±) fields
// on z-score mode generally, not just this collapse-specific case: outside
// z-score mode there's no meaningful "zero deviation" to draw a
// significance cutoff against, so both stay grayed out whenever Z is off.
function updateCollapseCmapControlsEnabled() {
  const unsigned = collapsedAsymUnsigned()
  const sel = document.getElementById('cmapAsymSel')
  const inv = document.getElementById('cmapAsymInv')
  sel.disabled = unsigned
  inv.disabled = unsigned
  sel.style.opacity = unsigned ? 0.4 : ''
  inv.parentElement.style.opacity = unsigned ? 0.4 : ''
  sel.title = unsigned
    ? 'Not used in collapse-depth z-score mode — the collapsed asym surface follows the main data colormap instead'
    : 'Colormap for the asymmetry index'

  for (const el of [climThreshEl, asymThreshEl]) {
    el.disabled = !showZscore
    el.parentElement.style.opacity = showZscore ? '' : 0.4
  }
  climThreshEl.title = !showZscore
    ? 'Only used in z-score mode (the Z checkbox)'
    : unsigned
      ? 'Significance cutoff for the collapsed mean |z| colormap — white below it, color above (one-sided: no negative side to an unsigned magnitude)'
      : climThreshDefaultTitle
  asymThreshEl.title = !showZscore
    ? 'Only used in z-score mode (the Z checkbox)'
    : unsigned
      ? 'Significance cutoff for the collapsed mean |LH-RH z| colormap — white below it, color above (one-sided: no negative side to an unsigned magnitude)'
      : asymThreshDefaultTitle
}
updateCollapseDepthToggleAvailability(currentMetric)
updateCollapseCmapControlsEnabled()

document.getElementById('collapseDepthChk').addEventListener('change', async function() {
  if (!currentMetric) { this.checked = false; return }
  collapseDepth = this.checked
  updateCollapseCmapControlsEnabled()
  await Promise.all([loadAllSurfaces(currentMetric), loadMatrices(currentMetric)])
  if (collapseDepth) applyCollapsedOverlays()
  setDepth(currentDepth)
  if (currentVertex !== null) await selectVertex(currentVertex, nvLhL)
})

// ── metric selector ───────────────────────────────────────────────────────────
document.getElementById('metricSel').addEventListener('change', async e => {
  if (e.target.value === '__other__') {
    // "other…" — a one-off custom overlay (see its own section below), not a
    // real metric switch: revert the dropdown and hand off to its own file
    // picker instead of running any of the logic below.
    e.target.value = currentMetric ?? ''
    document.getElementById('metricOtherFile').click()
    return
  }
  currentMetric = e.target.value
  const wasZscore = showZscore
  updateZscoreToggleAvailability(currentMetric)   // may force showZscore -> false
  updateCollapseDepthToggleAvailability(currentMetric)
  updateCollapseCmapControlsEnabled()
  // Z-score mode uses one fixed default (see applyZscoreModeDefaults) instead
  // of each metric's own computed cal_min/cal_max, so switching metrics
  // re-applies it rather than reading the new metric's stats; falling out of
  // z-score mode here (the new metric has no z-scored data) restores the
  // saved raw-mode state exactly like unchecking the checkbox does.
  if (wasZscore && !showZscore) restoreRawState()
  else if (showZscore) applyZscoreModeDefaults()
  else initClimInputs(activeMetricInfo(currentMetric))

  const info = activeMetricInfo(currentMetric)
  const nd = info.n_depths
  const sl = document.getElementById('depthSlider')
  sl.max = nd - 1
  currentDepth = Math.floor((nd - 1) / 2)
  sl.value = currentDepth

  await Promise.all([loadAllSurfaces(currentMetric), loadMatrices(currentMetric)])
  if (collapseDepth) applyCollapsedOverlays()
  setDepth(currentDepth)
  if (currentVertex !== null) {
    // Keep the selected vertex; re-select to redraw its markers and replot the
    // three depth profiles against the newly-loaded metric.
    await selectVertex(currentVertex, nvLhL)
  } else {
    document.getElementById('vtx-display-lh').textContent = '—, —, — mm'
    document.getElementById('vtx-display-rh').textContent = '—, —, — mm'
    document.getElementById('pos-mm').textContent  = '—, —, — mm'
    document.getElementById('pos-vox').textContent = '—, —, —'
    document.getElementById('pos-val').textContent = '—'
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
// Custom-color registry for the hidden Alt+Shift+V/N recolor feature (see
// promptVertexMarkerColor/promptNeighborMarkerColor below): a flat (single-
// color) colormap, same mechanism as flat_lh/flat_rh's "no data" tint —
// registered fresh on every nv instance whenever the override color
// changes, under a fixed name each marker/neighbor JSON can reference.
const MARKER_COLOR_CMAP   = 'vertex_marker_custom'
const NEIGHBOR_COLOR_CMAP = 'vertex_neighbor_custom'
function registerMarkerColorCmap(name, rgb) {
  const cmap = buildFlatCmap(rgb[0], rgb[1], rgb[2])
  for (const nv of [nvLhL, nvRhL, nvAsym]) {
    try { nv.addColormap(name, cmap) } catch (e) {}
  }
}

function markerConnectomeJSON(x, y, z, size) {
  const cmap = vertexMarkerColorOverride ? MARKER_COLOR_CMAP : 'warm'
  return {
    name: 'vertex-marker',
    nodeColormap: cmap, nodeColormapNegative: cmap,
    nodeMinColor: 0, nodeMaxColor: 1, nodeScale: 1,
    edgeColormap: cmap, edgeColormapNegative: cmap,
    edgeMin: 0, edgeMax: 1, edgeScale: 1,
    showLegend: false,   // suppress the floating "vertex" text label over the sphere
    nodes: { names: ['vertex'], X: [x], Y: [y], Z: [z], Color: [1], Size: [size] },
    edges: []
  }
}

function placeMarker(nvInst, x, y, z) {
  const surf = nvInst.meshes[0]   // the loaded brain surface, always added before any marker
  const radius = (surf?.pts ? meshBounds(surf.pts).radius * 0.015 : 2) * vertexSphereScale

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
  const cmap = neighborMarkerColorOverride ? NEIGHBOR_COLOR_CMAP : 'gray'
  return {
    name: 'vertex-neighbors',
    nodeColormap: cmap, nodeColormapNegative: cmap,
    nodeMinColor: 0, nodeMaxColor: 1, nodeScale: 1,
    edgeColormap: cmap, edgeColormapNegative: cmap,
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

// (Re)places the selected-vertex + neighbor-ring marker spheres for the
// current selection (currentVertex/selectedVertices) at the current
// vertexSphereScale — shared by selectVertex() (a fresh selection) and the
// '>'/'<' size shortcuts (same selection, just resized). No-op if nothing
// is selected.
function placeVertexMarkers() {
  if (currentVertex === null) return
  const vertIdx = currentVertex
  const neighborIdx = selectedVertices.filter(v => v !== vertIdx)
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
}

// Drops any existing marker/neighbor meshes so the next placeVertexMarkers()
// rebuilds them from scratch — needed because placeMarker()/syncNeighborMarkers()
// otherwise just update an existing connectome's node position/size in place,
// without re-reading nodeColormap from a fresh markerConnectomeJSON()/
// neighborConnectomeJSON() call. Used when the marker color changes (see
// promptVertexMarkerColor/promptNeighborMarkerColor below) — removeMesh()+
// recreate is also what syncNeighborMarkers() already does when a ring set
// becomes empty, and simpler than reaching into NiiVue's connectome
// internals to patch an existing mesh's colormap directly.
function rebuildVertexMarkers() {
  for (const nv of [nvLhL, nvRhL, nvAsym]) {
    const marker = markerMeshes.get(nv)
    if (marker) { nv.removeMesh(marker); markerMeshes.delete(nv) }
    const nbr = neighborMeshes.get(nv)
    if (nbr) { nv.removeMesh(nbr); neighborMeshes.delete(nv) }
  }
  placeVertexMarkers()
}

// Parses "R,G,B" / "R G B" (0-255 each) or "#RRGGBB" / "RRGGBB" hex into an
// [r,g,b] array, clamped to 0-255; returns null if the input doesn't parse.
function parseRgbInput(str) {
  str = str.trim()
  if (!str) return null
  const hex = str.match(/^#?([0-9a-f]{6})$/i)
  if (hex) {
    const n = parseInt(hex[1], 16)
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
  }
  const parts = str.split(/[\s,/]+/).map(Number)
  if (parts.length === 3 && parts.every(Number.isFinite))
    return parts.map(v => Math.max(0, Math.min(255, Math.round(v))))
  return null
}

// Hidden feature (shortcut: Alt+Shift+V): prompts for an RGB (or #hex) color
// and recolors the selected-vertex marker sphere — hardcoded 'warm' (yellow)
// otherwise. Leave the field blank to reset to the default.
function promptVertexMarkerColor() {
  const current = vertexMarkerColorOverride ? vertexMarkerColorOverride.join(',') : ''
  const input = prompt('Selected-vertex marker color — "R,G,B" (0-255) or "#RRGGBB".\nLeave blank to reset to the default (yellow).', current)
  if (input === null) return   // cancelled
  if (input.trim() === '') { vertexMarkerColorOverride = null; rebuildVertexMarkers(); return }
  const rgb = parseRgbInput(input)
  if (!rgb) { alert('Could not parse that color — use "R,G,B" (0-255) or "#RRGGBB".'); return }
  vertexMarkerColorOverride = rgb
  registerMarkerColorCmap(MARKER_COLOR_CMAP, rgb)
  rebuildVertexMarkers()
}

// Hidden feature (shortcut: Alt+Shift+N): same, for the neighbor-ring marker
// spheres — hardcoded 'gray' (white) otherwise.
function promptNeighborMarkerColor() {
  const current = neighborMarkerColorOverride ? neighborMarkerColorOverride.join(',') : ''
  const input = prompt('Neighbor-ring marker color — "R,G,B" (0-255) or "#RRGGBB".\nLeave blank to reset to the default (white).', current)
  if (input === null) return
  if (input.trim() === '') { neighborMarkerColorOverride = null; rebuildVertexMarkers(); return }
  const rgb = parseRgbInput(input)
  if (!rgb) { alert('Could not parse that color — use "R,G,B" (0-255) or "#RRGGBB".'); return }
  neighborMarkerColorOverride = rgb
  registerMarkerColorCmap(NEIGHBOR_COLOR_CMAP, rgb)
  rebuildVertexMarkers()
}

// Re-colors the LH (+ Asym, which mirrors LH) surfaces' base tint and their
// shared "no data" mask color (flat_lh — see MASK_CMAP_FOR) to match
// lhSurfRgb() (either lhSurfColorOverride or the default), on both the
// already-rendered mesh (nv.setMeshProperty, same public API used for the
// streamline fixed-color picker — see applyStreamlineColor) and the
// colormap registry, re-touching any currently-visible mask layer so an
// already-masked "no data" patch updates immediately too, not just
// newly-masked vertices from here on.
function applyLhSurfColor() {
  const rgb = lhSurfRgb()
  const rgba255 = new Uint8Array([...rgb, 255])
  registerMarkerColorCmap('flat_lh', rgb)
  for (const nv of [nvLhL, nvAsym]) {
    const mesh = nv.meshes[0]
    if (!mesh) continue
    nv.setMeshProperty(mesh.id, 'rgba255', rgba255)
    if (mesh.layers?.length > 1) nv.setMeshLayerProperty(mesh.id, 1, 'colormap', 'flat_lh')
  }
}
function applyRhSurfColor() {
  const rgb = rhSurfRgb()
  const rgba255 = new Uint8Array([...rgb, 255])
  registerMarkerColorCmap('flat_rh', rgb)
  const mesh = nvRhL.meshes[0]
  if (!mesh) return
  nvRhL.setMeshProperty(mesh.id, 'rgba255', rgba255)
  if (mesh.layers?.length > 1) nvRhL.setMeshLayerProperty(mesh.id, 1, 'colormap', 'flat_rh')
}

// Hidden feature (shortcut: Alt+Shift+L): prompts for an RGB (or #hex) color
// for the LH surface's base tint (and the Asym panel, which mirrors it) —
// hardcoded blue otherwise. Leave the field blank to reset to the default.
function promptLhSurfColor() {
  const current = lhSurfColorOverride ? lhSurfColorOverride.join(',') : ''
  const input = prompt('LH surface color — "R,G,B" (0-255) or "#RRGGBB" (also applies to the Asymmetry panel).\nLeave blank to reset to the default (blue).', current)
  if (input === null) return
  if (input.trim() === '') { lhSurfColorOverride = null; applyLhSurfColor(); return }
  const rgb = parseRgbInput(input)
  if (!rgb) { alert('Could not parse that color — use "R,G,B" (0-255) or "#RRGGBB".'); return }
  lhSurfColorOverride = rgb
  applyLhSurfColor()
}

// Hidden feature (shortcut: Alt+Shift+R): same, for the RH surface's base
// tint — hardcoded orange otherwise.
function promptRhSurfColor() {
  const current = rhSurfColorOverride ? rhSurfColorOverride.join(',') : ''
  const input = prompt('RH surface color — "R,G,B" (0-255) or "#RRGGBB".\nLeave blank to reset to the default (orange).', current)
  if (input === null) return
  if (input.trim() === '') { rhSurfColorOverride = null; applyRhSurfColor(); return }
  const rgb = parseRgbInput(input)
  if (!rgb) { alert('Could not parse that color — use "R,G,B" (0-255) or "#RRGGBB".'); return }
  rhSurfColorOverride = rgb
  applyRhSurfColor()
}

// Hidden feature (shortcut: Alt+Shift+W): sets every surface's base tint to
// white in one go (no prompt) — the data overlay (colormap, opacity) is
// untouched, only the tint showing through where it doesn't cover.
function setAllSurfacesWhite() {
  lhSurfColorOverride = [255, 255, 255]
  rhSurfColorOverride = [255, 255, 255]
  applyLhSurfColor()
  applyRhSurfColor()
}

async function selectVertex(vertIdx, nvInst) {
  if (!currentMetric) return
  const mesh = nvInst.meshes[0]
  if (!mesh?.pts) return
  const nVerts = mesh.pts.length / 3
  if (vertIdx < 0 || vertIdx >= nVerts) return

  // Snap orthoslice crosshairs to vertex world position — using this
  // subject's own white surface instead if the clicked panel isn't currently
  // showing white/pial (see anatomicalPts). Setting crosshairPos directly
  // doesn't fire onLocationChange (only user slice interaction does), so call
  // createOnLocationChange() to refresh the position readout.
  const clickedSurfSelId = nvInst === nvRhL ? 'rhSurfSel' : nvInst === nvAsym ? 'asymSurfSel' : 'lhSurfSel'
  const clickedHemi = nvInst === nvRhL ? 'rh' : 'lh'   // nvAsym shares LH geometry
  const { pt: [vx, vy, vz] } = await anatomicalPts(clickedSurfSelId, clickedHemi, mesh.pts, vertIdx)
  if (nvSlices.volumes.length && typeof nvSlices.mm2frac === 'function') {
    const frac = nvSlices.mm2frac([vx, vy, vz])
    if (frac) {
      nvSlices.scene.crosshairPos = [...frac]
      if (typeof nvSlices.createOnLocationChange === 'function') nvSlices.createOnLocationChange()
      nvSlices.drawScene()
    }
  }

  selectedVertices = currentRingSet(vertIdx)
  const ringSet    = selectedVertices
  const lhMesh     = nvLhL.meshes[0]
  const rhMesh     = nvRhL.meshes[0]
  currentVertex = vertIdx

  // Drop a marker sphere on this vertex (plus smaller white spheres on its
  // neighbor-ring vertices) in every surface panel
  placeVertexMarkers()
  applyStreamlineSelection()   // respects the mode selector; no-op if streamlines haven't been loaded yet
  currentHemi = (nvInst === nvRhL) ? 'rh' : 'lh'   // nvAsym shares LH geometry, counts as 'lh'
  broadcastDwiCrosshair()

  // Read depth profiles from binary matrices, averaged over the neighbor-ring set
  const zscore = showZscore && hasZscore(currentMetric)
  const info = activeMetricInfo(currentMetric)
  const nd   = info.n_depths
  const [lhMat, rhMat, asymMat] = await Promise.all([
    ensureMatrix('lh',   currentMetric, zscore),
    ensureMatrix('rh',   currentMetric, zscore),
    ensureMatrix('asym', currentMetric, zscore),
  ])
  const rowsOf = mat => ringSet.map(vi => {
    const row = new Array(nd)
    for (let d = 0; d < nd; d++) row[d] = mat[vi*nd+d]
    return row
  })
  const lhArea = ringArea('lh', ringSet)
  const rhArea = ringArea('rh', ringSet)

  // The cohort normative band is in the raw metric's own units/scale — not
  // comparable to a z-score y-axis (z-scores are themselves already relative
  // to that same cohort), so it's skipped while z-score mode is on.
  let normStat = null
  if (showNormative && !zscore && NORMATIVE[currentMetric]) {
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
  // asymmetric) geometry, so their mm coordinates differ and both are worth
  // showing. Each panel independently corrects to this subject's white
  // surface if it isn't currently showing white/pial (see anatomicalPts) —
  // flagged with a trailing "(white)" so it's clear the number doesn't match
  // the distorted/template mesh actually on screen.
  const fmtMm = async (surfSelId, hemi, mesh, i) => {
    if (!mesh?.pts) return '—, —, — mm'
    const { pt, corrected } = await anatomicalPts(surfSelId, hemi, mesh.pts, i)
    const txt = `${pt[0].toFixed(1)}, ${pt[1].toFixed(1)}, ${pt[2].toFixed(1)} mm`
    return corrected ? `${txt} (white)` : txt
  }
  document.getElementById('vtx-display-lh').textContent = await fmtMm('lhSurfSel', 'lh', lhMesh, vertIdx)
  document.getElementById('vtx-display-rh').textContent = await fmtMm('rhSurfSel', 'rh', rhMesh, vertIdx)
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

// ── custom metric overlay ("other…" in the Metric dropdown) ──────────────────
// Drops an arbitrary local .func.gii/.gii (one or more darrays — one per
// depth, same as any regular metric) or .tsf (MRtrix track-scalar, the
// format cortical_*.sh writes — parsed client-side here, since NiiVue has no
// TSF support of its own) file onto one surface panel, outside the normal
// metric/z-score/collapse-depth pipeline (which assumes one metric drives
// all three panels together — this is a one-off, single-panel override
// instead, picked by a prompt after the file). It replaces mesh.layers[0]
// directly, the same slot every regular metric occupies, so the existing
// Data/Asym colormap/invert/opacity controls keep working on it afterward;
// only Data/Asym min/max/Auto don't — those are tied to currentMetric's own
// server-computed stats, which a custom file has none of, so its cal_min/
// cal_max are set once here, from the file's own finite data range, and
// left alone after that.
{
  const metricSel = document.getElementById('metricSel')
  const otherOpt = document.createElement('option')
  otherOpt.value = '__other__'
  otherOpt.textContent = 'other…'
  metricSel.appendChild(otherOpt)

  const otherFile = document.getElementById('metricOtherFile')

  // Finite-only min/max scan. A naive Math.min/max over raw values breaks
  // (NaN poisons the whole range) the moment any single value is NaN or
  // ±Inf — a real risk for an arbitrary externally-sourced gifti, unlike
  // the pipeline's own server-generated ones, which are always zero-filled
  // first (see cortical_browser.py's write_func_gii).
  function finiteRange(values) {
    let mn = Infinity, mx = -Infinity
    for (let i = 0; i < values.length; i++) {
      const v = values[i]
      if (Number.isFinite(v)) { if (v < mn) mn = v; if (v > mx) mx = v }
    }
    return Number.isFinite(mn) ? [mn, mx] : [0, 1]
  }

  // MRtrix track-scalar (.tsf) parser — mirrors cortical_io.py's
  // read_mrtrix_tsf(): a short ASCII "key: value" header terminated by a
  // line reading "END", then binary Float32LE/Float64LE data starting at
  // the byte offset the header's own "file" key gives, NaN-delimited
  // between tracks, optionally Inf-terminated (end-of-file marker).
  function parseTsf(buf) {
    const bytes = new Uint8Array(buf)
    const decoder = new TextDecoder('utf-8')
    let pos = 0
    function readLine() {
      const start = pos
      while (pos < bytes.length && bytes[pos] !== 10) pos++
      const line = decoder.decode(bytes.subarray(start, pos)).replace(/\r$/, '')
      pos++
      return line.trim()
    }
    const header = {}
    while (true) {
      if (pos >= bytes.length) throw new Error('no END header line found')
      const line = readLine()
      if (line === 'END') break
      const i = line.indexOf(':')
      if (i < 0) continue
      header[line.slice(0, i).trim()] = line.slice(i + 1).trim()
    }
    let TypedArrayCtor, bytesPerEl
    if (header.datatype === 'Float32LE') { TypedArrayCtor = Float32Array; bytesPerEl = 4 }
    else if (header.datatype === 'Float64LE') { TypedArrayCtor = Float64Array; bytesPerEl = 8 }
    else throw new Error(`unsupported datatype ${header.datatype}`)
    if (!header.file || !header.count) throw new Error('missing "file" or "count" header key')
    const offset = parseInt(header.file.split(/\s+/)[1], 10)
    const count = parseInt(header.count, 10)
    // Slice to a fresh buffer first: a typed-array view needs its byteOffset
    // aligned to its element size, which an arbitrary header offset isn't
    // guaranteed to be — slice() always starts a new buffer at 0.
    const sliced = buf.slice(offset)
    const data = new TypedArrayCtor(sliced, 0, Math.floor(sliced.byteLength / bytesPerEl))

    let end = data.length
    for (let i = 0; i < data.length; i++) {
      if (data[i] === Infinity || data[i] === -Infinity) { end = i; break }
    }
    const tracks = []
    let start = 0
    for (let i = 0; i < end; i++) {
      if (Number.isNaN(data[i])) { tracks.push(data.subarray(start, i)); start = i + 1 }
    }
    if (tracks.length !== count) throw new Error(`expected ${count} tracks, parsed ${tracks.length}`)
    return tracks
  }

  // Frame-major flattened values — NiiVue's own multi-darray GIFTI reader
  // concatenates each darray the same way: all vertices for frame 0, then
  // all vertices for frame 1, … — from a .tsf's per-vertex track arrays.
  // MRtrix's own -1 invalid-sample sentinel is zero-filled, the same
  // convention cortical_browser.py's write_func_gii() already uses
  // server-side ("NaN ... on the surface overlay would render unpredictably").
  function tsfTracksToLayerValues(tracks, nVert) {
    const maxLen = tracks.reduce((m, t) => Math.max(m, t.length), 1)
    const values = new Float32Array(nVert * maxLen)   // zero-filled by default
    const n = Math.min(nVert, tracks.length)
    for (let v = 0; v < n; v++) {
      const t = tracks[v]
      for (let d = 0; d < t.length; d++) {
        const x = t[d]
        values[d * nVert + v] = (x === -1) ? 0 : x
      }
    }
    return { values, nFrame4D: maxLen }
  }

  // Builds a complete NiiVue mesh-layer object (same shape applyCollapsedDataLayer
  // uses) from raw values + frame count, with a safe cal_min/cal_max.
  function buildLayer(values, nFrame4D, colormap, invert) {
    const [cal_min, cal_max] = finiteRange(values)
    return {
      values, nFrame4D, frame4D: 0,
      colormap, colormapNegative: 'winter', useNegativeCmap: false,
      colormapInvert: invert, colormapType: 0, colormapLabel: null,
      isTransparentBelowCalMin: false, isAdditiveBlend: false, colorbarVisible: true,
      outlineBorder: 0, opacity: layerOpacity, cal_min, cal_max,
      cal_minNeg: NaN, cal_maxNeg: NaN, global_min: cal_min, global_max: cal_max,
    }
  }

  async function loadCustomOverlay(nvInst, file, colormap, invert) {
    const mesh = nvInst.meshes[0]
    if (!mesh?.pts) { alert('That surface has no mesh loaded yet.'); return }
    const nVert = mesh.pts.length / 3
    let layer
    if (file.name.toLowerCase().endsWith('.tsf')) {
      const tracks = parseTsf(await file.arrayBuffer())
      if (tracks.length !== nVert) {
        alert(`[warn] ${file.name}: ${tracks.length} tracks vs ${nVert} surface vertices — loading anyway`)
      }
      const { values, nFrame4D } = tsfTracksToLayerValues(tracks, nVert)
      layer = buildLayer(values, nFrame4D, colormap, invert)
    } else {
      // .func.gii / .gii: NiiVue's own GIFTI reader, via its public loadLayer()
      // API — reused instead of hand-parsing GIFTI's XML+base64/binary format.
      // It APPENDS to mesh.layers rather than replacing, so pop it back off
      // and place it at [0] ourselves, the same slot every regular metric uses.
      const blobUrl = URL.createObjectURL(file)
      const before = mesh.layers.length
      try {
        await niivue.NVMesh.loadLayer({ url: blobUrl, name: file.name, colormap, colormapInvert: invert, opacity: layerOpacity }, mesh)
      } finally {
        URL.revokeObjectURL(blobUrl)
      }
      if (mesh.layers.length <= before) { alert(`Could not parse ${file.name} as a gifti overlay.`); return }
      layer = mesh.layers.pop()
      if (layer.values.length % nVert !== 0) {
        alert(`[warn] ${file.name}: ${layer.values.length} values vs ${nVert} surface vertices — loading anyway`)
      }
      const [cal_min, cal_max] = finiteRange(layer.values)
      layer.cal_min = cal_min; layer.cal_max = cal_max   // override NiiVue's own NaN-unsafe auto-range
    }
    mesh.layers[0] = layer
    mesh.updateMesh(nvInst.gl)
    nvInst.drawScene()
  }

  otherFile.addEventListener('change', async () => {
    const file = otherFile.files && otherFile.files[0]
    otherFile.value = ''   // reset so the same file can be re-picked later
    if (!file) return
    const answer = (prompt('Show this overlay on which surface — "left", "right", or "asym"?') || '').trim().toLowerCase()
    if (!answer) return   // cancelled
    const target = answer.startsWith('l') ? { nv: nvLhL, colormap: currentCmap, invert: dataInvert }
                 : answer.startsWith('r') ? { nv: nvRhL, colormap: currentCmap, invert: dataInvert }
                 : answer.startsWith('a') ? { nv: nvAsym, colormap: currentCmapAsym, invert: asymInvert }
                 : null
    if (!target) { alert(`"${answer}" is not "left", "right", or "asym".`); return }
    try {
      await loadCustomOverlay(target.nv, file, target.colormap, target.invert)
    } catch (e) {
      console.error('[other metric] failed to load', file.name, e)
      alert(`Could not load ${file.name}: ${e.message}`)
    }
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

// ── yoked rotation toggle ──────────────────────────────────────────────────────
document.getElementById('yokeChk').addEventListener('change', function() {
  yokeEnabled = this.checked
  if (yokeEnabled) yokeRecordAll()   // fresh baseline so the very next drag's delta is correct
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

// Step the vertex-marker sphere size multiplicatively (same 1.1-per-tick
// feel as the surface scroll-zoom), clamped to a sane range, then redraw
// at the current selection — placeVertexMarkers() itself no-ops if nothing
// is selected, so this is safe to call from the '>'/'<' shortcuts any time.
function stepVertexSphereScale(factor) {
  vertexSphereScale = Math.max(0.2, Math.min(5, vertexSphereScale * factor))
  placeVertexMarkers()
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
  // Hidden feature: Alt+Shift+V / Alt+Shift+N prompt for an RGB color to
  // recolor the selected-vertex / neighbor-ring marker spheres; Alt+Shift+L
  // / Alt+Shift+R do the same for the LH/RH surfaces' base tint; Alt+Shift+W
  // sets every surface to white (overlay untouched) in one go — carved out
  // of the modifier-key guard just below, since every other shortcut here
  // is a bare, unmodified key.
  if (e.altKey && e.shiftKey && !e.ctrlKey && !e.metaKey) {
    const key = e.key.toLowerCase()
    if (key === 'v') { promptVertexMarkerColor(); e.preventDefault(); return }
    if (key === 'n') { promptNeighborMarkerColor(); e.preventDefault(); return }
    if (key === 'l') { promptLhSurfColor(); e.preventDefault(); return }
    if (key === 'r') { promptRhSurfColor(); e.preventDefault(); return }
    if (key === 'w') { setAllSurfacesWhite(); e.preventDefault(); return }
    return
  }
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
    case 'x':
    case ' ': {   // toggle the crosshair via its checkbox so the UI stays in sync
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
    case 'y': {   // toggle yoked rotation across the surface panels via its checkbox
      const chk = document.getElementById('yokeChk')
      chk.checked = !chk.checked
      chk.dispatchEvent(new Event('change'))
      e.preventDefault()
      break
    }
    // Vertex marker size: '>' grows, '<' shrinks the selected-vertex sphere
    // and its neighbor-ring spheres together (the latter always stay 30% of
    // the former — see placeMarker/syncNeighborMarkers).
    case '>': stepVertexSphereScale(1.15); e.preventDefault(); break
    case '<': stepVertexSphereScale(1 / 1.15); e.preventDefault(); break
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
    paper_bgcolor: CT.bg, plot_bgcolor: CT.bg,
    font: { color: CT.text, size: 10 },
    margin: { l: 46, r: 12, t: 30, b: 34 },
    showlegend: true,
    legend: { orientation: 'h', x: 0, y: 1.2, font: { size: 9, color: CT.text }, groupclick: 'togglegroup',
              itemwidth: 30, tracegroupgap: 4 },
    dragmode: false,
    hovermode: 'closest',
    hoverdistance: 50,
    xaxis: { nticks: 5, color: CT.text, gridcolor: CT.grid, zerolinecolor: CT.grid, tickfont: { size: 10 } },
    yaxis: { autorange: 'reversed', title: { text: 'Depth (mm)', font: { color: CT.text } },
             nticks: 8, tickformat: '.1f', color: CT.text, gridcolor: CT.grid, zerolinecolor: CT.grid,
             tickfont: { size: 10 } },
    shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 0, y1: 0,
               line: { color: CT.accent, width: 1.5, dash: 'dash' } }],
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

chartLH   = makeChart('chart-lh',   chartLhColor,   'LH')
chartRH   = makeChart('chart-rh',   chartRhColor,   'RH')
chartAsym = makeChart('chart-asym', chartAsymColor, 'Asymmetry', true)

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
const mvFont = { size: 10, color: CT.text }
const mvLegend = { orientation: 'h', x: 0, font: { size: 9, color: CT.text }, itemwidth: 30, tracegroupgap: 4 }

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
    line: { color: chartLhColor, width: 3 }, marker: { size: 1 } },
  ...mahalSdBand(chartLhColor, 'lh'),
  { x: [], y: [], name: 'RH', mode: 'lines+markers', legendgroup: 'rh',
    line: { color: chartRhColor, width: 3 }, marker: { size: 1 } },
  ...mahalSdBand(chartRhColor, 'rh'),
], {
  paper_bgcolor: CT.bg, plot_bgcolor: CT.bg,
  font: mvFont,
  margin: { l: 46, r: 12, t: 30, b: 34 },
  showlegend: true,
  legend: { ...mvLegend, y: 1.2, groupclick: 'togglegroup' },
  dragmode: false, hovermode: 'closest',
  xaxis: { range: [0, mvMahalLim], title: { text: 'Mahalanobis distance', font: { color: CT.text } },
           color: CT.text, gridcolor: CT.grid, tickfont: { size: 10 } },
  yaxis: { autorange: 'reversed', title: { text: 'Depth (mm)', font: { color: CT.text } },
           nticks: 8, tickformat: '.1f', color: CT.text, gridcolor: CT.grid, tickfont: { size: 10 } },
  shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 0, y1: 0,
             line: { color: CT.accent, width: 1.5, dash: 'dash' } }],
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
    line: { color: chartLhColor, width: 2 }, marker: { size: 4 } },
  ...radarSdBand(chartLhColor, 'lh'),
  { r: [], theta: [], type: 'scatterpolar', name: 'RH', mode: 'lines+markers', legendgroup: 'rh',
    line: { color: chartRhColor, width: 2 }, marker: { size: 4 } },
  ...radarSdBand(chartRhColor, 'rh'),
], {
  paper_bgcolor: CT.bg,
  font: mvFont,
  margin: { l: 30, r: 30, t: 20, b: 20 },
  showlegend: true,
  legend: { ...mvLegend, y: 1.15, groupclick: 'togglegroup' },
  dragmode: false,
  polar: {
    bgcolor: CT.bg,
    radialaxis: { range: [0, mvZlim], color: CT.text, gridcolor: CT.gridPolar, tickfont: { size: 8 } },
    angularaxis: { color: CT.text, gridcolor: CT.gridPolar, tickfont: { size: 10 } },
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
    error_x: { type: 'data', array: [], color: chartLhColor, thickness: 1, width: 3 } },
  { x: [], y: [], type: 'bar', orientation: 'h', name: 'RH', marker: { color: [] },
    error_x: { type: 'data', array: [], color: chartRhColor, thickness: 1, width: 3 } },
], {
  paper_bgcolor: CT.bg, plot_bgcolor: CT.bg,
  font: mvFont,
  margin: { l: 70, r: 15, t: 10, b: 34 },
  showlegend: true,
  legend: { ...mvLegend, y: 1.15 },
  dragmode: false,
  barmode: 'group',
  xaxis: { range: [-mvZlim, mvZlim], title: { text: 'Z-score', font: { color: CT.text } },
           color: CT.text, gridcolor: CT.grid, tickfont: { size: 10 } },
  yaxis: { type: 'category', autorange: 'reversed', color: CT.text, tickfont: { size: 9 }, automargin: true },
  shapes: [{ type: 'line', xref: 'x', x0: 0, x1: 0, yref: 'paper', y0: 0, y1: 1,
             line: { color: CT.zero, width: 1 } }],
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
    'marker.color': [zColor(at(data.lh.z), chartLhColor), zColor(at(data.rh.z), chartRhColor)],
    'error_x.array': [at(data.lh.z_sd), at(data.rh.z_sd)],
    name: [mvLabel('LH', data.n_vertices), mvLabel('RH', data.n_vertices)],
  }, [0, 1])
  Plotly.relayout(chartZBar, { 'xaxis.range': [-mvZlim, mvZlim] })
}

// Re-theme the four NiiVue canvases (3 surfaces + orthoslices) in place.
// backColor is read fresh on every redraw (see the comment by SURF_CFG), so
// mutating opts.backColor and calling drawScene() is all a live switch needs —
// no need to recreate the instances or reload any volumes/surfaces/streamlines.
// The crosshair also follows the accent, matching the Plotly depth-reference line.
function applyNiivueTheme() {
  const light = isLightTheme()
  const surfBack = light ? SURF_BACK_LIGHT : SURF_BACK_DARK
  const slicBack = light ? SLIC_BACK_LIGHT : SLIC_BACK_DARK
  for (const nv of [nvLhL, nvRhL, nvAsym]) {
    nv.opts.backColor = [...surfBack]
    nv.drawScene()
  }
  nvSlices.opts.backColor = [...slicBack]
  nvSlices.setCrosshairColor(accentRgba())
  nvSlices.drawScene()
  // Re-clear the inline parentElement background NiiVue set at attachTo() time
  // (see the comment where attachTo() is called) in case anything internal
  // re-applies it; harmless no-op otherwise since it's already cleared.
  for (const nv of [nvLhL, nvRhL, nvAsym, nvSlices]) {
    if (nv.canvas?.parentElement) nv.canvas.parentElement.style.backgroundColor = ''
  }
  // Belt-and-suspenders: force a full NiiVue repaint the same way grid-gutter
  // drag/panel maximize already do elsewhere in this file, in case anything
  // else needs more than a bare drawScene() to recomposite.
  requestAnimationFrame(() => window.dispatchEvent(new Event('resize')))
}

// Re-theme all six Plotly panels in place (background/grid/text/accent colors,
// plus the hemisphere/asymmetry/normative trace colors) when the sidebar theme
// toggle changes. The profile charts (LH/RH/asym) have no other code path that
// ever restyles their trace colors, so that happens here explicitly; the
// multivariate panels get their colors from chartLhColor/chartRhColor on every
// render already, so replaying the last payload through them is enough.
function applyChartTheme() {
  const light = isLightTheme()
  CT = CHART_THEME[currentTheme()]
  chartLhColor   = chartColorFor(LH_COLOR, light)
  chartRhColor   = chartColorFor(RH_COLOR, light)
  chartAsymColor = chartColorFor(ASYM_BASE_COLOR, light)

  for (const chart of [chartLH, chartRH, chartAsym, chartMahal, chartZBar]) {
    Plotly.relayout(chart, {
      paper_bgcolor: CT.bg, plot_bgcolor: CT.bg,
      'font.color': CT.text, 'legend.font.color': CT.text,
      'xaxis.color': CT.text, 'xaxis.gridcolor': CT.grid, 'xaxis.zerolinecolor': CT.grid,
      'yaxis.color': CT.text, 'yaxis.gridcolor': CT.grid, 'yaxis.zerolinecolor': CT.grid,
    })
  }
  for (const chart of [chartLH, chartRH, chartAsym, chartMahal]) {
    Plotly.relayout(chart, { 'yaxis.title.font.color': CT.text, 'shapes[0].line.color': CT.accent })
  }
  Plotly.relayout(chartZBar, { 'shapes[0].line.color': CT.zero })
  Plotly.relayout(chartRadar, {
    paper_bgcolor: CT.bg, 'font.color': CT.text, 'legend.font.color': CT.text,
    'polar.bgcolor': CT.bg,
    'polar.radialaxis.color': CT.text, 'polar.radialaxis.gridcolor': CT.gridPolar,
    'polar.angularaxis.color': CT.text, 'polar.angularaxis.gridcolor': CT.gridPolar,
  })

  for (const [chart, color] of [[chartLH, chartLhColor], [chartRH, chartRhColor], [chartAsym, chartAsymColor]]) {
    Plotly.restyle(chart, { 'line.color': [color, CT.normative] }, [0, 3])
    Plotly.restyle(chart, { fillcolor: [hexToRgba(color, 0.16), hexToRgba(color, 0.18), CT.normativeFill] }, [0, 2, 5])
  }
  Plotly.restyle(chartMahal, { 'line.color': [chartLhColor, chartRhColor] }, [0, 3])
  Plotly.restyle(chartMahal, { fillcolor: [hexToRgba(chartLhColor, 0.18), hexToRgba(chartRhColor, 0.18)] }, [2, 5])
  Plotly.restyle(chartRadar, {
    'line.color': [chartLhColor, chartLhColor, chartLhColor, chartRhColor, chartRhColor, chartRhColor],
  }, [0, 1, 2, 3, 4, 5])
  Plotly.restyle(chartZBar, { 'error_x.color': [chartLhColor, chartRhColor] }, [0, 1])

  // Replay the last multivariate payload so the bars' per-value alpha-blended
  // marker colors (derived from chartLhColor/chartRhColor) pick up the change too.
  if (mvCurrent) { renderMahalChart(mvCurrent); renderRadarBar(mvCurrent, currentDepth) }
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
  // LH and RH share one x range (covering both, bands and normative included)
  // so the two profiles are directly comparable; asym is pinned separately to
  // the asym colormap limits (applyAsymValueLimits).
  const zscore = showZscore && hasZscore(currentMetric)
  let lo = Infinity, hi = -Infinity
  for (const [chart, stat, area, norm] of entries) {
    let label = chart.baseLabel
    if (zscore) label += ' (z)'
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

    if (chart !== chartAsym)
      for (const arr of [mean, plus, minus, normMean, normPlus, normMinus])
        for (const v of arr) if (v !== null) { if (v < lo) lo = v; if (v > hi) hi = v }

    Plotly.restyle(chart, {
      x: [mean, plus, minus, normMean, normPlus, normMinus],
      y: [depth, sdDepth, sdDepth, normDepth, normDepth, normDepth],
    }, [0, 1, 2, 3, 4, 5])
    Plotly.restyle(chart, { name: [label, normLabel] }, [0, 3])
    // LH/RH shade the area under the curve (against x=0) the same way the
    // Asymmetry plot always does, but only in z-score mode — a raw metric's
    // x=0 isn't a meaningful reference line the way "0 deviation" is for a
    // z-score, so there's nothing to usefully shade against outside it.
    // Asym itself is unaffected (built with fillToZero=true — see
    // profileTraces/makeChart — and never toggled here).
    if (chart !== chartAsym) Plotly.restyle(chart, { fill: [zscore ? 'tozerox' : 'none'] }, [0])
  }
  if (zscore) {
    // Pinned to the symmetric, zero-centered data CLim (applyDataValueLimits)
    // rather than auto-fit to this vertex's data — a z-score plot's whole
    // point is reading deviation from 0 against a fixed scale.
    applyDataValueLimits()
  } else if (Number.isFinite(lo) && Number.isFinite(hi)) {
    const pad = (hi - lo) * 0.05 || 0.5
    for (const c of [chartLH, chartRH]) Plotly.relayout(c, { 'xaxis.range': [lo - pad, hi + pad] })
  } else {
    for (const c of [chartLH, chartRH]) Plotly.relayout(c, { 'xaxis.autorange': true })
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
