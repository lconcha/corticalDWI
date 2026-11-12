#!/usr/bin/env python3
"""
cortical_glm_covariate.py — group-level, surface-corrected significance test
of metric ~ covariate (e.g. age_scan), one BrainStat SLM fit per metric (and
per depth, for depth-wise metrics), both hemispheres combined into one
bilateral mesh so RFT's cluster extent is computed over the real cortical
topology rather than two disconnected halves.

This is the "bring out the big guns" sibling of cortical_zscore_tsf.py's own
--adjust-for (that one fits a single, unsmoothed, per-vertex OLS as a cheap
good-enough adjustment) and of notebooks/age_covariate_brainstat.ipynb /
FCD_flair's age_covariate_brainstat_batch.py (that one also renders BrainSpace
figures per metric/depth — this script only writes the stat GIFTIs, nothing
visual, since it feeds a pipeline rule rather than a one-off exploratory run).
The model, the combined-bilateral-mesh trick, the smoothing (mesh_smooth at
--fwhm with a NaN-fill-before-smoothing workaround), and the SLM `mask`
(finite data AND inside the anatomical cortex label — excludes medial wall,
also works around a BrainStat RFT bug when any vertex has a NaN t-statistic)
are all exactly what that notebook/batch script do; see those for the
underlying explanation.

For each metric, writes 7 stats as .func.gii, one file per hemisphere per
stat (14 files per metric), with every depth of that metric stacked as its
own darray (in depth order) inside the file — a scalar metric (no depth
axis) gets a single-darray file:
    {hemi}.{metric}_{covariate}_{stat}.{template}.func.gii
  slope          — per-vertex slope of metric on the covariate (smoothed fit)
  intercept      — per-vertex intercept
  r              — Pearson's r (t / sqrt(t^2 + df))
  p-uncorrected  — two-sided p-value, uncorrected
  p-fdr          — Benjamini-Hochberg q-value (saved for reference — in this
                   BrainStat version FDR never actually uses the surface, see
                   reference_brainstat_env_setup memory; RFT below is the one
                   cortical_zscore_tsf.py's --adjust-for actually gates on)
  p-rft          — RFT CLUSTER-corrected p-value (slm.P['pval']['C']) — the
                   spatially-aware one; a cluster that reaches nowhere gives
                   BrainStat's own "not significant anywhere" (all 1.0)
  resid-sd       — sqrt(SSE/df): the residual SD of the fit, needed (along
                   with slope/intercept) to actually turn this into a
                   predicted-value z-score the way cortical_zscore_tsf.py's
                   existing mu/sd pair does; not one of BrainStat's "named"
                   outputs, just SSE/df under a readable name.
Each file carries GIFTI AnatomicalStructurePrimary metadata (CortexLeft/
CortexRight) at the FILE level (the only place Connectome Workbench reads it
from), plus per-darray metadata: Name=depthNN, N=<subjects used>,
DF=<residual degrees of freedom> — both constants across all vertices of one
metric/depth (BrainStat fits one fixed subject set per metric/depth, not a
per-vertex-varying one), so they're recorded once per darray rather than as
a full per-vertex array.

Fit ONLY on the control cohort, {subjects-dir}/templates/subjects_to_average.txt
(same file cortical_create_normative_data_from_tsf.py uses to build the
normative HDF5 -- the GLM must reflect the same reference population the
z-scores themselves are computed against, not whatever subjects happen to
have a covariate value). The HDF5's own `subjects` dataset is already built
from that file, so this is normally a no-op subset; it's enforced here too
rather than assumed, so a differently-built HDF5 (e.g. stale, or built for a
different cohort) can't silently pull patients into the fit.

Requires a cortex label GIFTI per hemisphere at
{subjects-dir}/templates/surf/{lh,rh}.cortex.{template}.label.gii (True =
cortex) — exits with an error if missing.

With --figures, also renders one SVG per metric/depth under <out-dir>/figures/
(matplotlib engine, via nilearn.plotting.plot_surf_stat_map — no VTK/Xvfb
needed, unlike age_covariate_brainstat_batch.py's BrainSpace figures, since
matplotlib's SVG backend is vector and headless by construction). Each figure
is 4 rows (p-rft, p-uncorrected, r, slope) x 4 panels (lh/rh x lateral/medial),
with one colorbar per row. Rendered inside the same worker that fits the SLM
(fit_one), as an in-memory SVG string via a StringIO buffer, and written out
by main() alongside the GIFTIs -- avoids re-pickling the surface mesh to a
second round of workers and keeps all file I/O centralized in main(), same
pattern as the GIFTI writes.

Usage:
    python cortical_glm_covariate.py [subjects_dir] --covariate age_scan
    python cortical_glm_covariate.py [subjects_dir] --covariate age_scan --list-only
    python cortical_glm_covariate.py [subjects_dir] --covariate age_scan --metrics surf/thickness

Options:
    --subjects-dir DIR     default: $SUBJECTS_DIR
    --template NAME        default: ico6_sym
    --covariate COL        participants.tsv column name (required)
    --covariates FILE      default: <subjects_dir>/bids/participants.tsv, else
                            <subjects_dir>/templates/covariates.tsv
    --covariate-id-col COL default: participant_id
    --fwhm MM              surface smoothing kernel in mm, applied before every fit (default: 10.0)
    --metrics M [M ...]    subset of metrics to run (default: all metrics in the HDF5)
    --out-dir DIR          default: <subjects_dir>/templates/normative/glm
    --workers N            parallel (metric, depth) fits (default: 4)
    --figures              also render a per-metric/depth SVG figure (see above) under <out-dir>/figures/
    --list-only            print the metric/depth plan and exit, without fitting anything
"""
import os
import sys
import argparse
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import h5py
import nibabel as nib
from scipy import stats as scipy_stats

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cortical_browser'))
from cortical_io import read_covariates, default_covariates_path, read_surface
from cortical_browser_config import TEMPLATE as TEMPLATE_DEFAULT

