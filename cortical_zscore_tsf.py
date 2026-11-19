#!/usr/bin/env python3
"""
cortical_zscore_tsf.py — vertex- and depth-wise z-scores of one subject's
depth-wise and single-scalar-per-vertex metrics against the precomputed
normative dataset.

For every metric in the normative HDF5 (templates/normative/{TEMPLATE}_multivariate.h5,
built by cortical_create_normative_data_from_tsf.py) and each hemisphere, finds
whichever of the two file conventions that metric actually uses under the
subject's directory and writes, next to it (metrics are labelled
<folder>/<name>, folder = the full path from the subject directory down, e.g.
dwi/dti/fa vs dwi/dki/fa):

  Depth-wise:  <folder>/{hemi}_{TEMPLATE}_<name>.tsf ->
    {hemi}_{TEMPLATE}_<name>_zscore.tsf            z per streamline point
    {hemi}_{TEMPLATE}_<name>_zscore_absmean.func.gii   mean |z| over each vertex's streamline
    {hemi}_{TEMPLATE}_<name>_zscore_abssum.func.gii    sum  |z| over each vertex's streamline

  Single-scalar-per-vertex (curv/sulc/thickness):
  <folder>/{hemi}.<name>.{TEMPLATE}.func.gii ->
    {hemi}.<name>.{TEMPLATE}_zscore.func.gii       z per vertex (no depth axis,
                                                    so no absmean/abssum — the
                                                    z-score IS already the
                                                    per-vertex summary)

z = (x - mean) / std across control subjects (sample std, ddof=1), computed per
vertex (and per depth index, for depth-wise metrics). A point/vertex is
invalid, when the subject value is missing (-1 for a depth-wise point, the
sentinel the rest of the pipeline masks to NaN; non-finite for a scalar),
fewer than MIN_N controls have a value there, or the control std is 0.
Invalid points are excluded from the mean |z|; a vertex with no valid points
gets NaN in the giftis.

Runs for every subject, including those in subjects_to_average.txt — a
cohort subject's own value is part of the mean/std it's compared against, so
its z-scores are biased toward 0 (not a true held-out deviation), but they
are still computed, as a sanity check that the normative stats behave as
expected on the data that built them.

--adjust-for COL additionally writes a covariate-adjusted z-score next to
each plain one above (never in place of it): {..}_zscore_adj-{COL}.tsf /
_absmean / _abssum .func.gii, or {..}_zscore_adj-{COL}.func.gii for a scalar
metric. This is now GATED on a real group-level significance test, not just a
per-vertex OLS computed on the fly: cortical_glm_covariate.py must already
have been run for COL (it fits a BrainStat SLM, metric ~ COL, both
hemispheres combined into one bilateral mesh, smoothed, FDR+RFT corrected,
and writes slope/intercept/resid-sd/p-rft — among other stats — as .func.gii
under templates/normative/glm/). At each vertex/depth where that fit's RFT
CLUSTER-corrected p-value is below --rft-threshold (default 0.05), the
subject is compared to THAT fit's predicted value (intercept + slope *
subject's own COL) and residual SD instead of the cohort's raw mean/SD —
z = (x - predicted) / residual_SD — so a systematic, statistically real
relationship between the metric and the covariate across controls doesn't by
itself show up as deviation. Everywhere else (not significant, or outside the
cortex mask) it's simply not adjusted: identical to the plain z-score there.
COL's values for the TARGET subject come from --covariates, a TSV/CSV with
one row per subject (default: <subjects_dir>/bids/participants.tsv, else
<subjects_dir>/templates/covariates.tsv), matched by exact string equality
against the subject-ID column (--covariate-id-col, default participant_id);
the target subject itself MUST have a value for COL or the run errors out,
since there's nothing to predict from otherwise. --glm-stats-dir points at
cortical_glm_covariate.py's output (default: <subjects_dir>/templates/
normative/glm) — missing stats for any metric being adjusted is a hard error,
not a silent skip, since there's no principled unadjusted/adjusted fallback
other than the one the significance test itself already encodes.

Usage:
    python cortical_zscore_tsf.py <subjid> [subjects_dir] [--min-n 4]
    python cortical_zscore_tsf.py <subjid> [subjects_dir] --tsf FILE [FILE ...]
    python cortical_zscore_tsf.py <subjid> [subjects_dir] --gii FILE [FILE ...]
    python cortical_zscore_tsf.py <subjid> [subjects_dir] --adjust-for age_scan [--covariates FILE]
    python cortical_zscore_tsf.py --stats-only [subjects_dir] [--adjust-for age_scan]

--tsf/--gii each process exactly the given files (used by their own Snakemake
rule) instead of searching the subject's directory; either or both may be
given together. --stats-only just builds/refreshes the normative stats cache
(plain, and the fast per-vertex-OLS --adjust-for one too if given — that one
is now used only by cortical_var_explorer.py's interactive exploration, NOT
by the production --adjust-for path above) and exits (also used by the
Snakemake rule, so the cache is built once rather than raced for by parallel
subject jobs).
"""
import os, sys, glob, argparse, warnings, re, hashlib
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import h5py
import nibabel as nib
from scipy import stats as scipy_stats   # only used by _block_stats_adj, for the slope's p-value

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cortical_browser'))
from cortical_io import (read_mrtrix_tsf, write_mrtrix_tsf, pad_to_matrix, find_tsf, metric_label,
                          find_scalar_gii, scalar_gii_label, read_gifti_scalar, read_covariates,
                          default_covariates_path)
