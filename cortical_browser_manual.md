# Cortical Browser (Python / NiiVue) — User Manual

`cortical_browser.py` is an interactive, browser-based viewer for cortical diffusion‑MRI
depth‑profile data. It starts a small local web server and opens a page in your browser
showing bilateral hemisphere surfaces with overlay metrics, a multiplanar MRI orthoslice
view, per‑hemisphere depth‑profile charts, and a multivariate (Mahalanobis / z‑score)
explorer that compares a subject against a precomputed normative cohort.

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

Both the browser and the normative‑data builder read their shared settings from one file:

**`cortical_browser_config.py`**

```python
TEMPLATE = 'ico6_sym'    # surface template / naming convention: 'ico6_sym' or 'fsLR-32k'
METRICS  = ['fa', 'md', 'ad', 'rd', 'afd-par', 'afd-perp']   # metrics to search & display
```

| Setting | Meaning |
|---|---|
| `TEMPLATE` | Which surface template's files to look for. All TSF and surface files are expected to follow the `{hemi}_{…}_{TEMPLATE}…` naming convention (e.g. `lh_ico6_sym_fa.tsf`, `lh_white_ico6_sym.surf.gii`). Change this one string to retarget the whole toolchain (`ico6_sym` ↔ `fsLR-32k`). |
| `METRICS` | The allow‑list of metrics to search for, show in the **Metric** dropdown, and include in the normative dataset — in the order they should appear. Each metric `<m>` maps to per‑hemisphere files `{hemi}_{TEMPLATE}_<m>.tsf`. |

Because this file is the single source of truth, the browser and the normative builder
always agree on the template and metric set. Edit it in one place; there are no other
copies.

> :information_source: The browser searches for each configured metric's TSF files **recursively**
> under the subject directory, so files nested in sub‑folders (e.g.
> `dwi/csd_fixels_singletissue/`) are found, not only those directly in `dwi/`. A metric
> appears only when **both** `lh` and `rh` files are present.

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
    ├── surf/   {lh,rh}_white_<TEMPLATE>.surf.gii, …_inflated, pial, …
    └── dwi/    {lh,rh}_<TEMPLATE>_<metric>.tsf   (also found in sub-folders)