from brainstat.stats.terms import FixedEffect
from brainstat.stats.SLM import SLM
from brainstat.mesh.data import mesh_smooth
from brainstat.mesh.utils import mesh_edges

COVARIATE_FWHM_DEFAULT = 10.0
WORKERS_DEFAULT = 4

# filename stat tag -> key in fit_one()'s result dict
STAT_RESULT_KEYS = {
    'slope': 'slope', 'intercept': 'intercept', 'r': 'r',
    'p-uncorrected': 'p_uncorrected', 'p-fdr': 'q', 'p-rft': 'p_rft_cluster',
    'resid-sd': 'resid_sd',
}
ANATOMICAL_STRUCTURE = {'lh': 'CortexLeft', 'rh': 'CortexRight'}

# --figures rows: (result dict key, row label, colormap, fixed (vmin, vmax)
# or 'symmetric' to derive (-max(|row's own values|), +max(|...|)) at render
# time -- slope's range is data-dependent (native metric units, no fixed
# scale), whether to NaN out (hide) values above vmax.
# plasma_r/PuOr_r: reversed versions of the requested colormaps.
FIGURE_ROWS = [
    ('p_rft_cluster', 'p (RFT, cluster)', 'plasma_r', (0.0, 0.05), True),
    ('q', 'p (FDR)', 'plasma_r', (0.0, 0.05), True),
    ('p_uncorrected', 'p (uncorrected)', 'plasma_r', (0.0, 0.05), True),
    ('r', 'r', 'PuOr_r', (-1.0, 1.0), False),
    ('slope', 'slope', 'PuOr_r', 'symmetric', False),
]


def sanitize(metric):
    return metric.replace('/', '_')


def resolve_covariates_path(subjects_dir, override):
    if override:
        if not os.path.isfile(override):
            sys.exit(f'--covariates {override}: not found')
        return override
    candidates = [
        default_covariates_path(subjects_dir),
        os.path.join(subjects_dir, 'templates', 'participants.tsv'),
        os.path.join(os.path.dirname(subjects_dir.rstrip('/')), 'bids', 'participants.tsv'),
    ]
    path = next((p for p in candidates if p and os.path.isfile(p)), None)
    if path is None:
        sys.exit(f'No covariates file found; tried: {candidates}')
    return path


