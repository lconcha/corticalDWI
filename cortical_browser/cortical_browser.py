#!/usr/bin/env python3
"""
cortical_browser.py — Production NiiVue cortical browser.

Three surface panels (LH lateral, RH lateral, Asymmetry index on LH geometry),
three orthoslice panels with surface contours, three depth-profile charts.
CLim and colormap controls for both data and asymmetry surfaces.

Usage:
    python cortical_browser.py [subjects_dir] [subj_id] [--port PORT]
"""
import os, sys, glob, json, time, threading, webbrowser, argparse, tempfile, re, warnings, shutil, atexit, signal, subprocess
import numpy as np
import nibabel as nib
import h5py

sys.path.insert(0, os.path.dirname(__file__))
from cortical_io import read_mrtrix_tsf, pad_to_matrix
from cortical_browser_config import TEMPLATE, METRICS   # shared with the normative builder
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

STEP_MM         = 0.5
NIIVUE_CDN      = 'https://cdn.jsdelivr.net/npm/@niivue/niivue/dist/index.js'
PLOTLY_CDN      = 'https://cdn.plot.ly/plotly-2.35.2.min.js'

_WEB_DIR = os.path.dirname(__file__)

def _read_web_file(name):
    with open(os.path.join(_WEB_DIR, name), encoding='utf-8') as f:
        return f.read()

# ── HTML template ──────────────────────────────────────────────────────────────
_HTML    = _read_web_file('main.html')
_MAIN_JS = _read_web_file('main.js')

_DWI_HTML = _read_web_file('dwi.html')
_DWI_JS   = _read_web_file('dwi.js')


# ── file discovery ─────────────────────────────────────────────────────────────

def kill_other_instances():
    """Find and kill other running cortical_browser.py processes (not self)."""
    script_name = os.path.basename(__file__)
    self_pid = os.getpid()
    out = subprocess.run(['ps', '-eo', 'pid,cmd'], capture_output=True, text=True).stdout
    victims = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        pid_str, cmd = parts
        if script_name not in cmd or 'grep' in cmd:
            continue
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        if pid == self_pid:
            continue
        victims.append((pid, cmd))

    if not victims:
        print('No other cortical_browser.py instances found.')
        return

    for pid, cmd in victims:
        print(f'Killing pid {pid}: {cmd}')
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except PermissionError:
            print(f'  [WARN] no permission to kill pid {pid}')

    time.sleep(1.0)
    for pid, cmd in victims:
        try:
            os.kill(pid, 0)   # still alive?
        except ProcessLookupError:
            continue
        print(f'  pid {pid} still alive, sending SIGKILL')
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


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


STREAMLINE_FILENAMES = {
    'lh': 'lh_ico6_sym_laplace-wm-streamlines.tck',
    'rh': 'rh_ico6_sym_laplace-wm-streamlines.tck',
}


def find_streamline_files(subj_dir):
    """Locate the per-hemisphere Laplace white-matter streamlines
    (.tck, in T1 space) under mri/, if present. Returns {'lh': path, 'rh': path},
    only including hemispheres whose file actually exists."""
    mri_dir = os.path.join(subj_dir, 'mri')
    result = {}
    for hemi, fname in STREAMLINE_FILENAMES.items():
        p = os.path.join(mri_dir, fname)
        if os.path.isfile(p):
            result[hemi] = p
    return result


DWI_STREAMLINE_FILENAMES = {
    'lh': 'lh_ico6_sym_laplace-wm-streamlines_dwispace.tck',
    'rh': 'rh_ico6_sym_laplace-wm-streamlines_dwispace.tck',
}