from cortical_browser_config import TEMPLATE

MIN_N = 4
RFT_THRESHOLD_DEFAULT = 0.05


def _sanitize_label(name):
    """Filesystem/CLI-safe form of a covariate column name, for an output
    filename or cache path (e.g. age_scan stays age_scan)."""
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', name)


def _sanitize_metric(metric):
    """Matches cortical_glm_covariate.py's own sanitize() exactly — that
    script, not this one, is what actually names the GLM stat files this
    reads, so the two must agree. A one-line duplicate rather than an import,
    so plain (non-adjusted) z-scoring never has to import brainstat."""
    return metric.replace('/', '_')


def zscore_tracks(tracks, mu, sd, n, min_n=MIN_N):
    """z-score a list of per-vertex arrays against (nVerts, nDepths) mean/std/n.
    Returns (z_tracks with -1 for invalid, per-vertex mean |z|, per-vertex sum |z|);
    the per-vertex values are NaN where a vertex has no valid points."""
    lens = np.array([len(t) for t in tracks])
    L = int(lens.max()) if len(lens) else 0
    D = mu.shape[1]
    X = pad_to_matrix(tracks).astype(np.float64)        # (nVerts, L), NaN-padded
    # align normative stats to the subject's depth axis (extra depths -> invalid)
    def fit(A, fill):
        out = np.full((A.shape[0], L), fill, dtype=np.float64)
        k = min(L, D)
        out[:, :k] = A[:, :k]
        return out
    mu_, sd_, n_ = fit(mu, np.nan), fit(sd, np.nan), fit(n, 0)

    with np.errstate(all='ignore'):
        ok = (X != -1) & np.isfinite(X) & np.isfinite(mu_) & (n_ >= min_n) & (sd_ > 0)
        Z = np.where(ok, (X - mu_) / sd_, np.nan)
    absZ = np.abs(Z)
    n_ok = ok.sum(axis=1)
    abs_sum = np.where(n_ok > 0, np.nansum(absZ, axis=1), np.nan).astype(np.float32)
    abs_mean = np.where(n_ok > 0, abs_sum / np.maximum(n_ok, 1), np.nan).astype(np.float32)

    Zout = np.where(ok, Z, -1.0).astype(np.float32)
    z_tracks = [Zout[v, :lens[v]] for v in range(len(tracks))]
    return z_tracks, abs_mean, abs_sum


def zscore_scalar(x, mu, sd, n, min_n=MIN_N):
    """z-score one subject's single-scalar-per-vertex metric (curv/sulc/
    thickness) against cohort (mu, sd, n) — same validity rule as
    zscore_tracks (NaN where the subject value is missing/non-finite, fewer
    than min_n controls have a value there, or the control SD is 0), but
    there's only one value per vertex, no depth axis and no -1 point
    sentinel to encode (a gifti scalar is never -1-as-invalid the way an
    MRtrix track point is), so this returns a plain (nVerts,) float32 array
    with NaN for invalid vertices, and there's nothing to summarize across
    depth (no absmean/abssum — they'd just be |z| again)."""
    with np.errstate(all='ignore'):
        ok = np.isfinite(x) & np.isfinite(mu) & (n >= min_n) & (sd > 0)
        z = np.where(ok, (x - mu) / sd, np.nan)
    return z.astype(np.float32)


BLOCK = 5122   # vertices per HDF5 read (2 x the file's 2561-vertex chunk)


def _block_stats(h5_path, hemi, mi):
    """Control mean, sample SD (ddof=1) and n for one hemisphere/metric, read in
    vertex blocks so peak memory stays small. Runs in a worker process."""
    with h5py.File(h5_path, 'r') as h5f:
        d = h5f[f'{hemi}_M']
        mu = np.empty(d.shape[:2], dtype=np.float32)
        sd = np.empty_like(mu)
        n  = np.empty(d.shape[:2], dtype=np.int16)
        for v0 in range(0, d.shape[0], BLOCK):
            blk = d[v0:v0 + BLOCK, :, :, mi]                      # (nV, nDepths, nSubjects)
            valid = ~np.isnan(blk)
            cnt = valid.sum(axis=2)
            with np.errstate(all='ignore'):
                m = np.where(valid, blk, 0).sum(axis=2, dtype=np.float64) / cnt
                dev = np.where(valid, blk - m[..., None].astype(np.float32), 0)
                v = (dev.astype(np.float64) ** 2).sum(axis=2) / (cnt - 1)
            m[cnt == 0] = np.nan
            v[cnt < 2] = np.nan
            mu[v0:v0 + BLOCK], sd[v0:v0 + BLOCK], n[v0:v0 + BLOCK] = m, np.sqrt(v), cnt
    return hemi, mi, mu, sd, n