def load_cohort_subjects(subjects_dir):
    """Control cohort subject IDs from templates/subjects_to_average.txt --
    same file, same format (one ID per line) as
    cortical_create_normative_data_from_tsf.py uses to build the normative
    HDF5."""
    path = os.path.join(subjects_dir, 'templates', 'subjects_to_average.txt')
    if not os.path.isfile(path):
        sys.exit(f'Cohort list not found: {path}')
    with open(path) as f:
        return {line.strip() for line in f if line.strip()}


def nan_equal(a, b):
    """Elementwise equal, treating NaN==NaN as equal (unlike ==)."""
    both_nan = np.isnan(a) & np.isnan(b)
    return bool(np.all((a == b) | both_nan))


def is_scalar_metric(h5f, mi, n_depths):
    """True if this metric's value is identical at every depth (broadcast
    scalar, e.g. surf/thickness) -- checked by comparing depth 0 vs depth 1,
    on both hemispheres."""
    if n_depths < 2:
        return True
    for hemi in ('lh', 'rh'):
        a = h5f[f'{hemi}_M'][:, 0, :, mi]
        b = h5f[f'{hemi}_M'][:, 1, :, mi]
        if not nan_equal(a, b):
            return False
    return True


def load_cortex_mask(subjects_dir, template, n_lh, n_rh):
    """lh/rh anatomical cortex label GIFTIs (True = cortex, False = medial
    wall/non-cortex), concatenated into one boolean mask over the combined
    bilateral mesh, same vertex order as `surf` everywhere else here."""
    masks = []
    for hemi, n in (('lh', n_lh), ('rh', n_rh)):
        path = os.path.join(subjects_dir, 'templates', 'surf', f'{hemi}.cortex.{template}.label.gii')
        if not os.path.isfile(path):
            sys.exit(f'Cortex mask not found: {path}')
        data = nib.load(path).darrays[0].data.astype(bool)
        if data.shape[0] != n:
            sys.exit(f'{path}: {data.shape[0]} vertices, expected {n} to match the {hemi} surface')
        masks.append(data)
    return np.concatenate(masks)


def smooth_filled(Y, surf, fwhm):
    """Fill NaNs (per-vertex, across-subject mean; falling back to the whole-
    map mean for vertices NaN in every subject) and smooth with mesh_smooth.
    mesh_smooth has no concept of missing data -- it averages neighbors for
    ~FWHM**2/(2*ln2) iterations, so even a handful of NaN vertices spreads
    NaN across the entire connected hemisphere otherwise. The caller still
    applies its own `mask` (built from Y's ORIGINAL, unfilled completeness)
    when fitting, so these fill values never reach the actual results."""
    vertex_mean = np.nanmean(Y, axis=0)
    vertex_mean = np.where(np.isnan(vertex_mean), np.nanmean(Y), vertex_mean)
    Y_filled = np.where(np.isnan(Y), vertex_mean, Y)
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):   # mesh_smooth prints a progress bar; too noisy in parallel
        return mesh_smooth(Y_filled, surf, fwhm)


