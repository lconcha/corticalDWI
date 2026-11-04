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

Usage:
    python cortical_zscore_tsf.py <subjid> [subjects_dir] [--min-n 4]
    python cortical_zscore_tsf.py <subjid> [subjects_dir] --tsf FILE [FILE ...]
    python cortical_zscore_tsf.py <subjid> [subjects_dir] --gii FILE [FILE ...]
    python cortical_zscore_tsf.py --stats-only [subjects_dir]

--tsf/--gii each process exactly the given files (used by their own Snakemake
rule) instead of searching the subject's directory; either or both may be
given together. --stats-only just builds/refreshes the normative stats cache
and exits (also used by the Snakemake rule, so the cache is built once rather
than raced for by parallel subject jobs).
"""
import os, sys, glob, argparse, warnings
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import h5py
import nibabel as nib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cortical_browser'))
from cortical_io import (read_mrtrix_tsf, write_mrtrix_tsf, pad_to_matrix, find_tsf, metric_label,
                          find_scalar_gii, scalar_gii_label, read_gifti_scalar)
from cortical_browser_config import TEMPLATE

MIN_N = 4


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


def load_normative_stats(h5_path, metrics, use_cache=True, workers=4, needed=None):
    """{(hemi, metric_index): (mu, sd, n)} for the whole normative file.

    Cached in <h5 stem>_zscore_stats.npz beside the HDF5 (keyed on its size and
    mtime, so it is rebuilt if the normative data changes); the HDF5 itself is
    never modified. Without a valid cache the stats are computed in parallel,
    which is the slow part of a run (gzip decompression of the full stack).
    `needed` (set of (hemi, metric_index)) limits what is read from a valid cache."""
    st = os.stat(h5_path)
    key = np.array([st.st_size, st.st_mtime_ns], dtype=np.int64)
    cache = h5_path[:-len('.h5')] + '_zscore_stats.npz'
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

    if args.stats_only:
        load_normative_stats(h5_path, metrics, use_cache=True, workers=args.workers)
        return

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

    for hemi, metric, path, is_scalar in todo:
        mu, sd, n = stats[(hemi, metrics.index(metric))]

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


if __name__ == '__main__':
    main()
