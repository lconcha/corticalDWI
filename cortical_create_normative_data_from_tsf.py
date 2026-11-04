#!/usr/bin/env python3
"""
cortical_create_normative_data_from_tsf.py — Python port of
cortical_create_normative_data_from_tsf.m

Builds a normative (control-cohort) dataset from per-subject MRtrix .tsf
files and saves it as a single HDF5 file for use by the cortical DWI viewer's
future normative-comparison / multivariate (Mahalanobis) explorer features.

Unlike the MATLAB version, this does NOT also precompute/save per-metric
mean/std/n — those are cheaply derivable from the raw per-subject stack via
np.nanmean/np.nanstd/count-of-non-NaN, so storing them separately would just
be redundant derived data that could drift out of sync. Consumers should
compute them on demand from lh_M/rh_M.

Also unlike the MATLAB version, a subject's per-metric contribution is placed
at a FIXED index (its position in subjects_to_average.txt) rather than being
appended positionally as files are found. This keeps the subject axis
consistently aligned across metrics even if some subjects are missing a
particular metric's file — the MATLAB script implicitly assumes every
subject has every metric, which would silently misalign the subject axis
across the metric dimension if that assumption doesn't hold.

Usage:
    python cortical_create_normative_data_from_tsf.py [subjects_dir]

If subjects_dir is omitted, the SUBJECTS_DIR environment variable is used
(matching the MATLAB script's getenv('SUBJECTS_DIR')).
"""
import os, sys, glob, argparse
import numpy as np
import h5py

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'cortical_browser'))
from cortical_io import read_mrtrix_tsf, pad_to_matrix, find_tsf, find_scalar_gii, read_gifti_scalar
from cortical_browser_config import TEMPLATE, METRICS, print_config_report   # shared with cortical_browser.py


def load_subject_matrix(tsf_path):
    """One subject's (nVerts, ownMaxLen) matrix, -1 sentinel masked to NaN
    (mirrors cortical_cell2mat(..., 'MaskInvalid', true))."""
    _, tracks = read_mrtrix_tsf(tsf_path)
    M = pad_to_matrix(tracks)
    M[M == -1] = np.nan
    return M


def stack_subjects(subjects_dir, subjects, hemi, template, metric):
    """(stack, is_scalar). stack is a (nVerts, maxDepth, nSubjects) NaN-padded
    stack for one metric/hemi, aligned to `subjects` by index (maxDepth is 1
    when is_scalar). A subject missing this file contributes an all-NaN
    slice, keeping the subject axis consistent across metrics.

    A metric is either depth-wise (a <folder>/{hemi}_{template}_<name>.tsf
    per subject — find_tsf) or single-scalar-per-vertex (a
    <folder>/{hemi}.<name>.{template}.func.gii per subject — find_scalar_gii,
    e.g. surf/thickness, in any subfolder, not just surf/). Its type is
    decided once, from whichever convention the first matching subject's
    file follows, then used for every subject — a metric is expected to be
    consistently one type across a cohort, so once a type is chosen the
    other convention is no longer even checked."""
    is_scalar = None
    per_subj = [None] * len(subjects)
    n_found = 0
    for i, subj in enumerate(subjects):
        subj_dir = os.path.join(subjects_dir, subj)
        if is_scalar is not False:
            hits = find_scalar_gii(subj_dir, hemi, template, metric)
            if hits:
                is_scalar = True
                per_subj[i] = read_gifti_scalar(hits[0])[:, None]   # (nVerts, 1)
                n_found += 1
                continue
        if is_scalar is not True:
            hits = find_tsf(subj_dir, hemi, template, metric)
            if len(hits) > 1:
                print(f'    [warn] {subj} {hemi} {metric}: {len(hits)} matches, using {hits[0]}')
            if hits:
                is_scalar = False
                per_subj[i] = load_subject_matrix(hits[0])
                n_found += 1
    is_scalar = bool(is_scalar)
    print(f'    {hemi} {metric}: {n_found}/{len(subjects)} subjects found' + (' [scalar]' if is_scalar else ''))

    n_verts = next((m.shape[0] for m in per_subj if m is not None), 0)
    max_len = max((m.shape[1] for m in per_subj if m is not None), default=0)
    stack = np.full((n_verts, max_len, len(subjects)), np.nan, dtype=np.float32)
    for s, M in enumerate(per_subj):
        if M is not None:
            stack[:, :M.shape[1], s] = M
    return stack, is_scalar