def find_dwi_files(subj_dir):
    """Locate the DWI-space FA map and its corresponding per-hemisphere
    streamlines under dwi/. The FA map now lives in a model-specific
    sub-folder (e.g. dwi/dti/fa.nii.gz) rather than directly under dwi/, so
    it's found via a recursive search, preferring dwi/dti/fa.nii.gz (the
    canonical DTI FA) if present and otherwise falling back to whatever
    fa.nii.gz turns up first (e.g. under dwi/dki/). The streamlines are still
    written directly under dwi/, so those are looked up there as before.
    These are the same streamlines as STREAMLINE_FILENAMES pre-warp: point
    index i of streamline v here is the DWI-space location of point i of
    streamline v in the T1-space file, so a (vertex, depth) pair already
    selected in T1 space locates directly into these files with no separate
    transform. Returns {'fa': path, 'lh': path, 'rh': path}, omitting any
    that are missing."""
    dwi_dir = os.path.join(subj_dir, 'dwi')
    result = {}
    dti_fa = os.path.join(dwi_dir, 'dti', 'fa.nii.gz')
    if os.path.isfile(dti_fa):
        result['fa'] = dti_fa
    else:
        fa_matches = sorted(glob.glob(os.path.join(dwi_dir, '**', 'fa.nii.gz'), recursive=True))
        if fa_matches:
            result['fa'] = fa_matches[0]
    for hemi, fname in DWI_STREAMLINE_FILENAMES.items():
        p = os.path.join(dwi_dir, fname)
        if os.path.isfile(p):
            result[hemi] = p
    return result


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


def find_tsf_metrics(subj_dir, template=TEMPLATE, metrics=METRICS, verbose=True):
    """Locate each configured metric's lh/rh TSF files anywhere under the
    subject dir (recursive, mirroring the normative builder's search — so files
    nested in sub-folders like dwi/csd_fixels_singletissue/ are found, not just
    those directly in dwi/). A metric is included only when both hemispheres are
    present as siblings, and the result preserves the config's metric order.

    With verbose=True (the default) it reports, per configured metric, whether it
    was found and in which sub-folder, or why it was skipped (no file at all, or
    an lh with no matching rh sibling) — so a missing metric is visible in the
    terminal rather than silently absent from the dropdown."""
    if verbose:
        print(f'Finding TSF files (template={template}) under {subj_dir}:')
    found = {}
    for metric in metrics:
        lh_matches = sorted(glob.glob(os.path.join(subj_dir, '**', f'lh_{template}_{metric}.tsf'),
                                      recursive=True))
        chosen = next(((lh, rh) for lh in lh_matches
                       if os.path.isfile(rh := os.path.join(os.path.dirname(lh),
                                                            f'rh_{template}_{metric}.tsf'))), None)
        if chosen:
            found[metric] = {'lh': chosen[0], 'rh': chosen[1]}
            if verbose:
                rel = os.path.relpath(chosen[0], subj_dir)
                print(f'  found    {metric:12s} {rel}')
        elif verbose:
            if not lh_matches:
                print(f'\033[31m  MISSING  {metric:12s} no lh/rh .tsf found\033[0m')
            else:
                rel = os.path.relpath(os.path.dirname(lh_matches[0]), subj_dir)
                print(f'\033[31m  MISSING  {metric:12s} lh in {rel}/ but no rh sibling\033[0m')
    if verbose:
        print(f'  -> {len(found)}/{len(metrics)} configured metric(s) available: {list(found) or "none"}')
    return found


# ── TSF → func.gii conversion ─────────────────────────────────────────────────
# Split into a cheap in-memory "stats" pass (needed up front for every metric,
# so the dropdown/depth-slider/CLim inputs work before its overlay exists) and
# an expensive "materialize" pass (write the actual .func.gii + .f32 files),
# which only runs for a metric once it's actually requested.

def read_tsf_matrix(tsf_path):
    """Read a TSF file into a padded (n_vertices, n_depths) float32 matrix.
    Both the -1 invalid sentinel and the short-track NaN padding are left as
    NaN (matching the stats/normative readers) so they read as "no data" —
    excluded from profile averages and shown as gaps, never as spurious 0/-1
    values. The surface overlay re-fills these to 0 at gii-write time
    (write_func_gii), since NaN is only meaningful for the profile matrices."""
    _, tracks = read_mrtrix_tsf(tsf_path)
    M = pad_to_matrix(tracks).astype(np.float32)   # NaN where a track is short
    M[M == -1] = np.nan                            # mask mrtrix invalid sentinel
    return M


def matrix_cal_range(M):
    finite = M[np.isfinite(M) & (M > 0)]
    cal_min = float(np.percentile(finite,  2)) if finite.size else 0.0
    cal_max = float(np.percentile(finite, 98)) if finite.size else 1.0
    return round(cal_min, 4), round(cal_max, 4)


