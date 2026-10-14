#!/usr/bin/env python3
"""
cortical_qc.py — mrview-based QC: streamlines-visibility crossfade.

For each subject, two configs are each captured twice with mrview (once with
the Laplacian streamlines visible, once with them hidden):
  - T1w_proc (mri/)  + the T1-space streamlines (mri/)
  - dti/fa   (dwi/)  + the same streamlines already warped to DWI space (dwi/)

The two captures per config are crossfaded into a looping GIF — since
everything BUT the streamlines is identical between the two frames, anything
that moves in the loop is the streamlines, which makes misregistration/bad
tracking obvious at a glance. The two configs' loops are placed side by side
into one final animated GIF per subject.

Usage:
    python cortical_qc.py <subjects_dir> [subj_id ...] [--out-dir DIR]
"""
import os, sys, glob, argparse, subprocess, tempfile, shutil
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'cortical_browser'))
from cortical_browser import find_streamline_files, find_dwi_files

CAPTURE_SIZE = (900, 700)   # pinned via mrview's -size, so frames always combine cleanly
HOLD_FRAMES  = 6            # frames held at each extreme (with / without streamlines)
FADE_STEPS   = 8            # frames per crossfade leg
FRAME_MS     = 90           # GIF frame duration
LABEL_H      = 24           # top label strip height, in the combined canvas


def find_structural_volume(subj_dir):
    """mri/T1w_proc.nii.gz, or None if missing."""
    p = os.path.join(subj_dir, 'mri', 'T1w_proc.nii.gz')
    return p if os.path.isfile(p) else None


def discover_subject_files(subjects_dir, subj_id):
    subj_dir = os.path.join(subjects_dir, subj_id)
    dwi_files = find_dwi_files(subj_dir)          # fa, lh, rh (dwi-space streamlines)
    stream_t1 = find_streamline_files(subj_dir)    # lh, rh (T1-space streamlines, mri/)

    report = {
        'T1w_proc':              find_structural_volume(subj_dir),
        'dti/fa':                dwi_files.get('fa'),
        'streamlines lh (mri/)': stream_t1.get('lh'),
        'streamlines rh (mri/)': stream_t1.get('rh'),
        'streamlines lh (dwi/)': dwi_files.get('lh'),
        'streamlines rh (dwi/)': dwi_files.get('rh'),
    }
    for label, path in report.items():
        print(f'  {"found  " if path else "MISSING"}  {label:24s} {path or ""}')

    return {
        't1':          find_structural_volume(subj_dir),
        'stream_t1':   {'lh': stream_t1.get('lh'), 'rh': stream_t1.get('rh')},
        'fa':          dwi_files.get('fa'),
        'stream_fa':   {'lh': dwi_files.get('lh'), 'rh': dwi_files.get('rh')},
        'has_dwi_dir': os.path.isdir(os.path.join(subj_dir, 'dwi')),
    }


# ── mrview capture ────────────────────────────────────────────────────────────