def _block_stats_adj(h5_path, hemi, mi, covariate):
    """Per-vertex/depth simple linear regression of one metric on a single
    continuous covariate across the control cohort (y = a + b*covariate + e),
    read in vertex blocks like _block_stats. Returns (hemi, mi, a, b,
    resid_sd, se_b, p, n) — a/resid_sd/n are the same (nVerts, nDepths) shape
    as _block_stats's (mu, sd, n), so a caller just feeds them to
    zscore_scalar/zscore_tracks in place of mu/sd/n: the "expected value"
    there becomes the covariate-predicted value a + b*covariate_of_this_subject
    rather than the cohort mean, and "SD" becomes the regression's residual
    SD. se_b (the slope's standard error) and p (two-sided p-value for H0:
    b=0, via a Student's t with n-2 df) are extra, for cortical_var_explorer.py
    — not used by the z-scoring path itself.

    A point is invalid (NaN a/b/resid_sd/se_b/p) wherever fewer than 3 cohort
    subjects have both a finite metric value AND a finite covariate value
    there, or the covariate has zero variance among them (b undefined); n
    (the count) is still reported either way, so a caller's own --min-n
    threshold (typically >= 3) still applies on top of this as usual.
    Runs in a worker process, same as _block_stats."""
    c = covariate.astype(np.float64)
    c_ok = np.isfinite(c)
    with h5py.File(h5_path, 'r') as h5f:
        d = h5f[f'{hemi}_M']
        shape2 = d.shape[:2]
        a   = np.empty(shape2, dtype=np.float32)
        b   = np.empty(shape2, dtype=np.float32)
        rs  = np.empty(shape2, dtype=np.float32)
        se  = np.empty(shape2, dtype=np.float32)
        pv  = np.empty(shape2, dtype=np.float32)
        n   = np.empty(shape2, dtype=np.int16)
        for v0 in range(0, d.shape[0], BLOCK):
            blk = d[v0:v0 + BLOCK, :, :, mi].astype(np.float64)   # (nV, nDepths, nSubjects)
            valid = np.isfinite(blk) & c_ok[None, None, :]
            cnt = valid.sum(axis=2)
            cm = np.where(valid, c[None, None, :], 0.0)
            ym = np.where(valid, blk, 0.0)
            with np.errstate(all='ignore'):
                sum_c, sum_y = cm.sum(axis=2), ym.sum(axis=2)
                sum_cc = (cm ** 2).sum(axis=2)
                sum_cy = (cm * ym).sum(axis=2)
                sum_yy = (ym ** 2).sum(axis=2)
                mean_c, mean_y = sum_c / cnt, sum_y / cnt
                Sxx = sum_cc - cnt * mean_c ** 2
                Sxy = sum_cy - cnt * mean_c * mean_y
                Syy = sum_yy - cnt * mean_y ** 2
                bb = Sxy / Sxx
                aa = mean_y - bb * mean_c
                resid_var = (Syy - bb * Sxy) / (cnt - 2)
                se_b = np.sqrt(resid_var / Sxx)
                tstat = bb / se_b
                df = np.clip(cnt - 2, 1, None)   # clipped only to keep t.sf finite; masked out by `bad` below anyway
                pval = 2 * scipy_stats.t.sf(np.abs(tstat), df=df)
            bad = (cnt < 3) | ~(Sxx > 0)
            aa = np.where(bad, np.nan, aa)
            bb = np.where(bad, np.nan, bb)
            resid_var = np.where(bad, np.nan, np.clip(resid_var, 0, None))
            se_b = np.where(bad, np.nan, se_b)
            pval = np.where(bad, np.nan, pval)
            a[v0:v0 + BLOCK], b[v0:v0 + BLOCK] = aa, bb
            rs[v0:v0 + BLOCK], n[v0:v0 + BLOCK] = np.sqrt(resid_var), cnt
            se[v0:v0 + BLOCK], pv[v0:v0 + BLOCK] = se_b, pval
    return hemi, mi, a, b, rs, se, pv, n