def compute_asym_matrix(lh_M, rh_M):
    """Asymmetry index (LH-RH)/mean(LH,RH). Invalid inputs (NaN) and undefined
    ratios (both hemispheres zero → 0/0) propagate as NaN, so they're excluded
    from profiles and cohort averages rather than biasing them toward 0."""
    LH = lh_M.astype(np.float64)
    RH = rh_M.astype(np.float64)
    denom = (LH + RH) / 2.0
    with np.errstate(divide='ignore', invalid='ignore'):
        A = ((LH - RH) / denom).astype(np.float32)
    A[~np.isfinite(A)] = np.nan   # NaN input or 0/0 → undefined
    return A


def asym_cal_range():
    # Fixed symmetric range for the asymmetry index; the front-end uses this for
    # both the surface color limits and the asym plot's y-axis.
    return -1.0, 1.0


def write_func_gii(M, out_path):
    # NaN ("no data") is meaningful only for the profile matrices; on the
    # surface overlay it would render unpredictably, so zero-fill a copy here
    # (the caller's array — written to the .f32 profile file — keeps its NaN).
    # Invalid vertices then clamp to the low end of the colormap, as before.
    M = np.nan_to_num(M, nan=0.0)
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
        # LH/RH depth counts usually match (same streamline-sampling config for
        # both hemis), but aren't guaranteed to — e.g. mri/-space metrics sampled
        # from cortical_tcksample_mri.sh can differ by a step or two between
        # hemispheres. Truncate both to their common depth so lh/rh/asym stay
        # aligned: the front end assumes a single n_depths per metric shared by
        # all three surfaces (depth slider, matrix stride, compute_asym_matrix's
        # elementwise LH/RH op all rely on this).
        common_d = min(lh_M.shape[1], rh_M.shape[1])
        lh_M = lh_M[:, :common_d]
        rh_M = rh_M[:, :common_d]
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


def compute_normative_ring_stat(subjects_dir, metric, kind, vertices, template=TEMPLATE):
    """Correct cohort mean/SD for a set of >1 vertices: average each control
    subject's values across the selected vertices first, then take mean/SD
    across subjects. This is NOT the same as averaging the precomputed
    per-vertex normative_*_std.f32 maps together (mean-of-SDs != SD-of-means)
    — that pooled-variance shortcut is what normativeRingStat() used to do
    for rings, and only the mean of the two approaches happens to agree.
    Reads the raw per-subject stack straight from the cohort h5 file, so it's
    only worth calling for >1 vertex; a lone vertex needs no aggregation and
    the precomputed per-vertex file is exact and cheaper to serve."""
    h5_path = os.path.join(subjects_dir, 'templates', 'normative', f'{template}_multivariate.h5')
    if not os.path.isfile(h5_path):
        return None
    with h5py.File(h5_path, 'r') as h5f:
        cohort_metrics = list(h5f['metrics'].asstr()[:])
        if metric not in cohort_metrics:
            return None
        idx = cohort_metrics.index(metric)
        n_cohort_verts = h5f['lh_M'].shape[0]
        verts = sorted({int(v) for v in vertices if 0 <= int(v) < n_cohort_verts})
        if not verts:
            return None

        with np.errstate(invalid='ignore'), warnings.catch_warnings():
            warnings.simplefilter('ignore', category=RuntimeWarning)
            if kind == 'asym':
                lh_stack = np.asarray(h5f['lh_M'][verts])[:, :, :, idx].astype(np.float64)  # (nV, nDL, nSub)
                rh_stack = np.asarray(h5f['rh_M'][verts])[:, :, :, idx].astype(np.float64)  # (nV, nDR, nSub)
                common_d = min(lh_stack.shape[1], rh_stack.shape[1])
                stack = compute_asym_matrix(lh_stack[:, :common_d, :], rh_stack[:, :common_d, :]).astype(np.float64)
            elif kind in ('lh', 'rh'):
                stack = np.asarray(h5f[f'{kind}_M'][verts])[:, :, :, idx].astype(np.float64)  # (nV, nD, nSub)
            else:
                return None

            # Average within each control subject across the selected vertices...
            subj_vec = np.nanmean(stack, axis=0)   # (nDepths, nSubjects)
            # ...then take mean/SD across subjects.
            mean = np.nanmean(subj_vec, axis=1)
            sd   = np.nanstd(subj_vec, axis=1)
            n    = np.sum(~np.isnan(subj_vec), axis=1)

    return {'mean': _jsonable(mean), 'sd': _jsonable(sd), 'n': [int(x) for x in n]}