def capture_pair(volume, streamlines, timeout=120):
    """Runs mrview once for one volume + its streamlines, grabbing a frame with
    them visible and a second with them hidden. Returns (with_img, without_img)
    as PIL Images, or (None, None) if the volume or both streamline files are
    missing."""
    if not volume or not (streamlines.get('lh') or streamlines.get('rh')):
        return None, None

    tmp_dir = tempfile.mkdtemp(prefix='cortical_qc_')
    try:
        prefix = 'qc'
        cmd = ['mrview', volume, '-size', f'{CAPTURE_SIZE[0]},{CAPTURE_SIZE[1]}']
        for hemi in ('lh', 'rh'):
            if streamlines.get(hemi):
                cmd += ['-tractography.load', streamlines[hemi]]
        cmd += [
            '-mode', '2', '-noannotations', '-intensity_range', '0,1',
            '-capture.prefix', prefix, '-capture.folder', tmp_dir,
            '-capture.grab',                        # frame 0: streamlines visible
            '-tractography.opacity', '0', '-capture.grab',   # frame 1: hidden
            '-exit',
        ]
        # Always run under a virtual display, even when $DISPLAY is set — mrview
        # otherwise pops up a real, briefly-visible window on the caller's screen
        # for every capture_pair() call.
        cmd = ['xvfb-run', '-a'] + cmd
        subprocess.run(cmd, check=True, timeout=timeout,
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        frames = sorted(glob.glob(os.path.join(tmp_dir, f'{prefix}*.png')))
        if len(frames) < 2:
            raise RuntimeError(f'mrview produced {len(frames)} frame(s), expected 2')
        with_img    = Image.open(frames[0]).convert('RGB').copy()
        without_img = Image.open(frames[1]).convert('RGB').copy()
        return with_img, without_img
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── crossfade assembly ────────────────────────────────────────────────────────

def crossfade_sequence(img_a, img_b):
    """Looping sequence: hold@A, fade A->B, hold@B, fade B->A."""
    seq = [img_a] * HOLD_FRAMES
    for i in range(1, FADE_STEPS):
        seq.append(Image.blend(img_a, img_b, i / FADE_STEPS))
    seq += [img_b] * HOLD_FRAMES
    for i in range(1, FADE_STEPS):
        seq.append(Image.blend(img_b, img_a, i / FADE_STEPS))
    return seq


def placeholder_sequence(label, n_frames):
    img = Image.new('RGB', CAPTURE_SIZE, (17, 19, 23))
    d = ImageDraw.Draw(img)
    text = f'{label} not found'
    bbox = d.textbbox((0, 0), text)
    d.text(((CAPTURE_SIZE[0] - (bbox[2] - bbox[0])) / 2,
             (CAPTURE_SIZE[1] - (bbox[3] - bbox[1])) / 2),
            text, fill=(192, 86, 77))
    return [img] * n_frames


def label_strip(text, width):
    strip = Image.new('RGB', (width, LABEL_H), (17, 19, 23))
    d = ImageDraw.Draw(strip)
    d.text((6, 4), text, fill=(217, 219, 224))
    return strip


def build_combined_gif(seq_t1, seq_fa, out_path):
    """seq_fa=None (no dwi/ directory at all) drops the second column entirely,
    rather than rendering it as a 'not found' placeholder."""
    w, h = CAPTURE_SIZE
    label_t1 = label_strip('T1w_proc + streamlines (mri/)', w)
    label_fa = label_strip('FA (dti) + streamlines (dwi/, warped)', w) if seq_fa is not None else None
    n_cols = 1 if seq_fa is None else 2
    n = len(seq_t1) if seq_fa is None else max(len(seq_t1), len(seq_fa))

    frames = []
    for i in range(n):
        canvas = Image.new('RGB', (w * n_cols, h + LABEL_H), (10, 10, 12))
        canvas.paste(label_t1, (0, 0))
        canvas.paste(seq_t1[i % len(seq_t1)], (0, LABEL_H))
        if seq_fa is not None:
            canvas.paste(label_fa, (w, 0))
            canvas.paste(seq_fa[i % len(seq_fa)], (w, LABEL_H))
        frames.append(canvas)

    frames[0].save(
        out_path, save_all=True, append_images=frames[1:],
        duration=FRAME_MS, loop=0, optimize=True,
    )


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='mrview-based QC: streamlines-visibility crossfade GIF per subject')
    ap.add_argument('subjects_dir')
    ap.add_argument('subj_ids', nargs='*',
                     help='Subject IDs to QC; default: every sub-* directory in subjects_dir')
    ap.add_argument('--out-dir', help='Output directory for GIFs (default: <subjects_dir>/QC)')
    args = ap.parse_args()

    subj_ids = args.subj_ids or sorted(
        d for d in os.listdir(args.subjects_dir)
        if d.startswith('sub-') and os.path.isdir(os.path.join(args.subjects_dir, d))
    )
    if not subj_ids:
        sys.exit(f'No sub-* subjects found under {args.subjects_dir}')

    out_dir = args.out_dir or os.path.join(args.subjects_dir, 'QC')
    os.makedirs(out_dir, exist_ok=True)

    for i, subj_id in enumerate(subj_ids, 1):
        print(f'\n[{i}/{len(subj_ids)}] {subj_id}')
        try:
            files = discover_subject_files(args.subjects_dir, subj_id)

            t1_with, t1_without = capture_pair(files['t1'], files['stream_t1'])
            seq_t1 = (crossfade_sequence(t1_with, t1_without) if t1_with
                      else placeholder_sequence('T1w_proc / mri/ streamlines', 2 * HOLD_FRAMES))

            if files['has_dwi_dir']:
                fa_with, fa_without = capture_pair(files['fa'], files['stream_fa'])
                seq_fa = (crossfade_sequence(fa_with, fa_without) if fa_with
                          else placeholder_sequence('dti/fa / dwi/ streamlines', 2 * HOLD_FRAMES))
            else:
                seq_fa = None   # no dwi/ directory at all: drop the second column entirely

            out_path = os.path.join(out_dir, f'{subj_id}_qc.gif')
            build_combined_gif(seq_t1, seq_fa, out_path)
            print(f'  -> {out_path}')
        except Exception as exc:   # noqa: BLE001 — one bad subject shouldn't kill the batch
            print(f'  [ERROR] {subj_id}: {exc}')


if __name__ == '__main__':
    main()