def fit_one(h5_path, metric, mi, depth, cov, ok, surf, n_lh, fwhm, cortex_mask,
            covariate=None, mesh_lh=None, mesh_rh=None, make_figure=False, bg_map=None):
    """Load Y for this metric/depth (both hemispheres), align subjects to the
    covariate, smooth, fit the combined bilateral SLM. Returns (result, status)
    -- result is None (with a status string explaining why) if there's too
    little usable data to fit anything. If make_figure, result also carries
    'figure_svg' (see render_stat_figure)."""
    with h5py.File(h5_path, 'r') as h5f:
        Y_lh_all = h5f['lh_M'][:, depth, :, mi].astype(np.float64)
        Y_rh_all = h5f['rh_M'][:, depth, :, mi].astype(np.float64)

    has_metric = np.isfinite(Y_lh_all).any(axis=0) | np.isfinite(Y_rh_all).any(axis=0)
    keep = ok & has_metric
    n_kept = int(keep.sum())
    if n_kept < 3:   # need at least 3 to have df>=1 for a 2-parameter model
        return None, 'skipped (too few subjects)'

    cov_kept = cov[keep]
    Y = np.concatenate([Y_lh_all[:, keep].T, Y_rh_all[:, keep].T], axis=1)

    # Vertices with finite data for every kept subject, AND inside the
    # anatomical cortex mask. Also works around a BrainStat RFT bug when any
    # vertex has a NaN t-statistic -- see age_covariate_brainstat_batch.py's
    # own comment on this (same fit, same workaround).
    finite_mask = np.isfinite(Y).all(axis=0) & cortex_mask

    # Empty/disconnected finite_mask crashes BrainStat's _compute_resls()
    # deep inside slm.fit() ("IndexError: arrays used as indices must be of
    # integer (or boolean) type") -- see age_covariate_brainstat_batch.py's
    # own comment; skip instead of hitting the bug.
    if mesh_edges(surf, finite_mask).shape[0] == 0:
        return None, 'skipped (no usable mesh edges -- finite data too sparse/absent at this depth)'

    Y_smooth = smooth_filled(Y, surf, fwhm)

    term = FixedEffect(cov_kept, names='covariate')
    slm = SLM(term, contrast=cov_kept, correction=['fdr', 'rft'], surf=surf, mask=finite_mask)
    slm.fit(Y_smooth)

    t = slm.t.ravel()
    q = slm.Q.ravel()
    p_rft_cluster = slm.P['pval']['C']
    if p_rft_cluster is None:
        # BrainStat leaves this None (not an all-ones array) when NO vertex
        # anywhere reaches the cluster-forming threshold -- equivalent to
        # "not significant everywhere".
        p_rft_cluster = np.ones_like(t)

    r = t / np.sqrt(t**2 + slm.df)
    intercept = slm.coef[0, :]   # slm.X is [intercept, covariate]
    slope = slm.coef[1, :]
    p_uncorrected = 2 * scipy_stats.t.sf(np.abs(t), df=slm.df)
    resid_sd = np.sqrt(slm.SSE[0] / slm.df)

    result = dict(
        n_subjects=n_kept, df=float(slm.df), slope=slope, intercept=intercept, r=r,
        p_uncorrected=p_uncorrected, q=q, p_rft_cluster=p_rft_cluster, resid_sd=resid_sd,
    )
    if make_figure:
        result['figure_svg'] = render_stat_figure(result, metric, covariate, depth,
                                                    mesh_lh, mesh_rh, cortex_mask, n_lh, bg_map)
    return result, 'ok'