# ── multivariate (Mahalanobis + z-score) explorer ──────────────────────────────
# Port of cortical_subject_mahal_by_depth.m: for one vertex, at each depth,
# compare the subject's per-metric vector against the cohort's multivariate
# distribution (both hemispheres pooled to better estimate the covariance).
# Computed on demand per selected vertex, served as JSON to the /mahal endpoint —
# far too much data to precompute for every vertex (nVerts * nDepths * nMetrics^2).

def _subject_tsf_nan(tsf_path):
    """One subject metric/hemi as an (nVerts, nDepths) matrix with the -1
    invalid sentinel and short-track padding both left as NaN — unlike the
    display path's read_tsf_matrix, which zero-fills them (wrong for stats)."""
    _, tracks = read_mrtrix_tsf(tsf_path)
    M = pad_to_matrix(tracks)          # float32, NaN where a track is short
    M[M == -1] = np.nan                # mask invalid sentinel (as the cohort builder does)
    return M


def _mahal_sq(x, mu, cov, n_valid, n_metrics):
    """Squared Mahalanobis distance of vector x from a distribution with mean
    mu and covariance cov (matching MATLAB mahal, which returns the squared
    distance). NaN (→ None) when the subject vector is incomplete or the
    cohort can't support a covariance for this many metrics."""
    if cov is None or n_valid <= n_metrics:
        return None
    if np.any(np.isnan(x)) or np.any(np.isnan(mu)):
        return None
    d = x - mu
    try:
        sol = np.linalg.solve(cov, d)
    except np.linalg.LinAlgError:
        sol = np.linalg.pinv(cov) @ d
    val = float(d @ sol)
    return val if np.isfinite(val) else None


def _jsonable(arr):
    """numpy float array → nested Python lists with any non-finite value
    (NaN/inf, e.g. an all-invalid mean or a single-sample std) replaced by
    None, so the front end draws a gap rather than a bogus point."""
    a = np.asarray(arr, dtype=np.float64)
    conv = lambda x: (float(x) if np.isfinite(x) else None)
    if a.ndim == 1:
        return [conv(v) for v in a]
    return [[conv(v) for v in row] for row in a]


