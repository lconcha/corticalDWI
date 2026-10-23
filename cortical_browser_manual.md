# Cortical Browser (Python / NiiVue) — User Manual

`cortical_browser.py` is an interactive, browser-based viewer for cortical diffusion‑MRI
depth‑profile data. It starts a small local web server and opens a page in your browser
showing bilateral hemisphere surfaces with overlay metrics, a multiplanar MRI orthoslice
view, per‑hemisphere depth‑profile charts, and a multivariate (Mahalanobis / z‑score)
explorer that compares a subject against a precomputed normative cohort. Depth from the pial
surface is obtained through pre-computed streamlines that integrate a Laplacian field.

It is the successor to the MATLAB `cortical_browser_2.m`; this manual covers the Python
version.

---

## Requirements

- The project's Python environment (has `numpy`, `nibabel`, `h5py`):
  ```bash
  [micromamba|conda] activate corticalDWI; # choose micromamba or conda depending on what you are using.
  ```

- A modern web browser (Chrome/Firefox/Edge). Rendering uses NiiVue (WebGL) and Chart.js,
  loaded from a CDN, so the machine running the browser needs internet access on first
  load.
- TSF files produced by the corticalDWI sampling pipeline (see the main `README.md`).

---

## Configuration file

Both the browser and the normative‑data builder read their shared settings from one file: `$SUBJECTS_DIR/corticalDWI_params.conf` (falling back to the repo's own copy of the same file for any key the study‑level one doesn't set — see that file's own header):

**`corticalDWI_params.conf`**

```init
target_type=ico6_sym          # surface template (fsLR-32k, ico6_sym, …)
nsteps=100                     # streamline integration steps
step_size=0.1                  # integration step size (mm)
tck_step_size=0.5              # resampled streamline step size (mm)
max_length=10                  # max streamline length after warp (mm)
nDepths=30                     # cortical depth points to extract
angle=45                       # max fixel–streamline angle (degrees)
csd_fixel_dir=csd_fixels_singletissue  # CSD fixel directory name (relative to dwi/)
mrds_fixel_dir=mrds_fixels             # MRDS fixel directory name (relative to dwi/mrds/)
browser_metrics=dwi/dti/fa,dwi/dki/fa,dwi/dti/md,dwi/dti/ad,dwi/dti/rd,dwi/csd_fixels_singletissue/afd-par,dwi/csd_fixels_singletissue/afd-perp,dwi/dki/mk,dwi/dki/ak,dwi/dki/rk,dwi/mrds/mrds_fixels/BIC/FA-par
```

Relevant for the browser and normative data creation are `target_type` and `browser_metrics`


| Setting | Meaning |
|---|---|
| `target_type` | Which surface template's files to look for. All TSF and surface files are expected to follow the `{hemi}_{…}_{TEMPLATE}…` naming convention (e.g. `lh_ico6_sym_fa.tsf`, `lh_white_ico6_sym.surf.gii`). Change this one string to retarget the whole toolchain (`ico6_sym` ↔ `fsLR-32k`). |
| `browser_metrics` | The allow‑list of metrics to search for, show in the **Metric** dropdown, and include in the normative dataset — in the order they should appear. Each metric is written `<folder>/<name>` (e.g. `dwi/dti/fa`, `dwi/dki/fa`, `mri/T1w_proc`, `dwi/mrds/mrds_fixels/BIC/FA-par`), where `<folder>` is the *full* path — every directory name from the subject directory down — of the directory that holds the `.tsf` files, however many folders deep. This is what tells apart metrics that several methods (or, for MRDS, different model‑selection variants) produce under the same name. It maps to the exact file `<folder>/{hemi}_{TEMPLATE}_<name>.tsf` under the subject. A bare name such as `fa` is rejected. Normative files built before this labelling must be rebuilt. |

Because this file is the single source of truth, the browser and the normative builder
always agree on the template and metric set. Edit it in one place; there are no other
copies.

> :information_source: Each configured metric names its file's exact location — the
> `<folder>` half of `<folder>/<name>` is the *full* path, every directory name from the
> subject directory down (e.g. `dwi/dti`, `dwi/csd_fixels_singletissue`,
> `dwi/mrds/mrds_fixels/BIC`), so the browser looks up `<folder>/{hemi}_{TEMPLATE}_<name>.tsf`
> directly rather than searching the subject tree. A metric appears only when **both** `lh`
> and `rh` files are present at that exact path.

### Expected data layout

```
<subjects_dir>/
├── templates/
│   ├── subjects_to_average.txt          # cohort list for the normative builder
│   ├── normative/
│   │   └── <TEMPLATE>_multivariate.h5    # produced by the normative builder
│   └── surf/                             # shared average surfaces (optional)
└── <subject_id>/
    ├── mri/    brain.nii.gz | brain.nii | brain.mgz   # background volume (optional)
    │           {lh,rh}_ico6_sym_laplace-wm-streamlines.tck   # T1-space streamlines (optional)
    │           {lh,rh}_<TEMPLATE>_<name>.tsf           # metrics labelled mri/<name>, e.g. mri/T1w_proc
    ├── surf/   {lh,rh}_white_<TEMPLATE>.surf.gii, …_inflated, pial, …
    └── dwi/    fa.nii.gz                                          # DWI-space FA map (optional)
                {lh,rh}_ico6_sym_laplace-wm-streamlines_dwispace.tck  # DWI-space streamlines (optional)
                dti/{lh,rh}_<TEMPLATE>_<name>.tsf                  # metrics labelled dwi/dti/<name>
                dki/{lh,rh}_<TEMPLATE>_<name>.tsf                  # metrics labelled dwi/dki/<name>
                csd_fixels_singletissue/{lh,rh}_<TEMPLATE>_<name>.tsf   # dwi/csd_fixels_singletissue/<name>
                mrds/mrds_fixels/<modsel>/{lh,rh}_<TEMPLATE>_<name>.tsf # dwi/mrds/mrds_fixels/<modsel>/<name>
```

Each `.tsf`'s metric label is `<folder>/<name>` — the full path from `<subject_id>/` down to
the directory holding the file, plus the file's own `<name>` part. A method that can only
ever produce one metric of a given name lives in a one‑segment folder (`mri/T1w_proc`,
`dwi/dti/fa`); MRDS, which fits several model‑selection variants under the same directory
tree, needs the deeper `dwi/mrds/mrds_fixels/<modsel>/<name>` form so `BIC` and `FTest`
don't collide.

The last three are all optional — without them, the browser still runs, just without the
**Streamlines** panel and/or **Open DWI space** button (see *Streamlines* and *DWI space*).

> :heavy_exclamation_mark: Vertex indices in this browser are **0‑based**.

---

## Running the browser

```bash
[micromamba|conda] activate corticalDWI
cortical_browser.sh <$SUBJECTS_DIR> <subject_id> [--port PORT]
```

| Argument | Default | Meaning |
|---|---|---|
| `$SUBJECTS_DIR` | `/home/lconcha/fs-edmonton` | FreeSurfer‑style subjects directory |
| `subject_id` | `sub-Mcd005` | Subject folder name under `$SUBJECTS_DIR` |
| `--port` | `8787` | Local server port (>1024) |

On launch it scans the subject for the configured metrics and surfaces, starts the server
at `http://localhost:<port>/`, and opens your browser. Press **Ctrl+C** in the terminal to
stop.

The browser shows **one subject per launch**. To view another subject, run the command
again with a different `subject_id` (the same port can be reused — each launch tags its
data URLs with a unique token so a previously viewed subject's data is never served from
the browser cache).

---

## Pre‑computing normative data

The normative (cohort) comparison — the **Show normative** band on the profile charts and
the entire multivariate row (Mahalanobis / radar / z‑scores) — is driven by a precomputed
HDF5 file. Build it once per cohort with:

```bash
[micromamba|conda] activate corticalDWI
python cortical_create_normative_data_from_tsf.py <subjects_dir>
# or rely on the SUBJECTS_DIR environment variable:
SUBJECTS_DIR=/path/to/subjects  python cortical_create_normative_data_from_tsf.py
```

Under Snakemake, the same call is available as a rule you trigger by name —
`cortical_snakerun.py build_normative_data` or `snakemake build_normative_data`
— so `--delete-rule build_normative_data` / `--status` pick it up too. It is
**not** wired as a dependency of anything else in the pipeline (see
`rules/zscore.smk`'s module docstring): the cohort is a deliberate human
choice, so this only ever runs when you ask for it by name.

**Inputs**
- `<subjects_dir>/templates/subjects_to_average.txt` — the cohort: one subject ID per line.
- `$SUBJECTS_DIR/corticalDWI_params.conf` — for `browser_metrics`.

**What it does**
- For every subject in the list and every configured `<folder>/<name>` metric, it looks up
  `<folder>/{hemi}_{TEMPLATE}_<name>.tsf` at that exact path (same lookup the browser itself
  uses — see *Configuration file* above), masking the `-1` invalid sentinel to NaN.
- It stacks all subjects into a `(nVerts, nDepths, nSubjects, nMetrics)` array per hemisphere.

**Output**
- `<subjects_dir>/templates/normative/<TEMPLATE>_multivariate.h5`

The browser loads this file **lazily**: per‑metric mean ± SD is computed the first time you
tick **Show normative**, and the multivariate panels are computed on demand per selected
vertex. If the file is missing, those features are shown as unavailable ("no cohort data")
but the rest of the browser works normally.

> **Re‑run the builder whenever** you change `browser_metrics` or `target_type`, or the
> cohort list — otherwise the normative panels won't reflect the new configuration. A
> normative file built before metric labels became `<folder>/<name>` (full path) still
> stores its old, bare names (`fa`, not `dwi/dti/fa`) — none of them will match a current
> `browser_metrics` entry, so the browser just shows **no cohort data** for every metric
> rather than an error. Rebuild it if that happens.

---

## Layout

```
┌──────────────────┬──────────────────┬──────────────────┐
│   LH lateral     │   RH lateral     │  Asymmetry index │   ← 3-D surfaces
│   (3-D surface)  │   (3-D surface)  │   (LH geometry)  │
├──────────────────┴──────────────────┴──────────────────┤
│        Multiplanar orthoslices (axial · coronal · sag)  │   ← background volume
├──────────────────┬──────────────────┬──────────────────┤
│  LH depth profile│  RH depth profile│ Asymmetry profile│   ← univariate plots
├──────────────────┼──────────────────┼──────────────────┤
│   Mahalanobis    │  |Z-score| radar │    Z-scores      │   ← multivariate explorer
│    distance      │                  │     (bars)       │
└──────────────────┴──────────────────┴──────────────────┘
```

Orthoslices default to **radiological** orientation (patient right on the viewer's left);
toggle with **Rad**.

---

## Control panel (top toolbar)

| Control | Description |
|---|---|
| **Metric** | Dropdown of the configured metrics found for this subject |
| **Z** | Show per‑vertex z‑scores against the cohort norm instead of raw values; disabled for metrics with no z‑scored data. Switches the Data/Asym colormap dropdowns to diverging‑only, with their own fixed default range (see *Thresholded diverging colormaps*) |
| **Depth** (slider + mm) | Cortical depth layer shown on the surfaces; the mm label is distance from the pial surface |
| **Data** min / max / **Auto** | Color limits for the LH/RH overlays; **Auto** sets them from the data's 2–98th percentile |
| **Data colormap** / **Inv** | Colormap for the LH/RH overlays and an invert toggle |
| **Data ±** (threshold) | Half‑width dead zone around zero shown as solid white — only affects the 13 diverging colormaps; 0 disables. Only enabled in **Z** mode (see *Thresholded diverging colormaps*) |
| **Ov** | Overlay opacity on the surfaces — lower it to reveal the base tint underneath (see *Surface base color*) |
| **Asym** min / max / **Auto** | Color limits for the asymmetry surface (default ±1) |
| **Asym colormap** / **Inv** | Diverging colormap for the asymmetry surface and invert toggle |
| **Asym ±** (threshold) | Same dead‑zone threshold as **Data ±**, independent, for the asymmetry surface. Only enabled in **Z** mode (see *Thresholded diverging colormaps*) |
| **Shader** | Surface lighting model (Matte / Phong / Diffuse) |
| **Yoke rotation** | Link rotation across the LH/RH/Asym 3‑D panels — mirrored for RH, same as Connectome Workbench's "Yoking" (shortcut `y`; see *Interacting with the surfaces*) |
| **LH / RH / Asym surf** | Per‑panel surface geometry (white, pial, inflated, very‑inflated, average_*) |
| **Rad** | Radiological vs neurological orthoslice orientation |
| **X‑hair** | Show/hide the orthoslice crosshair (shortcut: `x` or `Space`) |
| **WM** / **pial** | Overlay white‑matter / pial surface contours on the orthoslices (loaded on first use — also loaded lazily by Shift/Ctrl‑click vertex picking on the orthoslices, see *Interacting with the surfaces*) |
| **3D cutaway** / **Invert** | Carve the octant nearest the crosshair out of the orthoslice viewer's 3‑D volume render, revealing the three slice surfaces in 3‑D (shortcut `c`); **Invert** removes the opposite octant instead (see *Orthoslice volume*) |
| **Volume** | Choose which volume the orthoslices show; **other…** opens a file picker to load an extra volume (see *Orthoslice volume*) |
| **cmap** | Colormap for the orthoslice volume (a colorbar is drawn on the ortho view) |
| **clip** min / max / **Auto** | Clip the orthoslice color range; **Auto** restores the volume's default window |
| **Interp** | Smooth (linear) vs nearest‑neighbor orthoslice interpolation (shortcut `i`) |
| **Load streamlines** / **Show** | Load and show/hide the white‑matter Laplacian streamlines overlay (see *Streamlines*) |
| **Streamlines: Selected vertex / All** | Show only the streamline(s) seeded from the selected vertex/rings, or every streamline |
| **Color: Direction / Custom** | Color streamlines by local direction, or a single fixed color |
| **Open DWI space** | Open the subject's diffusion‑space data in a linked companion tab (see *DWI space*) |
| **Vertex** | Jump to a vertex by index (0‑based) |
| **Rings** | Number of neighbor rings to aggregate around the selected vertex |
| **Pivot@vertex** | Orbit the 3‑D surfaces around the selected vertex instead of the whole‑brain center |
| **Reset pivot** | Restore the 3‑D orbit pivot to the whole‑brain center |
| **Show normative** | Overlay the cohort mean ± SD band on the profile charts (needs the normative HDF5) |
| **\|z\|≤** | Max \|z\| shown on the radar and z‑score bar panels |
| **Mahal≤** | Max Mahalanobis distance shown on the multivariate depth panel |

---

## Interacting with the surfaces

- **Click** any of the three 3‑D surface panels to select the nearest vertex on whatever
  surface that panel currently shows.
- On the **orthoslices**, a plain click only moves the crosshair (and updates the
  world/voxel position and intensity readout) — it does **not** change the vertex selection.
  - **Shift‑click** selects the nearest **white**‑surface vertex to the clicked position.
  - **Ctrl‑click** selects the nearest **pial**‑surface vertex to the clicked position.
  - Both search only the white/pial contour geometry (the same one loaded by the **WM**/
    **pial** contour checkboxes) — inflated/very‑inflated surfaces don't occupy real
    anatomical space, so "nearest" wouldn't mean anything there. Either modifier also
    switches the **LH/RH/Asym surf** dropdowns to the surface you clicked, so the 3‑D panels,
    crosshair, and markers all end up showing that same surface.
- The selected vertex is marked with a sphere on every panel; neighbor‑ring vertices get
  smaller markers. `>` / `<` grow or shrink them (see *Vertex marker size*); `Alt+Shift+V` /
  `Alt+Shift+N` recolor them (see *Vertex marker color*).
- The orthoslices **snap** to the selected vertex's world coordinate.
- The depth‑profile and multivariate charts update to that vertex (and its ring neighbors
  when **Rings > 0**).
- **Scroll** over a surface to zoom it; drag to rotate. **Ctrl+scroll** zooms the orthoslices.

### Yoke rotation
With **Yoke rotation** on (or the `y` shortcut), dragging any one of the LH/RH/Asym 3‑D
panels rotates the other two along with it — the same feature as Connectome Workbench's
"Yoking". Because LH and RH are mirror images of each other, the rotation is **mirrored**
between them: turning LH/Asym toward their medial surface turns RH toward its medial
surface too, rather than snapping both to the same absolute camera angle. The Asym panel
(rendered on LH geometry) always moves with LH, never mirrored against it. Elevation (tilt
up/down) is shared as‑is, not mirrored. Zoom and pivot are independent per panel regardless
of yoking. Toggling yoking off/on never forces an immediate realignment — it only governs
rotation from that point on.

### Rings
Setting **Rings > 0** expands the selection to include mesh neighbors within that many
edge‑hops. Every plot then shows the **mean ± 1 SD** across the selected vertices — the
univariate profiles and all three multivariate panels aggregate over the same vertex set.

---

## Thresholded diverging colormaps

13 diverging colormaps support an optional dead zone around zero, shown as solid white
instead of a gradient: our own 3 hand‑rolled ones — **bwr** (blue‑white‑red), **cwr**
(cyan‑white‑red), **gwr** (green‑white‑red) — plus 10 straight from matplotlib's
[diverging set](https://matplotlib.org/stable/users/explain/colors/colormaps.html#diverging)
(**spectral** excluded — it has no true white stop at its center, so the dead zone wouldn't
read as "neutral"): **rdbu, rdgy, puor, piyg, prgn, brbg, rdylbu, rdylgn, coolwarm, seismic**.
This is
the **Data ±** / **Asym ±** field next to each panel's min/max/**Auto** controls: set it to a
value `t` and the colormap's whole color trajectory on each side gets squeezed between
**min**/**max** and **∓t**, holding flat white across **[‑t, +t]** instead of the plain
gradient you get with `t = 0`. This is useful for z‑score surfaces, where it reads as "not
significant" vs "significant deviation": e.g. min/max of **‑7/7** with a threshold of **2.29**
shows color only outside ±2.29, and solid white everywhere in between.

- The threshold only affects these 13 diverging colormaps — it's ignored for every other
  (sequential) colormap, since those have no "zero" to center a dead zone on.
- **Data ±** and **Asym ±** are independent, same as the **Data**/**Asym** min/max/colormap
  controls they sit next to — each panel can use a different diverging colormap with its own
  range and threshold at the same time.
- The colorbar legend under each panel always reflects the current threshold, so the dead
  zone is visible there too, not just on the 3‑D surfaces.
- **Data ±** / **Asym ±** are only enabled in **Z** (z‑score) mode — outside it they're grayed
  out, since raw values have no meaningful "zero deviation" to draw a significance cutoff
  against. Turning **Z** off restores whatever value either field had before (see *Z‑score
  mode defaults*), same as the colormap/range fields they sit next to.

### Z‑score mode defaults

Turning **Z** on changes the Data and Asym colormap controls:

- Both **Data colormap** and **Asym colormap** dropdowns are restricted to the 13 diverging
  colormaps (see *Thresholded diverging colormaps*) — every sequential colormap is hidden,
  since z‑scores are signed and a sequential colormap has no zero to diverge from.
- Both switch to **cwr** and reset to **min ‑3 / max 3 / threshold ±2.3** — a fixed default
  that applies the same way to every metric, rather than a per‑metric computed range.
- Whatever colormap/limits/threshold were active just before turning **Z** on are saved and
  restored **exactly** when **Z** goes back off — including if the metric has no z‑scored
  data and the browser disables **Z** for you automatically. Any tweaks made *while* in
  z‑score mode (a different colormap, a wider threshold, …) are discarded on the way out,
  not carried into raw mode.
- Switching **Metric** while **Z** is already on re‑applies the same fixed z‑score default
  (cwr / ‑3 / 3 / ±2.3) for the new metric, rather than remembering whatever was tweaked for
  the previous one. Use **Auto** to fit the range to that metric's actual z‑score data
  instead, same as in raw mode.
- With **Collapse depth** *also* on, the LH/RH/Asym surfaces instead show an unsigned mean
  |z| (the collapsed overlay averages |z| across depths, not z itself). Only **Asym
  colormap**/**Inv** go disabled in this one combination — the asym surface follows the
  **Data** colormap here, not its own (same as the raw, non‑z‑score collapse-depth case
  already did), so picking one would silently have no effect. **Data**/**Asym**
  min/max/**Auto**/± all stay fully editable and independent of each other, same as every
  other mode — set any range you like; **Auto** fits each to that panel's own collapsed
  data (which starts at 0 and is usually a different scale than the fixed z‑score default,
  since a mean across depths is smaller than any single depth's z).
- The colormap itself also changes shape here: since mean |z| is never negative, only the
  colormap's "hot" half is used (e.g. cwr's white‑to‑red) — white below **±**, ramping into
  color above it, with no "cool" half, since there's no negative side to an unsigned
  magnitude.

---

## Orthoslice volume

The **Volume** dropdown selects which volume the orthoslices display. At startup it holds
only the subject's `brain.mgz` / `brain.nii[.gz]` (if present). The last entry, **other…**,
opens a file picker so you can load any additional NIfTI/MGZ volume from disk; every loaded
volume is **appended to the dropdown**, so you can switch back and forth between them.

- Switching to an already‑loaded volume is fast — each volume is decoded once and kept in
  memory — and the world‑space crosshair position is preserved across the switch.
- **cmap** sets the colormap (a colorbar is drawn on the ortho view), and **clip** min / max
  clip the mapped intensity range (**Auto** restores the volume's default window). Both apply
  to whichever volume is currently shown.
- Right‑drag on the orthoslices adjusts window/level interactively; the **clip** boxes and the
  colorbar track it live.
- **Interp** (or the `i` shortcut) toggles between smooth (linear) and nearest‑neighbor
  display.

### 3‑D cutaway

The orthoslice viewer's 3‑D panel normally renders the whole volume as an opaque block.
**3D cutaway** (shortcut `c`) instead carves away the one octant nearest the crosshair,
opening the render up to reveal the three orthogonal slice surfaces in 3‑D context — closer
to the "corner view" most neuroimaging viewers show, rather than a full opaque render.
**Invert** flips which octant gets removed. The cutaway follows the crosshair live as you
move it.

---

## Streamlines

The **Streamlines** panel loads the subject's white‑matter Laplacian streamlines 
(`mri/{lh,rh}_ico6_sym_laplace-wm-streamlines.tck`, T1 space) and overlays it on the
orthoslices. Streamlines are stored **one per vertex**, on the same surface template used
everywhere else in the browser — streamline index *v* is the pathway seeded from vertex *v*.
That correspondence is also what makes the DWI‑space linking below possible.

- **Load streamlines** fetches the LH/RH files (lazily, on first click) and overlays them —
  colored by local direction by default.
- **Show** hides/shows the overlay without discarding it.
- **Streamlines: Selected vertex / All** — in *Selected vertex* mode, only the streamline(s)
  seeded from the currently selected vertex (and its neighbor rings, if **Rings** > 0) are
  drawn; *All* shows all the Laplacian streamlines regardless of selection. Picking a vertex or
  changing **Rings** updates the *Selected vertex* set immediately.
- **Color: Direction / Custom** switches between direction‑coded coloring and a single
  user‑picked color.

> :information_source: Streamlines render **only on the orthoslices**, not on the 3‑D surface
> panels.

---

## DWI space

**Open DWI space** launches a second, linked browser tab showing the subject's diffusion
data — the FA map (`dwi/fa.nii.gz`) by default — as its own multiplanar orthoslice viewer,
with the corresponding **DWI‑space** streamlines
(`dwi/{lh,rh}_ico6_sym_laplace-wm-streamlines_dwispace.tck`) overlaid. Unlike the main tab,
its 3‑D panel is always off — just the three orthogonal slices.

### Streamline position linking

The DWI‑space streamlines are the exact warp target of the T1‑space ones in the main tab:
point *i* along streamline *v* in the DWI file **is** the diffusion‑space location of point
*i* along streamline *v* in the T1 file. Since a selected vertex plus the current **Depth**
already picks out a specific point along a specific streamline in the main tab, that same
(vertex, depth) pair locates a point in DWI space directly — no separate registration or
transform step. Practically, this means:

- Selecting a vertex, or moving the **Depth** slider, in the **main (T1‑space) tab**
  instantly moves the crosshair in the **DWI‑space tab**, if it's open — the two tabs sync
  live over the browser's own cross‑tab messaging, no server round‑trip.
- The DWI tab's status line reports the vertex, depth, hemisphere, and resulting DWI‑space
  coordinate for the most recent sync.
- The DWI tab has its own **Streamlines: on/off** and **Mode: selected/all** buttons,
  independent of the main tab's — *selected* mode highlights the same vertex/ring set just
  synced from the main tab.

> :heavy_exclamation_mark: The DWI tab must already be open for a selection to reach it — open
> it once with **Open DWI space**; repeat clicks refocus the same tab rather than opening more.

### Loading DWI‑derived maps

The DWI tab has its own **Volume** dropdown, working exactly like the main tab's: it starts
with just `fa.nii.gz`, and its **other…** entry opens a file picker to load any additional
NIfTI/MGZ volume from disk — an MD map, an AD map, a fixel‑derived metric converted to
NIfTI, another subject's registered FA, anything. **There is no limit on how many volumes you
can add** — each one loaded is appended to the dropdown, exactly as in the main tab, so you
can build up as many DWI‑derived maps as you like and switch between them freely. Switching
back to an already‑loaded volume is instant (each is decoded once and kept resident), and the
crosshair position is preserved across switches.

- **cmap**, **min** / **max** control the colormap and clipped color range of whichever
  volume is currently shown (a colorbar is drawn on the view), exactly as in the main tab.
- Right‑drag adjusts window/level interactively, calibrated to feel the same as the main
  tab's orthoslices regardless of the loaded volume's intensity range (an FA map's 0–1 range
  and a T1's much wider range both feel the same to drag).

| Key | Action |
| --- | --- |
| `1`–`9` | Show the *n*th loaded volume, in dropdown order |
| `0` | Open the file picker to load a new volume |

These shortcuts are independent of the main tab's own `1`–`9`/`0` — each tab tracks its own
loaded volumes.

---

## Depth‑profile plots

Three charts show, per depth (y‑axis = mm from the pial surface, reversed so pial is at the
top; x‑axis = the value itself):

1. **LH depth profile** and **RH depth profile** — the metric value, with a dashed ± SD band
   when Rings > 0, and (optionally) a **Normative** cohort mean ± SD band.
2. **Asymmetry profile** — `(LH − RH) / mean(LH, RH)` per depth, with a zero reference line.

A vertical marker tracks the currently selected depth; clicking a chart sets the depth.

In **Z** (z‑score) mode, **LH**/**RH** also shade the area between the curve and the zero
reference line — the same way **Asymmetry** always does — since a z‑score's deviation from 0
is the whole point of the plot. Outside **Z** mode, LH/RH go back to a plain unfilled line: a
raw metric's x=0 isn't a meaningful reference to shade against. Asymmetry itself is unaffected
either way.


> :heavy_exclamation_mark:  **Invalid data** (the `-1` sentinel or depths beyond a short track) is treated as *no data*: it is **excluded from the averages** and drawn as a **gap** rather than a spurious value.

---

## Multivariate explorer (bottom row)

Compares the subject to the normative cohort at the selected vertex (aggregated over the
ring set, mean ± SD):

- **Mahalanobis distance** vs depth — one line per hemisphere; capped by **Mahal≤**.
- **|Z‑score| radar** — one spoke per metric, mean |z| with a dashed ± SD band; capped by **|z|≤**.
- **Z‑scores** — horizontal bars of the signed z per metric, with SD whiskers; capped by **|z|≤**.

These require the normative HDF5 file (see *Pre‑computing normative data*). If it is absent,
the panels read "no cohort data".

---

## Keyboard shortcuts

Shortcuts are handled by a global key listener and are **ignored while typing in a text
field or dropdown** (Vertex, Rings, colour‑limit inputs, selectors), so those controls keep
working normally. This section covers the **main (T1‑space) tab**; the **DWI‑space tab** has
its own smaller, independent set (see *DWI space*).

### Views & display
| Key | Action |
| --- | --- |
| `r` | Reset everything: orthoslice zoom/pan, orthoslice grayscale contrast, and the 3‑D surface framing (camera angles, zoom, rotation pivot). |
| `x` / `Space` | Toggle the orthoslice crosshair on/off (mirrors the **X‑hair** checkbox). |
| `p` | Toggle **Pivot@vertex** — orbit the 3‑D surfaces around the selected vertex vs. the whole‑brain centre. |
| `i` | Toggle orthoslice interpolation — smooth (linear) vs nearest‑neighbor (mirrors the **Interp** checkbox). |
| `c` | Toggle **3D cutaway** in the orthoslice viewer's 3‑D panel (mirrors the **3D cutaway** checkbox). |
| `y` | Toggle **Yoke rotation** across the LH/RH/Asym 3‑D panels (mirrors the **Yoke rotation** checkbox; see *Yoke rotation*). |

### Orthoslice navigation (moves the crosshair one voxel)
| Key | Plane | Direction |
| --- | --- | --- |
| `↑` / `↓` | Axial | superior / inferior |
| `→` / `←` | Sagittal | right / left |
| `PgUp` / `PgDn` | Coronal | anterior / posterior |

Left/right follow the **anatomical** L–R axis, independent of the radiological display flip.

### Cortical depth
| Key | Action |
| --- | --- |
| `+` (or `=`) / `Home` | Step depth deeper |
| `-` / `End` | Step depth shallower |

`=` works as an unshifted `+`. Depth is clamped to the current metric's range and the depth
slider stays in sync.

### Neighbor rings
| Key | Action |
| --- | --- |
| Numpad `+` / `-` | Increase / decrease the neighbor‑ring count |

The numpad keys are distinct from the main‑keyboard `+`/`-` (which control depth); they
require a real numeric keypad with NumLock on.

### Vertex marker size
| Key | Action |
| --- | --- |
| `>` | Grow the selected‑vertex marker sphere (and its neighbor‑ring spheres) |
| `<` | Shrink them |

Both scale together — the neighbor‑ring spheres always stay 30% of the main sphere's size.
No‑op if no vertex is currently selected.

### Vertex marker color
| Key | Action |
| --- | --- |
| `Alt+Shift+V` | Prompt for a color for the selected‑vertex marker sphere (default: yellow) |
| `Alt+Shift+N` | Prompt for a color for the neighbor‑ring marker spheres (default: white) |

Enter either `R,G,B` (0–255 each) or `#RRGGBB` hex. Leave the field blank and confirm to
reset that marker back to its default color. The two are independent — recoloring one doesn't
touch the other.

### Surface base color
| Key | Action |
| --- | --- |
| `Alt+Shift+L` | Prompt for a color for the LH surface's base tint (default: blue) — also applies to the **Asymmetry** panel, which shares LH's geometry |
| `Alt+Shift+R` | Prompt for a color for the RH surface's base tint (default: orange) |
| `Alt+Shift+W` | Set every surface's base tint to white in one step — no prompt |

This is the color a surface shows through wherever the **Data**/**Asym** overlay doesn't
cover it — lower opacity (**Ov**), or an explicit "no data" patch — not the overlay itself,
which is untouched by any of these. Same input format and blank‑to‑reset behavior as *Vertex
marker color*; the color persists across metric/mode switches (which reload the surfaces)
until reset or changed again.

### Orthoslice volume
| Key | Action |
| --- | --- |
| `1`–`9` | Show the *n*th loaded volume, in the order it appears in the **Volume** dropdown. A key with no matching volume (e.g. `4` when only one volume is loaded) does nothing. |
| `0` | Open the **other…** file picker to load a new volume. |

### Mouse
| Action | Effect |
| --- | --- |
| Click (surface panel) | Select the nearest vertex on that panel's current surface |
| Click (orthoslices) | Move the crosshair only — no vertex change |
| Shift + click (orthoslices) | Select the nearest **white**‑surface vertex |
| Ctrl + click (orthoslices) | Select the nearest **pial**‑surface vertex |
| Scroll over a surface | Zoom that 3‑D surface |
| Drag on a surface | Rotate the 3‑D view |
| Ctrl + scroll on orthoslices | Zoom the orthoslice view |
| Click on a profile chart | Set the current depth |

---

## Notes / technical details

- **Vertex indices are 0‑based** (unlike the MATLAB browser, which is 1‑based).
- **Asymmetry index** is `(LH − RH) / ((LH + RH) / 2)` — a fractional difference relative to
  the bilateral mean; undefined ratios propagate as gaps, not zeros.
- **Invalid‑data handling:** the display reader masks the `-1` invalid sentinel and
  short‑track padding to NaN, so profiles and averages exclude them. On the surface overlays
  those vertices render at the low end of the colormap.
- `-1` values can also occur for per-fixel metrics if one of the fixels is not found (typically occurs when only one fixel exists within a voxel, and `afd-rad` can be assigned, but `afd-tan` is undefined).
- **Caching:** static surface/overlay files are cached aggressively within a session but each
  launch tags its URLs with a unique token, so switching subjects on the same port never
  shows stale data.
- **Normative data is lazy:** the HDF5 cohort file is only read when you tick **Show
  normative** or select a vertex with the multivariate panels active.
