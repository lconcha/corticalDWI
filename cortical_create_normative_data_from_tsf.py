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

sys.path.insert(0, os.path.dirname(__file__))
from cortical_io import read_mrtrix_tsf, pad_to_matrix
from cortical_browser_config import TEMPLATE, METRICS   # shared with cortical_browser.py


def find_one_subject_file(subjects_dir, subject, filename):
    """Recursively search one subject's directory for a file with the given
    exact basename (mirrors cortical_find_subject_files.m, but per-subject
    so a missing file can be reported/handled individually)."""
    matches = glob.glob(os.path.join(subjects_dir, subject, '**', filename), recursive=True)
    return matches[0] if matches else None


def load_subject_matrix(tsf_path):
    """One subject's (nVerts, ownMaxLen) matrix, -1 sentinel masked to NaN
    (mirrors cortical_cell2mat(..., 'MaskInvalid', true))."""
    _, tracks = read_mrtrix_tsf(tsf_path)
    M = pad_to_matrix(tracks)
    M[M == -1] = np.nan
    return M


def stack_subjects(subjects_dir, subjects, filename):
    """(nVerts, maxDepth, nSubjects) NaN-padded stack for one metric/hemi,
    aligned to `subjects` by index. A subject missing this file contributes
    an all-NaN slice, keeping the subject axis consistent across metrics."""
    per_subj = [None] * len(subjects)
    n_found = 0
    for i, subj in enumerate(subjects):
        path = find_one_subject_file(subjects_dir, subj, filename)
        if path is not None:
            per_subj[i] = load_subject_matrix(path)
            n_found += 1
    print(f'    {filename}: {n_found}/{len(subjects)} subjects found')

    n_verts = next((m.shape[0] for m in per_subj if m is not None), 0)
    max_len = max((m.shape[1] for m in per_subj if m is not None), default=0)
    stack = np.full((n_verts, max_len, len(subjects)), np.nan, dtype=np.float32)
    for s, M in enumerate(per_subj):
        if M is not None:
            stack[:, :M.shape[1], s] = M
    return stack


def build_normative_stack(subjects_dir, subjects, metrics, hemi, template=TEMPLATE):
    """(nVerts, nDepths, nSubjects, nMetrics) stack for one hemisphere,
    across all metrics, NaN-padded to the deepest metric's depth and
    trimmed of any trailing depth columns that are all-NaN everywhere."""
    per_metric_stacks = []
    for metric in metrics:
        filename = f'{hemi}_{template}_{metric}.tsf'
        per_metric_stacks.append(stack_subjects(subjects_dir, subjects, filename))

    n_verts   = per_metric_stacks[0].shape[0]
    n_subj    = len(subjects)
    n_depths  = max(s.shape[1] for s in per_metric_stacks)
    n_metrics = len(metrics)
    M = np.full((n_verts, n_depths, n_subj, n_metrics), np.nan, dtype=np.float32)
    for m, stack in enumerate(per_metric_stacks):
        M[:, :stack.shape[1], :, m] = stack

    keep = ~np.all(np.isnan(M), axis=(0, 2, 3))
    return M[:, keep, :, :]


def main():
    ap = argparse.ArgumentParser(description='Precompute an HDF5 normative dataset from a subject cohort')
    ap.add_argument('subjects_dir', nargs='?', default=os.environ.get('SUBJECTS_DIR'))
    args = ap.parse_args()
    if not args.subjects_dir:
        sys.exit('subjects_dir not given and SUBJECTS_DIR is not set')

    subjects_file = os.path.join(args.subjects_dir, 'templates', 'subjects_to_average.txt')
    if not os.path.isfile(subjects_file):
        sys.exit(f'Subject list not found: {subjects_file}')
    with open(subjects_file) as f:
        subjects = [line.strip() for line in f if line.strip()]
    print(f'Cohort  : {len(subjects)} subjects from {subjects_file}')
    print(f'Metrics : {METRICS}')

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
            h5f.create_dataset(f'{hemi}_M', data=M, compression='gzip', compression_opts=4)

    size_mb = os.path.getsize(out_path) / 1e6
    print(f'\nSaved {out_path} ({size_mb:.1f} MB)')


if __name__ == '__main__':
    main()