def load_normative_stats(h5_path, metrics, use_cache=True, workers=4, needed=None):
    """{(hemi, metric_index): (mu, sd, n)} for the whole normative file.

    Cached in <h5 stem>_normative_stats.npz beside the HDF5 (keyed on its size and
    mtime, so it is rebuilt if the normative data changes); the HDF5 itself is
    never modified. Without a valid cache the stats are computed in parallel,
    which is the slow part of a run (gzip decompression of the full stack).
    `needed` (set of (hemi, metric_index)) limits what is read from a valid cache."""
    st = os.stat(h5_path)
    key = np.array([st.st_size, st.st_mtime_ns], dtype=np.int64)
    cache = h5_path[:-len('.h5')] + '_normative_stats.npz'
    if use_cache and os.path.isfile(cache):
        try:
            z = np.load(cache)
            if np.array_equal(z['key'], key) and int(z['n_metrics']) == len(metrics):
                print(f'Using cached normative stats: {cache}')
                return {(h, i): (z[f'{h}_{i}_mu'], z[f'{h}_{i}_sd'], z[f'{h}_{i}_n'])
                        for h in ('lh', 'rh') for i in range(len(metrics))
                        if needed is None or (h, i) in needed}
        except Exception as e:
            print(f'  cache unreadable ({e}); recomputing')
    print(f'Computing normative mean/SD/n ({2 * len(metrics)} hemisphere-metric stacks, {workers} workers) …')
    jobs = [(h, i) for h in ('lh', 'rh') for i in range(len(metrics))]
    stats = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_block_stats, h5_path, h, i) for h, i in jobs]
        for fu in futs:
            h, i, mu, sd, n = fu.result()
            stats[(h, i)] = (mu, sd, n)
            print(f'  {h} {metrics[i]} done')
    if use_cache:
        try:
            out = {'key': key, 'n_metrics': np.array(len(metrics))}
            for (h, i), (mu, sd, n) in stats.items():
                out[f'{h}_{i}_mu'], out[f'{h}_{i}_sd'], out[f'{h}_{i}_n'] = mu, sd, n
            tmp = cache[:-len('.npz')] + f'.{os.getpid()}.tmp.npz'   # atomic: no reader sees a partial file
            np.savez(tmp, **out)
            os.replace(tmp, cache)
            print(f'Cached normative stats: {cache}')
        except OSError as e:
            print(f'  [warn] could not write cache ({e}); continuing without it')
    return stats


ADJ_STATS_SCHEMA = 2   # bump whenever the set of arrays in the adj cache changes (see below)


def load_normative_stats_adj(h5_path, metrics, covariate, covariate_label, use_cache=True, workers=4, needed=None):
    """{(hemi, metric_index): (a, b, resid_sd, se_b, p, n)} — same role as
    load_normative_stats, but for the covariate-adjusted regression stats
    from _block_stats_adj instead of the plain per-point mean/SD/n. se_b and
    p (two-sided, for H0: slope==0) are included for cortical_var_explorer.py;
    the z-scoring path itself (cortical_zscore_tsf.py's main()) only uses
    a/resid_sd/n.

    Cached separately, in <h5 stem>_normative_stats_adj-<covariate_label>.npz,
    keyed on the HDF5's (size, mtime) same as load_normative_stats, PLUS a
    hash of the actual covariate values used (so an edited participants.tsv,
    or a different file supplying the same column name, invalidates it
    rather than silently reusing a stale regression) AND ADJ_STATS_SCHEMA
    (so a cache from before se_b/p existed is rebuilt instead of raising a
    KeyError the first time something asks for them). The original,
    unsanitized covariate_label is also stored (as 'covariate_label'), so a
    reader can recover the exact participants.tsv column name from the file
    alone even though the filename itself uses the sanitized tag."""
    covariate = np.asarray(covariate, dtype=np.float64)
    st = os.stat(h5_path)
    key = np.array([st.st_size, st.st_mtime_ns], dtype=np.int64)
    cov_key = hashlib.sha1(np.ascontiguousarray(covariate).tobytes()).hexdigest()
    cache = h5_path[:-len('.h5')] + f'_normative_stats_adj-{_sanitize_label(covariate_label)}.npz'
    if use_cache and os.path.isfile(cache):
        try:
            z = np.load(cache)
            if (np.array_equal(z['key'], key) and int(z['n_metrics']) == len(metrics)
                    and str(z['cov_key']) == cov_key
                    and 'schema' in z.files and int(z['schema']) == ADJ_STATS_SCHEMA):
                print(f'Using cached adjusted ({covariate_label}) normative stats: {cache}')
                return {(h, i): (z[f'{h}_{i}_a'], z[f'{h}_{i}_b'], z[f'{h}_{i}_rs'],
                                  z[f'{h}_{i}_se'], z[f'{h}_{i}_p'], z[f'{h}_{i}_n'])
                        for h in ('lh', 'rh') for i in range(len(metrics))
                        if needed is None or (h, i) in needed}
        except Exception as e:
            print(f'  cache unreadable ({e}); recomputing')
    print(f'Computing covariate-adjusted ({covariate_label}) normative regression stats '
          f'({2 * len(metrics)} hemisphere-metric stacks, {workers} workers) …')
    jobs = [(h, i) for h in ('lh', 'rh') for i in range(len(metrics))]
    stats = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_block_stats_adj, h5_path, h, i, covariate) for h, i in jobs]
        for fu in futs:
            h, i, a, b, rs, se, p, n = fu.result()
            stats[(h, i)] = (a, b, rs, se, p, n)
            print(f'  {h} {metrics[i]} done')
    if use_cache:
        try:
            out = {'key': key, 'n_metrics': np.array(len(metrics)), 'cov_key': np.array(cov_key),
                   'schema': np.array(ADJ_STATS_SCHEMA), 'covariate_label': np.array(covariate_label)}
            for (h, i), (a, b, rs, se, p, n) in stats.items():
                out[f'{h}_{i}_a'], out[f'{h}_{i}_b'], out[f'{h}_{i}_rs'] = a, b, rs
                out[f'{h}_{i}_se'], out[f'{h}_{i}_p'], out[f'{h}_{i}_n'] = se, p, n
            tmp = cache[:-len('.npz')] + f'.{os.getpid()}.tmp.npz'
            np.savez(tmp, **out)
            os.replace(tmp, cache)
            print(f'Cached adjusted normative stats: {cache}')
        except OSError as e:
            print(f'  [warn] could not write cache ({e}); continuing without it')
    return stats