def build_normative_stack(subjects_dir, subjects, metrics, hemi, template=TEMPLATE):
    """(nVerts, nDepths, nSubjects, nMetrics) stack for one hemisphere,
    across all metrics, NaN-padded to the deepest metric's depth and
    trimmed of any trailing depth columns that are all-NaN everywhere.

    A scalar metric (is_scalar, see stack_subjects) only ever has real data
    at depth 0 up to this point — same as any depth-wise metric that happens
    to be shallower than the cohort's deepest one, EXCEPT a scalar isn't
    "missing" past depth 0, it's constant, so after the normal NaN-pad +
    trim (which must run first, on the un-broadcast data, or every depth
    would look "non-empty" because of the scalar and nothing would ever get
    trimmed) its depth-0 value is broadcast across the full, now-final depth
    axis — matching the same depth-invariant convention cortical_browser.py's
    own display path (tile_scalar_matrix) already uses, so z-scoring/
    Mahalanobis see a real, constant value at every depth instead of NaN."""
    per_metric = [stack_subjects(subjects_dir, subjects, hemi, template, metric) for metric in metrics]
    per_metric_stacks = [s for s, _ in per_metric]
    is_scalar          = [sc for _, sc in per_metric]

    n_verts   = per_metric_stacks[0].shape[0]
    n_subj    = len(subjects)
    n_depths  = max(s.shape[1] for s in per_metric_stacks)
    n_metrics = len(metrics)
    M = np.full((n_verts, n_depths, n_subj, n_metrics), np.nan, dtype=np.float32)
    for m, stack in enumerate(per_metric_stacks):
        M[:, :stack.shape[1], :, m] = stack

    keep = ~np.all(np.isnan(M), axis=(0, 2, 3))
    M = M[:, keep, :, :]

    for m, scalar in enumerate(is_scalar):
        if scalar:
            M[:, :, :, m] = M[:, 0:1, :, m]
    return M


def main():
    ap = argparse.ArgumentParser(description='Precompute an HDF5 normative dataset from a subject cohort')
    ap.add_argument('subjects_dir', nargs='?', default=os.environ.get('SUBJECTS_DIR'))
    args = ap.parse_args()
    if not args.subjects_dir:
        sys.exit('subjects_dir not given and SUBJECTS_DIR is not set')

    print_config_report(args.subjects_dir)

    subjects_file = os.path.join(args.subjects_dir, 'templates', 'subjects_to_average.txt')
    if not os.path.isfile(subjects_file):
        sys.exit(f'Subject list not found: {subjects_file}')
    with open(subjects_file) as f:
        subjects = [line.strip() for line in f if line.strip()]
    print(f'Cohort  : {len(subjects)} subjects from {subjects_file}')

    out_dir = os.path.join(args.subjects_dir, 'templates', 'normative')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'{TEMPLATE}_multivariate.h5')

    str_dtype = h5py.string_dtype(encoding='utf-8')
    with h5py.File(out_path, 'w') as h5f:
        h5f.attrs['template'] = TEMPLATE
        h5f.create_dataset('metrics',  data=np.array(METRICS,  dtype=object), dtype=str_dtype)
        h5f.create_dataset('subjects', data=np.array(subjects, dtype=object), dtype=str_dtype)
        for hemi in ('lh', 'rh'):
            print(f'Building {hemi}_M …')
            M = build_normative_stack(args.subjects_dir, subjects, METRICS, hemi)
            print(f'  {hemi}_M shape: {M.shape}  (nVerts, nDepths, nSubjects, nMetrics)')
            # Chunked so the browser's scattered-vertex reads (a clicked
            # vertex + its neighbor ring, or Mahalanobis's per-vertex cohort
            # fit) touch a small vertex block instead of h5py's default
            # auto-chunking, which packed depth/subjects/metrics into
            # fragments too (e.g. (2561, 4, 6, 1) for an 83-subject/4-metric
            # cohort) — a single-vertex query there had to decompress ~200
            # separate chunks across the depth/subject axes alone. Full
            # depth+subject axes and one metric per chunk means a query
            # touches exactly one chunk per selected vertex; benchmarked at
            # 5-20x faster for ring/Mahalanobis-sized vertex sets with no
            # measurable cost to the full-cohort bulk read pattern
            # (materialize_normative / cortical_zscore_tsf.py's _block_stats).
            chunks = (min(128, M.shape[0]), M.shape[1], M.shape[2], 1)
            h5f.create_dataset(f'{hemi}_M', data=M, chunks=chunks, compression='gzip', compression_opts=1)

    size_mb = os.path.getsize(out_path) / 1e6
    print(f'\nSaved {out_path} ({size_mb:.1f} MB)')


if __name__ == '__main__':
    main()