def render_stat_figure(result, metric, covariate, depth, mesh_lh, mesh_rh, cortex_mask, n_lh, bg_map):
    """One SVG: FIGURE_ROWS rows (p-rft, p-uncorrected, r, slope) x 4 panels
    (lh/rh x lateral/medial), one colorbar per row. matplotlib's 'svg' backend
    is vector and headless by construction -- no VTK/Xvfb needed. Runs inside
    the same worker as the SLM fit (same process that already has `result`),
    rendering to an in-memory StringIO buffer rather than a file, since a
    worker process shouldn't be writing pipeline outputs directly -- main()
    collects the returned SVG text and writes it out itself, same as every
    other result field here.

    bg_map: cohort-mean surf/sulc, same combined bilateral vertex order as
    cortex_mask (None if the HDF5 has no surf/sulc metric). Plotted underneath
    the data with bg_on_data=True so gyri/sulci actually show through --
    plot_surf_stat_map gives flat, unshaded color otherwise; it only shades
    by multiplying the data color with a background map, it doesn't do any
    lighting/normal-based shading of its own."""
    import io
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from nilearn import plotting

    def row_limits(values, vlim):
        if vlim != 'symmetric':
            return vlim
        abs_max = float(np.nanmax(np.abs(values[cortex_mask])))
        if not np.isfinite(abs_max) or abs_max <= 0:
            abs_max = 1.0   # degenerate (e.g. all-zero slope/r); avoid vmin==vmax
        return -abs_max, abs_max

    panels = [('left', mesh_lh, cortex_mask[:n_lh], slice(0, n_lh), 'lateral'),
              ('left', mesh_lh, cortex_mask[:n_lh], slice(0, n_lh), 'medial'),
              ('right', mesh_rh, cortex_mask[n_lh:], slice(n_lh, None), 'lateral'),
              ('right', mesh_rh, cortex_mask[n_lh:], slice(n_lh, None), 'medial')]

    fig, axes = plt.subplots(len(FIGURE_ROWS), len(panels),
                              figsize=(4 * len(panels), 4 * len(FIGURE_ROWS)),
                              subplot_kw={'projection': '3d'})
    for i, (key, label, cmap, vlim, nan_above) in enumerate(FIGURE_ROWS):
        values = result[key]
        vmin, vmax = row_limits(values, vlim)
        for j, (hemi, mesh, cmask, sl, view) in enumerate(panels):
            vals = np.where(cmask, values[sl], np.nan)
            if nan_above:
                vals = np.where(vals > vmax, np.nan, vals)
            bg = bg_map[sl] if bg_map is not None else None
            # plot_surf (NOT plot_surf_stat_map) -- a panel can easily be
            # entirely NaN after the masking above (e.g. zero vertices
            # survive the RFT/FDR >0.05 cut in that one hemi/view, which is
            # the common case, not an edge case). plot_surf_stat_map computes
            # its colorbar range from the data itself (np.nanmin/nanmax) and
            # crashes with "Axis limits cannot be NaN or Inf" when that's
            # all-NaN. plot_surf takes cbar_vmin/cbar_vmax directly, so the
            # colorbar always reflects OUR fixed/derived vmin,vmax regardless
            # of whether this particular panel has any data at all.
            plotting.plot_surf(
                mesh, surf_map=vals, bg_map=bg, bg_on_data=bg is not None, darkness=0.7,
                hemi=hemi, view=view, axes=axes[i, j], figure=fig,
                cmap=cmap, vmin=vmin, vmax=vmax, cbar_vmin=vmin, cbar_vmax=vmax,
                colorbar=(j == len(panels) - 1),
                title=label if j == 0 else None,
            )
            # The mesh itself is a Poly3DCollection with one path per face
            # (~40k/hemi at ico6) -- left as vector, the SVG backend writes
            # every face as its own path and the file balloons into the
            # hundreds of MB. Rasterize just that collection (titles/colorbar/
            # text stay vector and crisp) so the file is actually usable.
            axes[i, j].collections[-1].set_rasterized(True)

    fig.suptitle(f'{metric}  ~  {covariate}   (depth {depth})')
    buf = io.StringIO()
    fig.savefig(buf, format='svg', dpi=150)
    plt.close(fig)
    return buf.getvalue()