GLM_STATS_NEEDED = {'slope': 'slope', 'intercept': 'intercept', 'resid-sd': 'resid_sd', 'p-rft': 'p_rft'}


def load_glm_stats(glm_dir, metrics, cov_col, template, needed, subjects_dir, normative_stats):
    """{(hemi, metric_index): {'slope':, 'intercept':, 'resid_sd':, 'p_rft':}}
    (each (nVerts, nDepths), one column per depth, nDepths taken from
    normative_stats[(hemi, mi)] -- the SAME depth axis zscore_scalar/
    zscore_tracks already index pred/resid_sd by) -- read straight from
    cortical_glm_covariate.py's .func.gii outputs under glm_dir (default
    <subjects_dir>/templates/normative/glm), no cache of our own: those
    GIFTIs ARE the cache (a Snakemake output, rebuilt only when that rule's
    own inputs change).

    cortical_glm_covariate.py skips (writes no darray for) a depth it
    couldn't fit (too few subjects/mesh edges too sparse -- see its own
    fit_one() docstring), so a metric's GIFTI can have FEWER darrays than
    this metric's real depth count, and -- since depths are written in
    ascending order but with gaps -- darray index i is NOT reliably depth i.
    Each darray's own 'Name' metadata ('depthNN', written by
    save_stat_giftis_combined) says which depth it actually is; this
    reads that back and scatters each darray into its real column of a
    full-nDepths-sized array, leaving any skipped depth's column at the
    sentinel 'no group-level fit here' value (p_rft=1.0, so always
    >= --rft-threshold -- same as a fit that came back genuinely
    not-significant; slope/intercept/resid_sd=0.0, never read since `sig`
    is False there). Getting this wrong previously produced a silent
    misalignment (darray i treated as depth i) or, once nDepths also
    differed, a hard shape-mismatch crash in main()'s
    `g['intercept'] + g['slope'] * c_subj`.

    Hard-errors (sys.exit) if any needed (hemi, metric_index)'s file is
    missing — see this module's own --adjust-for docstring for why there's
    no silent-skip fallback here, unlike the plain per-vertex OLS cache this
    replaces for production z-scoring."""
    stats = {}
    for hemi, mi in sorted(needed):
        metric = metrics[mi]
        base = f'{_sanitize_metric(metric)}_{cov_col}'
        n_depths_full = normative_stats[(hemi, mi)][0].shape[1]   # mu's own depth axis
        arrs = {}
        for stat, key in GLM_STATS_NEEDED.items():
            path = os.path.join(glm_dir, f'{hemi}.{base}_{stat}.{template}.func.gii')
            if not os.path.isfile(path):
                sys.exit(f"--adjust-for {cov_col}: missing GLM stats file for metric '{metric}': {path}\n"
                         f"Run cortical_glm_covariate.py {subjects_dir} --covariate {cov_col} first "
                         f"(see this script's own --adjust-for docstring).")
            img = nib.load(path)
            n_verts = img.darrays[0].data.shape[0]
            fill = 1.0 if key == 'p_rft' else 0.0
            full = np.full((n_verts, n_depths_full), fill, dtype=np.float32)
            for da in img.darrays:
                name = dict(da.meta).get('Name', '')
                if not name.startswith('depth') or not name[len('depth'):].isdigit():
                    sys.exit(f"{path}: darray missing/malformed 'Name' metadata ({name!r}); "
                             f"expected 'depthNN' (written by cortical_glm_covariate.py)")
                depth = int(name[len('depth'):])
                if depth >= n_depths_full:
                    sys.exit(f"{path}: darray Name={name!r} (depth {depth}) is out of range for this "
                             f"metric's {n_depths_full} depths -- stale GLM output? re-run "
                             f"cortical_glm_covariate.py.")
                full[:, depth] = da.data.astype(np.float32)
            arrs[key] = full
        stats[(hemi, mi)] = arrs
    return stats