```

> :heavy_exclamation_mark: Vertex indices in this browser are **0‑based**.

---

## Running the browser

```bash
[micromamba|conda] activate corticalDWI
python cortical_browser.py <subjects_dir> <subject_id> [--port PORT]
```

| Argument | Default | Meaning |
|---|---|---|
| `subjects_dir` | `/home/lconcha/fs-edmonton` | FreeSurfer‑style subjects directory |
| `subject_id` | `sub-Mcd005` | Subject folder name under `subjects_dir` |
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

**Inputs**
- `<subjects_dir>/templates/subjects_to_average.txt` — the cohort: one subject ID per line.
- `cortical_browser_config.py` — `TEMPLATE` and `METRICS` (the same set the browser uses).

**What it does**
- For every subject in the list, it searches **recursively** for each metric's
  `{hemi}_{TEMPLATE}_<metric>.tsf`, masking the `-1` invalid sentinel to NaN.
- It stacks all subjects into a `(nVerts, nDepths, nSubjects, nMetrics)` array per hemisphere.

**Output**
- `<subjects_dir>/templates/normative/<TEMPLATE>_multivariate.h5`

The browser loads this file **lazily**: per‑metric mean ± SD is computed the first time you
tick **Show normative**, and the multivariate panels are computed on demand per selected
vertex. If the file is missing, those features are shown as unavailable ("no cohort data")
but the rest of the browser works normally.

> **Re‑run the builder whenever** you change `METRICS` or `TEMPLATE`, or the cohort list —
> otherwise the normative panels won't reflect the new configuration.

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
| **Depth** (slider + mm) | Cortical depth layer shown on the surfaces; the mm label is distance from the pial surface |
| **Data** min / max / **Auto** | Color limits for the LH/RH overlays; **Auto** sets them from the data's 2–98th percentile |
| **Data colormap** / **Inv** | Colormap for the LH/RH overlays and an invert toggle |
| **Ov** | Overlay opacity on the surfaces |
| **Asym** min / max / **Auto** | Color limits for the asymmetry surface (default ±1) |
| **Asym colormap** / **Inv** | Diverging colormap for the asymmetry surface and invert toggle |
| **Shader** | Surface lighting model (Matte / Phong / Diffuse) |
| **LH / RH / Asym surf** | Per‑panel surface geometry (white, pial, inflated, very‑inflated, average_*) |
| **Rad** | Radiological vs neurological orthoslice orientation |
| **X‑hair** | Show/hide the orthoslice crosshair |
| **WM** / **pial** | Overlay white‑matter / pial surface contours on the orthoslices (loaded on first use) |
| **Volume** | Choose which volume the orthoslices show; **other…** opens a file picker to load an extra volume (see *Orthoslice volume*) |
| **cmap** | Colormap for the orthoslice volume (a colorbar is drawn on the ortho view) |
| **clip** min / max / **Auto** | Clip the orthoslice color range; **Auto** restores the volume's default window |
| **Interp** | Smooth (linear) vs nearest‑neighbor orthoslice interpolation (shortcut `i`) |
| **Vertex** | Jump to a vertex by index (0‑based) |
| **Rings** | Number of neighbor rings to aggregate around the selected vertex |
| **Pivot@vertex** | Orbit the 3‑D surfaces around the selected vertex instead of the whole‑brain center |
| **Reset pivot** | Restore the 3‑D orbit pivot to the whole‑brain center |
| **Show normative** | Overlay the cohort mean ± SD band on the profile charts (needs the normative HDF5) |
| **\|z\|≤** | Max \|z\| shown on the radar and z‑score bar panels |
| **Mahal≤** | Max Mahalanobis distance shown on the multivariate depth panel |

---

## Interacting with the surfaces

- **Click** any of the three surface panels (or the orthoslices) to select the nearest vertex.
- The selected vertex is marked with a sphere on every panel; neighbor‑ring vertices get
  smaller markers.
- The orthoslices **snap** to the selected vertex's world coordinate.
- The depth‑profile and multivariate charts update to that vertex (and its ring neighbors
  when **Rings > 0**).
- **Scroll** over a surface to zoom it; drag to rotate. **Ctrl+scroll** zooms the orthoslices.

### Rings
Setting **Rings > 0** expands the selection to include mesh neighbors within that many
edge‑hops. Every plot then shows the **mean ± 1 SD** across the selected vertices — the
univariate profiles and all three multivariate panels aggregate over the same vertex set.

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

---

## Depth‑profile plots

Three charts show, per depth (x‑axis = mm from the pial surface):

1. **LH depth profile** and **RH depth profile** — the metric value, with a dashed ± SD band
   when Rings > 0, and (optionally) a **Normative** cohort mean ± SD band.
2. **Asymmetry profile** — `(LH − RH) / mean(LH, RH)` per depth, with a zero reference line.

A vertical marker tracks the currently selected depth; clicking a chart sets the depth.


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
working normally.

### Views & display
| Key | Action |
| --- | --- |
| `r` | Reset everything: orthoslice zoom/pan, orthoslice grayscale contrast, and the 3‑D surface framing (camera angles, zoom, rotation pivot). |
| `x` | Toggle the orthoslice crosshair on/off (mirrors the **X‑hair** checkbox). |
| `p` | Toggle **Pivot@vertex** — orbit the 3‑D surfaces around the selected vertex vs. the whole‑brain centre. |
| `i` | Toggle orthoslice interpolation — smooth (linear) vs nearest‑neighbor (mirrors the **Interp** checkbox). |

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

### Mouse
| Action | Effect |
| --- | --- |
| Click (surface or orthoslice) | Select the nearest vertex |
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