def save_stat_giftis_combined(out_dir, metric, covariate, n_lh, template, depth_buffer):
    """Write all 7 stats as .func.gii, one file per hemisphere per stat --
    ALL depths of this metric stacked as separate darrays (one per depth, in
    depth order) inside each file; a scalar metric (no depth axis) just gets
    a single-darray file. Each file carries FILE-level
    AnatomicalStructurePrimary metadata (Workbench ignores it per-darray).

    depth_buffer: {stat_name: [(depth, full_combined_array, n, df), ...]} for
    ONE metric, in depth order."""
    base = f'{sanitize(metric)}_{covariate}'
    for stat_name, items in depth_buffer.items():
        if not items:
            continue
        for hemi, sl in (('lh', slice(0, n_lh)), ('rh', slice(n_lh, None))):
            anat = ANATOMICAL_STRUCTURE[hemi]
            darrays = []
            for depth, values, n, df in items:
                meta = nib.gifti.GiftiMetaData({'Name': f'depth{depth:02d}', 'N': str(n), 'DF': str(df)})
                darrays.append(nib.gifti.GiftiDataArray(
                    values[sl].astype(np.float32), intent='NIFTI_INTENT_ESTIMATE',
                    datatype='NIFTI_TYPE_FLOAT32', meta=meta,
                ))
            file_meta = nib.gifti.GiftiMetaData({'AnatomicalStructurePrimary': anat})
            out_path = os.path.join(out_dir, f'{hemi}.{base}_{stat_name}.{template}.func.gii')
            nib.save(nib.gifti.GiftiImage(darrays=darrays, meta=file_meta), out_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('subjects_dir', nargs='?', default=os.environ.get('SUBJECTS_DIR'))
    ap.add_argument('--template', default=TEMPLATE_DEFAULT, help='default: %(default)s')
    ap.add_argument('--covariate', required=True, help='participants.tsv column name')
    ap.add_argument('--covariates', metavar='FILE', help='default: <subjects_dir>/bids/participants.tsv, '
                     'else <subjects_dir>/templates/covariates.tsv')
    ap.add_argument('--covariate-id-col', default='participant_id', metavar='COL')
    ap.add_argument('--fwhm', type=float, default=COVARIATE_FWHM_DEFAULT, help='default: %(default)s')
    ap.add_argument('--metrics', nargs='*', default=None, help='subset of metrics to run (default: all in the HDF5)')
    ap.add_argument('--out-dir', default=None, help='default: <subjects_dir>/templates/normative/glm')
    ap.add_argument('--workers', type=int, default=WORKERS_DEFAULT, help='default: %(default)s')
    ap.add_argument('--figures', action='store_true',
                     help='also render a per-metric/depth SVG under <out-dir>/figures/ (see module docstring)')
    ap.add_argument('--list-only', action='store_true')
    args = ap.parse_args()

    if not args.subjects_dir:
        sys.exit('subjects_dir not given and SUBJECTS_DIR is not set')

    h5_path = os.path.join(args.subjects_dir, 'templates', 'normative', f'{args.template}_multivariate.h5')
    if not os.path.isfile(h5_path):
        sys.exit(f'Normative data not found: {h5_path}')

    with h5py.File(h5_path, 'r') as h5f:
        all_metrics = [m.decode() if isinstance(m, bytes) else m for m in h5f['metrics'][:]]
        subjects = [s.decode() if isinstance(s, bytes) else s for s in h5f['subjects'][:]]
        n_depths = min(h5f['lh_M'].shape[1], h5f['rh_M'].shape[1])

    if args.metrics:
        bad = [m for m in args.metrics if m not in all_metrics]
        if bad:
            sys.exit(f'Unknown metric(s) {bad}; available: {all_metrics}')
        metrics_to_run = args.metrics
    else:
        metrics_to_run = all_metrics

    covariates_path = resolve_covariates_path(args.subjects_dir, args.covariates)
    cov_table = read_covariates(covariates_path, id_col=args.covariate_id_col)
    sample_cols = next(iter(cov_table.values()), {})
    if args.covariate not in sample_cols:
        sys.exit(f"{covariates_path}: no column '{args.covariate}' (found: {', '.join(sample_cols)})")
    cov = np.full(len(subjects), np.nan, dtype=np.float64)
    for i, s in enumerate(subjects):
        v = cov_table.get(s, {}).get(args.covariate, np.nan)
        if isinstance(v, str):
            sys.exit(f"--covariate {args.covariate}: non-numeric value '{v}' for subject '{s}' in "
                     f"{covariates_path} (only a continuous covariate is supported)")
        cov[i] = v

    cohort = load_cohort_subjects(args.subjects_dir)
    is_cohort = np.array([s in cohort for s in subjects])
    print(f'Cohort (controls): {int(is_cohort.sum())}/{len(subjects)} subjects in the normative HDF5 '
          f'are in subjects_to_average.txt ({len(cohort)} listed there)')

    ok = np.isfinite(cov) & is_cohort
    if ok.sum() < 3:
        sys.exit(f"Only {int(ok.sum())} cohort (control) subjects have a value for covariate "
                  f"{args.covariate!r} -- can't fit anything")

    plan = []
    with h5py.File(h5_path, 'r') as h5f:
        for metric in metrics_to_run:
            mi = all_metrics.index(metric)
            if is_scalar_metric(h5f, mi, n_depths):
                plan.append((metric, mi, 0, True))
            else:
                for depth in range(n_depths):
                    plan.append((metric, mi, depth, False))

    out_dir = args.out_dir or os.path.join(args.subjects_dir, 'templates', 'normative', 'glm')

    print(f'Subjects dir   : {args.subjects_dir}')
    print(f'Normative HDF5 : {h5_path} ({len(subjects)} subjects)')
    print(f'Covariate      : {args.covariate} from {covariates_path} ({int(ok.sum())}/{len(subjects)} have a value)')
    print(f'Smoothing      : FWHM={args.fwhm:g}mm')
    print(f'Metrics        : {metrics_to_run}')
    print(f'Out dir        : {out_dir}')
    print(f'Planned fits   : {len(plan)}')
    for metric, mi, depth, scalar in plan:
        tag = 'scalar, depth 0 only' if scalar else f'depth {depth}'
        print(f'  - {metric:25s} {tag}')

    if args.list_only:
        return

    os.makedirs(out_dir, exist_ok=True)
    figures_dir = os.path.join(out_dir, 'figures')
    if args.figures:
        os.makedirs(figures_dir, exist_ok=True)

    surf_paths = {hemi: os.path.join(args.subjects_dir, 'templates', 'surf', f'{hemi}_white.{args.template}.surf.gii')
                  for hemi in ('lh', 'rh')}
    verts_lh, faces_lh = read_surface(surf_paths['lh'])
    verts_rh, faces_rh = read_surface(surf_paths['rh'])
    n_lh = verts_lh.shape[0]
    surf = {
        'tri': np.concatenate([faces_lh + 1, faces_rh + 1 + n_lh], axis=0).astype(np.int64),
        'coord': np.concatenate([verts_lh, verts_rh], axis=0).T.astype(np.float64),
    }
    cortex_mask = load_cortex_mask(args.subjects_dir, args.template, n_lh, verts_rh.shape[0])
    print(f'Combined bilateral surface: {surf["coord"].shape[1]} verts, {surf["tri"].shape[0]} faces')
    print(f'Cortex mask: {int(cortex_mask.sum())}/{len(cortex_mask)} vertices')
    mesh_lh, mesh_rh = (verts_lh, faces_lh), (verts_rh, faces_rh)

    bg_map = None
    if args.figures:
        if 'surf/sulc' in all_metrics:
            mi_sulc = all_metrics.index('surf/sulc')
            with h5py.File(h5_path, 'r') as h5f:
                sulc_lh = np.nanmean(h5f['lh_M'][:, 0, :, mi_sulc][:, is_cohort].astype(np.float64), axis=1)
                sulc_rh = np.nanmean(h5f['rh_M'][:, 0, :, mi_sulc][:, is_cohort].astype(np.float64), axis=1)
            bg_map = np.concatenate([sulc_lh, sulc_rh])
            print(f'Figure background: cohort-mean surf/sulc over {int(is_cohort.sum())} subjects')
        else:
            print("Figure background: no 'surf/sulc' metric in this HDF5 -- figures will be flat-shaded")

    t_start_all = time.time()
    by_metric = {}
    for metric, mi, depth, scalar in plan:
        by_metric.setdefault(metric, []).append((mi, depth))

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for i, (metric, depths) in enumerate(by_metric.items(), 1):
            depth_buffer = {k: [] for k in STAT_RESULT_KEYS}
            futs = {ex.submit(fit_one, h5_path, metric, mi, depth, cov, ok, surf, n_lh, args.fwhm, cortex_mask,
                               covariate=args.covariate, mesh_lh=mesh_lh, mesh_rh=mesh_rh,
                               make_figure=args.figures, bg_map=bg_map): depth
                    for mi, depth in depths}
            n_ok = 0
            for fu in as_completed(futs):
                depth = futs[fu]
                result, status = fu.result()
                if result is None:
                    print(f'[{i}/{len(by_metric)}] {metric} depth={depth}: {status}')
                    continue
                n_ok += 1
                for stat_name, result_key in STAT_RESULT_KEYS.items():
                    depth_buffer[stat_name].append((depth, result[result_key], result['n_subjects'], result['df']))
                if args.figures:
                    scalar = len(depths) == 1
                    fig_name = f'{sanitize(metric)}_{args.covariate}' + ('' if scalar else f'_depth{depth:02d}') + '.svg'
                    with open(os.path.join(figures_dir, fig_name), 'w') as f:
                        f.write(result['figure_svg'])
            for stat_name in depth_buffer:
                depth_buffer[stat_name].sort(key=lambda item: item[0])   # as_completed finishes out of order
            if n_ok:
                save_stat_giftis_combined(out_dir, metric, args.covariate, n_lh, args.template, depth_buffer)
            print(f'[{i}/{len(by_metric)}] {metric}: {n_ok}/{len(depths)} depths fit -> wrote giftis')

    print(f'Done: {len(plan)} fits in {time.time() - t_start_all:.1f}s')
    print(f'Out dir: {out_dir}')


if __name__ == '__main__':
    main()
