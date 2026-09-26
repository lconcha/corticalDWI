#!/usr/bin/env python3
"""
cortical_zscore_tsf.py — vertex- and depth-wise z-scores of one subject's
.tsf files against the precomputed normative dataset.

For every metric in the normative HDF5 (templates/normative/{TEMPLATE}_multivariate.h5,
built by cortical_create_normative_data_from_tsf.py) and each hemisphere, finds
{hemi}_{TEMPLATE}_<metric>.tsf under the subject's directory and writes, next to it:

    {hemi}_{TEMPLATE}_<metric>_zscore.tsf            z per streamline point
    {hemi}_{TEMPLATE}_<metric>_zscore_absmean.func.gii   mean |z| over each vertex's streamline
    {hemi}_{TEMPLATE}_<metric>_zscore_abssum.func.gii    sum  |z| over each vertex's streamline

z = (x - mean) / std across control subjects (sample std, ddof=1), computed per
vertex and per depth index. A point is invalid, and written as -1 (the
sentinel the rest of the pipeline masks to NaN), when the subject value is
missing (-1), fewer than MIN_N controls have a value there, or the control std
is 0. Invalid points are excluded from the mean |z|; a vertex with no valid
points gets NaN in the giftis.

The subject must NOT be in subjects_to_average.txt (the normative data is
left untouched, so it would be compared against itself).

Usage:
    python cortical_zscore_tsf.py <subjid> [subjects_dir] [--min-n 4]
"""
import os, sys, glob, argparse, warnings
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import h5py
import nibabel as nib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cortical_browser'))
from cortical_io import read_mrtrix_tsf, write_mrtrix_tsf, pad_to_matrix
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


def load_normative_stats(h5_path, metrics, use_cache=True, workers=4):
    """{(hemi, metric_index): (mu, sd, n)} for the whole normative file.

    Cached in <h5 stem>_zscore_stats.npz beside the HDF5 (keyed on its size and
    mtime, so it is rebuilt if the normative data changes); the HDF5 itself is
    never modified. Without a valid cache the stats are computed in parallel,
    which is the slow part of a run (gzip decompression of the full stack)."""
    st = os.stat(h5_path)
    key = np.array([st.st_size, st.st_mtime_ns], dtype=np.int64)
    cache = h5_path[:-len('.h5')] + '_zscore_stats.npz'
    if use_cache and os.path.isfile(cache):
        try:
            z = np.load(cache)
            if np.array_equal(z['key'], key) and int(z['n_metrics']) == len(metrics):
                print(f'Using cached normative stats: {cache}')
                return {(h, i): (z[f'{h}_{i}_mu'], z[f'{h}_{i}_sd'], z[f'{h}_{i}_n'])
                        for h in ('lh', 'rh') for i in range(len(metrics))}
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
            np.savez(cache, **out)
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
    ap.add_argument('subjid')
    ap.add_argument('subjects_dir', nargs='?', default=os.environ.get('SUBJECTS_DIR'))
    ap.add_argument('--no-cache', action='store_true', help='do not read/write the normative stats cache')
    ap.add_argument('--workers', type=int, default=4, help='processes for computing normative stats (default 4)')
    ap.add_argument('--min-n', type=int, default=MIN_N, help='minimum controls with a valid value (default 4)')
    args = ap.parse_args()
    if not args.subjects_dir:
        sys.exit('subjects_dir not given and SUBJECTS_DIR is not set')

    subj_dir = os.path.join(args.subjects_dir, args.subjid)
    if not os.path.isdir(subj_dir):
        sys.exit(f'Subject directory not found: {subj_dir}')
    subjects_file = os.path.join(args.subjects_dir, 'templates', 'subjects_to_average.txt')
    with open(subjects_file) as f:
        cohort = [l.strip() for l in f if l.strip()]
    if args.subjid in cohort:
        sys.exit(f'{args.subjid} is in {subjects_file}; z-scores are only for subjects outside the normative cohort')

    h5_path = os.path.join(args.subjects_dir, 'templates', 'normative', f'{TEMPLATE}_multivariate.h5')
    if not os.path.isfile(h5_path):
        sys.exit(f'Normative data not found: {h5_path}')

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
    stats = load_normative_stats(h5_path, metrics, use_cache=not args.no_cache, workers=args.workers)
    for hemi in ('lh', 'rh'):
        for mi, metric in enumerate(metrics):
            fname = f'{hemi}_{TEMPLATE}_{metric}.tsf'
            hits = [p for p in glob.glob(os.path.join(subj_dir, '**', fname), recursive=True)]
            if not hits:
                print(f'  [skip] {hemi} {metric}: {fname} not found under {subj_dir}')
                continue
            path = hits[0]
            _, tracks = read_mrtrix_tsf(path)
            mu, sd, n = stats[(hemi, mi)]
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