def compute_multivariate(subjects_dir, tsf_metrics, subj_cache, vertices,
                         primary=None, template=TEMPLATE):
    """Per-depth squared Mahalanobis distance and per-metric z-scores (LH and
    RH), aggregated over a set of vertices (the selected vertex plus its
    neighbor-ring set). Mirrors the univariate profile panels: each vertex
    yields a Mahalanobis-by-depth vector and per-depth z-vectors, and we return
    the mean ± sd across vertices. With a single vertex the sd arrays are all
    None (no band). Returns a JSON-ready dict, or None if there's no cohort
    file / no shared metrics / no in-range vertex."""
    if isinstance(vertices, int):
        vertices = [vertices]
    h5_path = os.path.join(subjects_dir, 'templates', 'normative', f'{template}_multivariate.h5')
    if not os.path.isfile(h5_path):
        return None
    with h5py.File(h5_path, 'r') as h5f:
        cohort_metrics = list(h5f['metrics'].asstr()[:])
        n_subjects = int(h5f['subjects'].shape[0])
        n_cohort_verts = h5f['lh_M'].shape[0]
        # Metrics the cohort AND this subject both have, ordered by the cohort's
        # metric axis so the subject vector lines up with lh_M/rh_M column-wise.
        metrics = [m for m in cohort_metrics if m in tsf_metrics]
        # Unique, in-range, sorted so h5py fancy indexing is happy (order does
        # not matter — we aggregate across vertices).
        verts = sorted({int(v) for v in vertices if 0 <= int(v) < n_cohort_verts})
        if not metrics or not verts:
            return None
        midx = [cohort_metrics.index(m) for m in metrics]
        lh_c = np.asarray(h5f['lh_M'][verts])[:, :, :, midx].astype(np.float64)  # (nV, nDepthsL, nSub, nUsed)
        rh_c = np.asarray(h5f['rh_M'][verts])[:, :, :, midx].astype(np.float64)  # (nV, nDepthsR, nSub, nUsed)

    # Subject's own per-metric matrices (NaN-masked), cached for the session.
    for m in metrics:
        if m not in subj_cache:
            subj_cache[m] = (_subject_tsf_nan(tsf_metrics[m]['lh']),
                             _subject_tsf_nan(tsf_metrics[m]['rh']))

    n_used   = len(metrics)
    n_depths = min(lh_c.shape[1], rh_c.shape[1])   # combine both hemis per depth
    nV       = len(verts)

    def subj_vec(vertex, hemi_i):
        out = np.full((n_depths, n_used), np.nan)
        for j, m in enumerate(metrics):
            M = subj_cache[m][hemi_i]
            if vertex >= M.shape[0]:
                continue
            row = M[vertex]
            dd = min(n_depths, row.shape[0])
            out[:dd, j] = row[:dd]
        return out

    # Per-vertex results: NaN where undefined so the aggregation can skip them.
    mahal = [np.full((nV, n_depths), np.nan) for _ in (0, 1)]           # (nV, nDepths)
    zsc   = [np.full((nV, n_depths, n_used), np.nan) for _ in (0, 1)]   # (nV, nDepths, nUsed)
    for vi, vertex in enumerate(verts):
        subj = (subj_vec(vertex, 0), subj_vec(vertex, 1))   # (lh, rh)
        for d in range(n_depths):
            cohort_d = np.vstack([lh_c[vi, d], rh_c[vi, d]])   # (2*nSub, nUsed)
            C = cohort_d[~np.any(np.isnan(cohort_d), axis=1)]  # drop subjects missing any metric
            nC = C.shape[0]
            if nC >= 1:
                mu = C.mean(axis=0)
                sd = C.std(axis=0, ddof=0)                     # population std, as MATLAB std(...,1)
            else:
                mu = np.full(n_used, np.nan); sd = np.full(n_used, np.nan)
            cov = np.atleast_2d(np.cov(C, rowvar=False, ddof=1)) if nC > 1 else None
            for h in (0, 1):
                x = subj[h][d]
                ms = _mahal_sq(x, mu, cov, nC, n_used)
                mahal[h][vi, d] = np.nan if ms is None else ms
                with np.errstate(invalid='ignore', divide='ignore'):
                    zsc[h][vi, d, :] = np.where(sd > 0, (x - mu) / sd, np.nan)

    def aggregate(h):
        """Mean ± sd across vertices, ignoring NaN. Signed z feeds the bar
        chart; |z| feeds the radar; both need their own mean/sd because
        mean(|z|) != |mean(z)|. sd uses ddof=1, so it is None for a lone
        vertex."""
        m_arr, z_arr = mahal[h], zsc[h]
        absz = np.abs(z_arr)
        with warnings.catch_warnings():   # all-NaN slices are expected (fully invalid depths)
            warnings.simplefilter('ignore', category=RuntimeWarning)
            nan_sd = lambda a, shape: (np.nanstd(a, axis=0, ddof=1) if nV > 1 else np.full(shape, np.nan))
            return {
                'mahal':    _jsonable(np.nanmean(m_arr, axis=0)),
                'mahal_sd': _jsonable(nan_sd(m_arr, n_depths)),
                'z':        _jsonable(np.nanmean(z_arr, axis=0)),
                'z_sd':     _jsonable(nan_sd(z_arr, (n_depths, n_used))),
                'absz':     _jsonable(np.nanmean(absz, axis=0)),
                'absz_sd':  _jsonable(nan_sd(absz, (n_depths, n_used))),
            }

    return {
        'vertex': int(primary if primary is not None else verts[0]),
        'n_vertices': nV, 'metrics': metrics, 'step_mm': STEP_MM,
        'n_depths': int(n_depths), 'n_subjects': n_subjects,
        'lh': aggregate(0), 'rh': aggregate(1),
    }


# ── HTML generation ───────────────────────────────────────────────────────────