def write_gifti(path, values):
    da = nib.gifti.GiftiDataArray(values.astype(np.float32), intent='NIFTI_INTENT_ESTIMATE',
                                  datatype='NIFTI_TYPE_FLOAT32')
    nib.save(nib.gifti.GiftiImage(darrays=[da]), path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('subjid', nargs='?')
    ap.add_argument('subjects_dir', nargs='?', default=os.environ.get('SUBJECTS_DIR'))
    ap.add_argument('--tsf', nargs='+', metavar='FILE', help='z-score exactly these .tsf files instead of searching the subject dir')
    ap.add_argument('--gii', nargs='+', metavar='FILE', help='z-score exactly these single-scalar-per-vertex .func.gii files (curv/sulc/thickness) instead of searching the subject dir')
    ap.add_argument('--stats-only', action='store_true', help='only build/refresh the normative stats cache, then exit')
    ap.add_argument('--no-cache', action='store_true', help='do not read/write the normative stats cache')
    ap.add_argument('--workers', type=int, default=4, help='processes for computing normative stats (default 4)')
    ap.add_argument('--min-n', type=int, default=MIN_N, help='minimum controls with a valid value (default 4)')
    ap.add_argument('--adjust-for', metavar='COL', help='also compute a covariate-adjusted z-score for this '
                     'column (e.g. age_scan), gated on cortical_glm_covariate.py\'s own group-level significance '
                     'test (see this script\'s own --adjust-for docstring). Written alongside the plain z-score '
                     'files, never in place of them.')
    ap.add_argument('--covariates', metavar='FILE', help='TSV/CSV participants table for --adjust-for, with one '
                     'row per subject (default: <subjects_dir>/bids/participants.tsv, else '
                     '<subjects_dir>/templates/covariates.tsv)')
    ap.add_argument('--covariate-id-col', default='participant_id', metavar='COL',
                     help="subject-ID column in --covariates (default: participant_id)")
    ap.add_argument('--glm-stats-dir', metavar='DIR', help='cortical_glm_covariate.py output for --adjust-for '
                     '(default: <subjects_dir>/templates/normative/glm)')
    ap.add_argument('--rft-threshold', type=float, default=RFT_THRESHOLD_DEFAULT,
                     help=f'--adjust-for only applies where the GLM fit\'s RFT cluster-corrected p-value is below '
                     f'this (default {RFT_THRESHOLD_DEFAULT})')
    args = ap.parse_args()
    if args.stats_only and args.subjid and args.subjects_dir == os.environ.get('SUBJECTS_DIR'):
        args.subjects_dir, args.subjid = args.subjid, None   # lone positional = subjects_dir
    if not args.subjects_dir:
        sys.exit('subjects_dir not given and SUBJECTS_DIR is not set')
    if not args.stats_only and not args.subjid:
        ap.error('subjid is required (unless --stats-only)')

    h5_path = os.path.join(args.subjects_dir, 'templates', 'normative', f'{TEMPLATE}_multivariate.h5')
    if not os.path.isfile(h5_path):
        sys.exit(f'Normative data not found: {h5_path}')

    if not args.stats_only:
        subj_dir = os.path.join(args.subjects_dir, args.subjid)
        if not os.path.isdir(subj_dir):
            sys.exit(f'Subject directory not found: {subj_dir}')
        print(f'Subject : {args.subjid} ({subj_dir})')

    print(f'Loading normative data: {h5_path}')
    with h5py.File(h5_path, 'r') as h5f:
        metrics = [m.decode() if isinstance(m, bytes) else m for m in h5f['metrics'][:]]
        norm_subjects = [x.decode() if isinstance(x, bytes) else x for x in h5f['subjects'][:]]
        print(f'Normative data loaded: template {h5f.attrs.get("template", "?")}, '
              f'{len(norm_subjects)} subjects, {len(metrics)} metrics ({", ".join(metrics)})')
        for hemi in ('lh', 'rh'):
            print(f'  {hemi}_M shape (nVerts, nDepths, nSubjects, nMetrics): {h5f[f"{hemi}_M"].shape}')
        print(f'Minimum controls per point: {args.min_n}')
        old = [m for m in metrics if '/' not in m]
        if old:
            sys.exit(f'Normative file uses unqualified metric names ({", ".join(old)}); it predates <folder>/<name> labels. '
                     f'Rebuild it with cortical_create_normative_data_from_tsf.py.')

    # Covariate adjustment (--adjust-for): load the participants table once,
    # align one column to norm_subjects' order (NaN for any cohort subject
    # missing a value), and sanity-check it has enough coverage to regress
    # on before doing any of the expensive per-vertex work below.
    covariate = cov_col = covariates_path = cov_table = None
    if args.adjust_for:
        cov_col = args.adjust_for
        covariates_path = args.covariates or default_covariates_path(args.subjects_dir)
        if not covariates_path or not os.path.isfile(covariates_path):
            sys.exit(f'--adjust-for {cov_col}: no --covariates file given, and neither default '
                      f'location exists ({args.subjects_dir}/bids/participants.tsv, '
                      f'{args.subjects_dir}/templates/covariates.tsv)')
        cov_table = read_covariates(covariates_path, id_col=args.covariate_id_col)
        if not cov_table:
            sys.exit(f'{covariates_path}: no rows (check --covariate-id-col {args.covariate_id_col!r})')
        sample_cols = next(iter(cov_table.values()))
        if cov_col not in sample_cols:
            sys.exit(f"{covariates_path}: no column '{cov_col}' (found: {', '.join(sample_cols)})")
        covariate = np.full(len(norm_subjects), np.nan, dtype=np.float64)
        for i, s in enumerate(norm_subjects):
            v = cov_table.get(s, {}).get(cov_col, float('nan'))
            if isinstance(v, str):
                sys.exit(f"--adjust-for {cov_col}: non-numeric value '{v}' for subject '{s}' in "
                          f"{covariates_path} (only a continuous covariate is supported)")
            covariate[i] = v
        n_have = int(np.isfinite(covariate).sum())
        print(f'Covariate   : {cov_col!r} from {covariates_path} '
              f'({n_have}/{len(norm_subjects)} cohort subjects have a value)')
        if n_have < 3:
            sys.exit(f'--adjust-for {cov_col}: only {n_have}/{len(norm_subjects)} cohort subjects have a '
                      f'value for it; need at least 3 to fit a regression')

    if args.stats_only:
        load_normative_stats(h5_path, metrics, use_cache=True, workers=args.workers)
        if covariate is not None:
            load_normative_stats_adj(h5_path, metrics, covariate, cov_col, use_cache=True, workers=args.workers)
        return

    c_subj = None
    if covariate is not None:
        if args.subjid not in cov_table:
            sys.exit(f"--adjust-for {cov_col}: subject '{args.subjid}' not found in {covariates_path} "
                      f"(id column {args.covariate_id_col!r})")
        c_subj = cov_table[args.subjid].get(cov_col, float('nan'))
        if isinstance(c_subj, str) or not np.isfinite(c_subj):
            sys.exit(f"--adjust-for {cov_col}: subject '{args.subjid}' has a missing/non-numeric value "
                      f"({c_subj!r}) for it in {covariates_path}")

    # (hemi, metric) -> (path, is_scalar): explicit --tsf/--gii files, else a
    # search of the subject dir trying both file conventions per metric —
    # depth-wise .tsf (find_tsf) and single-scalar-per-vertex .func.gii
    # (find_scalar_gii, e.g. curv/sulc/thickness) — whichever actually exists.
    files = {}
    if args.tsf or args.gii:
        for path in (args.tsf or []):
            for hemi in ('lh', 'rh'):
                if os.path.basename(path).startswith(f'{hemi}_{TEMPLATE}_'):
                    if os.path.basename(path).endswith('_zscore.tsf'):
                        sys.exit(f'{path} is itself a z-score file')
                    files[(hemi, metric_label(path, hemi, TEMPLATE, subj_dir))] = (path, False)
                    break
            else:
                sys.exit(f'Cannot parse hemisphere from {os.path.basename(path)} (expected lh|rh_{TEMPLATE}_<name>.tsf)')
        for path in (args.gii or []):
            for hemi in ('lh', 'rh'):
                if os.path.basename(path).startswith(f'{hemi}.'):
                    if os.path.basename(path).endswith(f'_zscore.{TEMPLATE}.func.gii'):
                        sys.exit(f'{path} is itself a z-score file')
                    files[(hemi, scalar_gii_label(path, hemi, TEMPLATE, subj_dir))] = (path, True)
                    break
            else:
                sys.exit(f'Cannot parse hemisphere from {os.path.basename(path)} (expected lh|rh.<name>.{TEMPLATE}.func.gii)')
    else:
        for hemi in ('lh', 'rh'):
            for metric in metrics:
                hits = find_tsf(subj_dir, hemi, TEMPLATE, metric)
                if hits:
                    if len(hits) > 1:
                        print(f'  [warn] {hemi} {metric}: {len(hits)} files found, using {hits[0]}')
                    files[(hemi, metric)] = (hits[0], False)
                    continue
                hits = find_scalar_gii(subj_dir, hemi, TEMPLATE, metric)
                if hits:
                    files[(hemi, metric)] = (hits[0], True)
                    continue
                print(f'  [skip] {hemi} {metric}: no such .tsf or .func.gii under {subj_dir}')

    todo = []
    for (hemi, metric), (path, is_scalar) in files.items():
        if metric in metrics:
            todo.append((hemi, metric, path, is_scalar))
        else:
            print(f'  [skip] {hemi} {metric}: not in the normative data')
    needed = {(h, metrics.index(m)) for h, m, _, _ in todo}
    stats = load_normative_stats(h5_path, metrics, use_cache=not args.no_cache, workers=args.workers, needed=needed)
    glm_stats = None
    if covariate is not None:
        glm_dir = args.glm_stats_dir or os.path.join(args.subjects_dir, 'templates', 'normative', 'glm')
        glm_stats = load_glm_stats(glm_dir, metrics, cov_col, TEMPLATE, needed, args.subjects_dir, stats)
    tag = _sanitize_label(cov_col) if cov_col else None

    for hemi, metric, path, is_scalar in todo:
        mu, sd, n = stats[(hemi, metrics.index(metric))]
        # Covariate-adjusted "mu"/"sd": cortical_glm_covariate.py's own
        # smoothed, group-level predicted value for THIS subject's own
        # covariate (intercept + slope*c_subj) and residual SD, in place of
        # the cohort mean/SD — but ONLY where that fit's RFT cluster-corrected
        # p-value says the covariate effect there is real; everywhere else
        # (not significant, or outside the cortex mask — p_rft is 1.0 there,
        # always >= threshold) pred/resid_sd just fall back to the plain
        # mu/sd, i.e. "not adjusted". zscore_scalar/zscore_tracks don't care
        # which they're given either way — same validity rule (finite
        # expected value, n >= min_n, SD > 0) as always.
        pred = resid_sd = None
        if glm_stats is not None:
            g = glm_stats[(hemi, metrics.index(metric))]
            sig = g['p_rft'] < args.rft_threshold
            pred = np.where(sig, g['intercept'] + g['slope'] * c_subj, mu)
            resid_sd = np.where(sig, g['resid_sd'], sd)

        if is_scalar:
            # Every depth column of (mu, sd, n) is identical for a scalar
            # metric (see build_normative_stack's broadcast) — column 0 is
            # as good as any.
            x = read_gifti_scalar(path)
            if mu.shape[0] != x.shape[0]:
                print(f'  [skip] {hemi} {metric}: {x.shape[0]} vertices vs {mu.shape[0]} normative vertices')
                continue
            z = zscore_scalar(x, mu[:, 0], sd[:, 0], n[:, 0], args.min_n)
            out_path = path[:-len('.func.gii')] + '_zscore.func.gii'
            write_gifti(out_path, z)
            print(f'  {hemi} {metric}: wrote {os.path.basename(out_path)} '
                  f'(z computed for {np.isfinite(z).sum()}/{len(z)} vertices)')
            if pred is not None:
                z_adj = zscore_scalar(x, pred[:, 0], resid_sd[:, 0], n[:, 0], args.min_n)
                out_adj = path[:-len('.func.gii')] + f'_zscore_adj-{tag}.func.gii'
                write_gifti(out_adj, z_adj)
                print(f'  {hemi} {metric}: wrote {os.path.basename(out_adj)} (adjusted for {cov_col}; '
                      f'z computed for {np.isfinite(z_adj).sum()}/{len(z_adj)} vertices)')
            continue

        _, tracks = read_mrtrix_tsf(path)
        if mu.shape[0] != len(tracks):
            print(f'  [skip] {hemi} {metric}: {len(tracks)} streamlines vs {mu.shape[0]} normative vertices')
            continue
        if max(len(t) for t in tracks) > mu.shape[1]:
            print(f'  [warn] {hemi} {metric}: subject has streamlines deeper than normative data; extra points set to -1')
        z_tracks, abs_mean, abs_sum = zscore_tracks(tracks, mu, sd, n, args.min_n)

        base = path[:-len('.tsf')]
        write_mrtrix_tsf(base + '_zscore.tsf', z_tracks, template_path=path)
        write_gifti(base + '_zscore_absmean.func.gii', abs_mean)
        write_gifti(base + '_zscore_abssum.func.gii', abs_sum)
        print(f'  {hemi} {metric}: wrote {os.path.basename(base)}_zscore.tsf / _absmean / _abssum .func.gii '
              f'(mean|z| over {np.isfinite(abs_mean).sum()}/{len(abs_mean)} vertices)')

        if pred is not None:
            z_tracks_adj, abs_mean_adj, abs_sum_adj = zscore_tracks(tracks, pred, resid_sd, n, args.min_n)
            write_mrtrix_tsf(f'{base}_zscore_adj-{tag}.tsf', z_tracks_adj, template_path=path)
            write_gifti(f'{base}_zscore_adj-{tag}_absmean.func.gii', abs_mean_adj)
            write_gifti(f'{base}_zscore_adj-{tag}_abssum.func.gii', abs_sum_adj)
            print(f'  {hemi} {metric}: wrote {os.path.basename(base)}_zscore_adj-{tag}.tsf / _absmean / _abssum '
                  f'.func.gii (adjusted for {cov_col}; mean|z| over '
                  f'{np.isfinite(abs_mean_adj).sum()}/{len(abs_mean_adj)} vertices)')


if __name__ == '__main__':
    main()