def make_html(subj_id, vol_path, lh_path, rh_path, overlay_info, port, surf_types=None,
              normative_info=None, template=TEMPLATE, cache_bust='', streamline_files=None,
              dwi_available=False):
    base = f'http://localhost:{port}/data'
    # The /data/ files are served immutable (see _reply), and their URLs depend
    # only on hemi/template/metric — NOT the subject. Two subjects on the same
    # port therefore share URLs, so the browser would serve subject A's cached
    # bytes for subject B. A per-launch token in the query string gives each
    # session its own cache keys (the server ignores the query when locating the
    # file), busting the cache across subjects while keeping it within a session.
    q = f'?v={cache_bust}' if cache_bust else ''

    volumes = []
    if vol_path:
        volumes.append({'url': f'{base}/{os.path.basename(vol_path)}{q}',
                        'name': os.path.basename(vol_path),
                        'colormap': 'gray', 'opacity': 1})
    # Per-hemisphere accent colors; the front-end derives the LH/RH plot line
    # colors from these same rgba255 values so surfaces and plots stay in sync.
    surfs = []
    if lh_path:
        surfs.append({'url': f'{base}/{os.path.basename(lh_path)}{q}',
                      'rgba255': [102, 179, 255, 255], 'hemi': 'lh'})   # #66B3FF
    if rh_path:
        surfs.append({'url': f'{base}/{os.path.basename(rh_path)}{q}',
                      'rgba255': [255, 133, 77, 255], 'hemi': 'rh'})    # #FF854D

    surf_types_urls = {
        surf_type: {hemi: f'{base}/{os.path.basename(p)}{q}' for hemi, p in hemis.items()}
        for surf_type, hemis in (surf_types or {}).items()
    }
    streamlines_urls = {hemi: f'{base}/{os.path.basename(p)}{q}' for hemi, p in (streamline_files or {}).items()}

    metric_opts = '\n'.join(
        f'      <option value="{m}">{m}</option>' for m in overlay_info
    ) if overlay_info else '<option value="">none</option>'

    first_info = next(iter(overlay_info.values())) if overlay_info else None
    max_depth  = (first_info['n_depths'] - 1) if first_info else 0
    init_depth = max_depth // 2

    subs = [
        ('__SUBJ_ID__',        subj_id),
        ('__NIIVUE_CDN__',     NIIVUE_CDN),
        ('__PLOTLY_CDN__',     PLOTLY_CDN),
        ('__VOLUMES_JSON__',   json.dumps(volumes)),
        ('__SURFS_JSON__',     json.dumps(surfs)),
        ('__SURF_TYPES_JSON__', json.dumps(surf_types_urls)),
        ('__STREAMLINES_JSON__',     json.dumps(streamlines_urls)),
        ('__DWI_AVAILABLE_JSON__', json.dumps(bool(dwi_available))),
        ('__NORMATIVE_JSON__', json.dumps(normative_info or {})),
        ('__METRICS_JSON__',   json.dumps(overlay_info)),
        ('__BASE_URL__',       base),
        ('__CACHE_BUST__',     cache_bust),
        ('__TEMPLATE__',       template),
        ('__STEP_MM__',        str(STEP_MM)),
        ('__METRIC_OPTIONS__', metric_opts),
        ('__MAX_DEPTH__',      str(max_depth)),
        ('__INIT_DEPTH__',     str(init_depth)),
        ('__INIT_DEPTH_MM__',  f'{init_depth * STEP_MM:.1f}'),
    ]
    html, js = _HTML, _MAIN_JS
    for k, v in subs:
        html = html.replace(k, v)
        js   = js.replace(k, v)
    return html, js


def make_dwi_html(subj_id, dwi_files, port, cache_bust=''):
    """Build the companion DWI-space page: FA map + the DWI-space streamlines,
    synced to the main tab's vertex/depth selection via BroadcastChannel."""
    base = f'http://localhost:{port}/data'
    q = f'?v={cache_bust}' if cache_bust else ''
    fa_path = dwi_files.get('fa')
    fa_url = f'{base}/{os.path.basename(fa_path)}{q}' if fa_path else ''
    streamlines_urls = {hemi: f'{base}/{os.path.basename(p)}{q}'
                         for hemi, p in dwi_files.items() if hemi in ('lh', 'rh')}

    subs = [
        ('__SUBJ_ID__',        subj_id),
        ('__NIIVUE_CDN__',     NIIVUE_CDN),
        ('__FA_URL__',         fa_url),
        ('__STREAMLINES_JSON__', json.dumps(streamlines_urls)),
        ('__STEP_MM__',        str(STEP_MM)),
        ('__CACHE_BUST__',     cache_bust),
    ]
    html, js = _DWI_HTML, _DWI_JS
    for k, v in subs:
        html = html.replace(k, v)
        js   = js.replace(k, v)
    return html, js


# ── HTTP server ───────────────────────────────────────────────────────────────

def make_handler(html_bytes, file_map, overlay_arrays, materialized, out_dir,
                  subjects_dir=None, normative_materialized=None, template=TEMPLATE,
                  tsf_metrics=None, dwi_html_bytes=None, main_js_bytes=None, dwi_js_bytes=None):
    # Session cache of the subject's NaN-masked per-metric matrices, populated
    # lazily on the first /mahal request and reused across vertices.
    mv_subject_cache = {}
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
            if path == '/dwi':
                if dwi_html_bytes:
                    self._reply(200, 'text/html; charset=utf-8', dwi_html_bytes)
                else:
                    self._reply(404, 'text/plain', b'DWI space not available for this subject\n')
                return
            if path == '/static/main.js':
                self._reply(200, 'text/javascript; charset=utf-8', main_js_bytes)
                return
            if path == '/static/dwi.js':
                if dwi_js_bytes:
                    self._reply(200, 'text/javascript; charset=utf-8', dwi_js_bytes)
                else:
                    self._reply(404, 'text/plain', b'DWI space not available for this subject\n')
                return
            if path == '/mahal':
                self._serve_mahal()
                return
            if path == '/normative_ring':
                self._serve_normative_ring()
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

        def _serve_mahal(self):
            """On-demand multivariate stats (squared Mahalanobis + z-scores) for
            one vertex, as JSON — computed fresh from the cohort h5 + subject
            tsf files (no static file to materialize)."""
            if not subjects_dir or not tsf_metrics:
                self._reply(404, 'text/plain', b'no cohort data\n')
                return
            qs = parse_qs(urlparse(self.path).query)
            try:
                vtx = int(qs.get('vertex', [''])[0])
            except (ValueError, TypeError):
                self._reply(400, 'text/plain', b'bad or missing vertex\n')
                return
            # Optional neighbor-ring set to aggregate over (mean ± sd across
            # vertices); defaults to the selected vertex alone.
            verts_arg = qs.get('vertices', [''])[0]
            try:
                verts = [int(v) for v in verts_arg.split(',') if v != ''] or [vtx]
            except (ValueError, TypeError):
                verts = [vtx]
            try:
                payload = compute_multivariate(subjects_dir, tsf_metrics, mv_subject_cache,
                                               verts, primary=vtx, template=template)
            except Exception as exc:   # noqa: BLE001 — report, don't crash the server
                self._reply(500, 'text/plain', f'mahal error: {exc}\n'.encode('utf-8'))
                return
            if payload is None:
                self._reply(404, 'text/plain', b'no multivariate data\n')
                return
            self._reply(200, 'application/json', json.dumps(payload).encode('utf-8'))

        def _serve_normative_ring(self):
            """On-demand correct cohort mean/SD for >1 selected vertices (see
            compute_normative_ring_stat) — computed fresh from the cohort h5's
            raw per-subject stack, since the precomputed per-vertex
            normative_*_std.f32 maps can't be combined into a ring SD by simple
            averaging."""
            if not subjects_dir:
                self._reply(404, 'text/plain', b'no cohort data\n')
                return
            qs = parse_qs(urlparse(self.path).query)
            metric = qs.get('metric', [''])[0]
            kind = qs.get('kind', [''])[0]
            if not metric or kind not in ('lh', 'rh', 'asym'):
                self._reply(400, 'text/plain', b'bad or missing metric/kind\n')
                return
            verts_arg = qs.get('vertices', [''])[0]
            try:
                verts = [int(v) for v in verts_arg.split(',') if v != '']
            except (ValueError, TypeError):
                verts = []
            if not verts:
                self._reply(400, 'text/plain', b'missing vertices\n')
                return
            try:
                payload = compute_normative_ring_stat(subjects_dir, metric, kind, verts, template=template)
            except Exception as exc:   # noqa: BLE001 — report, don't crash the server
                self._reply(500, 'text/plain', f'normative_ring error: {exc}\n'.encode('utf-8'))
                return
            if payload is None:
                self._reply(404, 'text/plain', b'no cohort data for metric\n')
                return
            self._reply(200, 'application/json', json.dumps(payload).encode('utf-8'))

        def _reply(self, code, ctype, data, cacheable=False):
            self.send_response(code)
            self.send_header('Content-Type',                ctype)
            self.send_header('Content-Length',              str(len(data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            if cacheable:
                # Safe to cache forever only because the URL carries a per-launch
                # cache-buster (see make_html) — otherwise a different subject on
                # the same port would reuse these bytes.
                self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
            else:
                # Dynamic responses (the HTML page, /mahal JSON): never cache, so
                # they can't leak across subjects sharing a port.
                self.send_header('Cache-Control', 'no-store')
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
    ap.add_argument('--killall', action='store_true',
                    help='Kill any other running cortical_browser.py instances and exit')
    args = ap.parse_args()

    if args.killall:
        kill_other_instances()
        sys.exit(0)

    subj_dir = os.path.join(args.subjects_dir, args.subj_id)
    if not os.path.isdir(subj_dir):
        sys.exit(f'Subject directory not found: {subj_dir}')

    vol_path, lh_path, rh_path = find_files(subj_dir)
    print(f'Subject  : {args.subj_id}')
    print(f'Volume   : {vol_path  or "NOT FOUND"}')
    print(f'LH surf  : {lh_path   or "NOT FOUND"}')
    print(f'RH surf  : {rh_path   or "NOT FOUND"}')

    tsf_metrics = find_tsf_metrics(subj_dir)   # prints its own per-metric finding report
    surf_types  = find_surface_types(args.subjects_dir, subj_dir)
    print(f'Surf types: {list(surf_types) or "none"}')

    streamline_files = find_streamline_files(subj_dir)
    print(f'Streamlines: {list(streamline_files) or "none"}')

    dwi_files = find_dwi_files(subj_dir)
    print(f'DWI space: {list(dwi_files) or "none"}')

    out_dir = tempfile.mkdtemp(prefix='cortical_browser_')
    # Materialized overlays/matrices live here for the session only; mkdtemp
    # doesn't self-clean, so remove it on any graceful exit (normal quit or the
    # Ctrl+C below). A hard kill (kill -9, crash) can't run this — the OS clears
    # /tmp on reboot in that case.
    atexit.register(shutil.rmtree, out_dir, ignore_errors=True)
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
    for p in streamline_files.values():
        file_map[f'/data/{os.path.basename(p)}'] = p
    for p in dwi_files.values():
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

    # Unique per launch (tempfile guarantees a fresh suffix), so every session's
    # /data/ URLs differ from any previous subject's on the same port.
    cache_bust = os.path.basename(out_dir)
    html, main_js = make_html(
        args.subj_id, vol_path, lh_path, rh_path,
        overlay_info, args.port, surf_types, normative_info,
        cache_bust=cache_bust, streamline_files=streamline_files,
        dwi_available=bool(dwi_files.get('fa')),
    )
    html_bytes    = html.encode('utf-8')
    main_js_bytes = main_js.encode('utf-8')
    dwi_html_bytes = dwi_js_bytes = None
    if dwi_files.get('fa'):
        dwi_html, dwi_js = make_dwi_html(args.subj_id, dwi_files, args.port, cache_bust=cache_bust)
        dwi_html_bytes = dwi_html.encode('utf-8')
        dwi_js_bytes   = dwi_js.encode('utf-8')

    server = HTTPServer(('localhost', args.port),
        make_handler(html_bytes, file_map, overlay_arrays, materialized, out_dir,
                      args.subjects_dir, normative_materialized, tsf_metrics=tsf_metrics,
                      dwi_html_bytes=dwi_html_bytes, main_js_bytes=main_js_bytes,
                      dwi_js_bytes=dwi_js_bytes))
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
