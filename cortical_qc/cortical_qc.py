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
import os, sys, glob, json, argparse, subprocess, tempfile, shutil
from PIL import Image, ImageDraw
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import nibabel as nib
from nibabel.orientations import io_orientation, axcodes2ornt, ornt_transform, apply_orientation
import numpy as np

_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'cortical_browser'))
sys.path.insert(0, _REPO_DIR)
from cortical_browser import find_streamline_files, find_dwi_files
from cortical_config import load_conf

CAPTURE_SIZE = (900, 700)   # pinned via mrview's -size, so frames always combine cleanly
HOLD_FRAMES  = 6            # frames held at each extreme (with / without streamlines)
FADE_STEPS   = 8            # frames per crossfade leg
FRAME_MS     = 90           # GIF frame duration
LABEL_H      = 24           # top label strip height, in the combined canvas


def find_structural_volume(subj_dir):
    """mri/T1w_proc.nii.gz, or None if missing."""
    p = os.path.join(subj_dir, 'mri', 'T1w_proc.nii.gz')
    return p if os.path.isfile(p) else None


def find_flair_volume(subj_dir):
    """mri/flair_proc.nii.gz, or None if missing. Only used by --interactive —
    the batch GIF capture doesn't include FLAIR."""
    p = os.path.join(subj_dir, 'mri', 'flair_proc.nii.gz')
    return p if os.path.isfile(p) else None


def dwi_metrics_configured(subjects_dir):
    """True if corticalDWI_params.conf's browser_metrics — repo defaults,
    overridden by subjects_dir's own corticalDWI_params.conf if present, same
    two-tier resolution cortical_browser_config.py uses — configures at least
    one dwi/ metric. False means this study doesn't use DWI metrics at all,
    so DWI-space QC is skipped outright rather than going by whether dwi/
    folders merely happen to exist on disk. If browser_metrics isn't set in
    either file, defaults to True (matches the pre-existing behavior of
    always attempting DWI when the folder is there)."""
    params, _, _, _ = load_conf(_REPO_DIR, subjects_dir)
    raw = params.get('browser_metrics')
    if raw is None:
        return True
    metrics = [m.strip() for m in raw.split(',') if m.strip()]
    return any(m.startswith('dwi/') for m in metrics)


def discover_subject_files(subjects_dir, subj_id, check_dwi=True):
    subj_dir = os.path.join(subjects_dir, subj_id)
    dwi_files = find_dwi_files(subj_dir) if check_dwi else {}   # fa, lh, rh (dwi-space streamlines)
    stream_t1 = find_streamline_files(subj_dir)                 # lh, rh (T1-space streamlines, mri/)

    report = {'T1w_proc': find_structural_volume(subj_dir)}
    if check_dwi:
        report['dti/fa'] = dwi_files.get('fa')
    report['streamlines lh (mri/)'] = stream_t1.get('lh')
    report['streamlines rh (mri/)'] = stream_t1.get('rh')
    if check_dwi:
        report['streamlines lh (dwi/)'] = dwi_files.get('lh')
        report['streamlines rh (dwi/)'] = dwi_files.get('rh')
    for label, path in report.items():
        print(f'  {"found  " if path else "MISSING"}  {label:24s} {path or ""}')
    if not check_dwi:
        print('  (dwi/ not configured in browser_metrics — not checked)')

    return {
        't1':          find_structural_volume(subj_dir),
        'stream_t1':   {'lh': stream_t1.get('lh'), 'rh': stream_t1.get('rh')},
        'fa':          dwi_files.get('fa'),
        'stream_fa':   {'lh': dwi_files.get('lh'), 'rh': dwi_files.get('rh')},
        'has_dwi_dir': check_dwi and os.path.isdir(os.path.join(subj_dir, 'dwi')),
    }


# ── mrview command building ───────────────────────────────────────────────────

def _mrview_base_cmd(volumes, streamlines):
    """The part shared between a batch capture and an --interactive session:
    the volume(s) to load, plus a -tractography.load per hemisphere present."""
    cmd = ['mrview'] + list(volumes)
    for hemi in ('lh', 'rh'):
        if streamlines.get(hemi):
            cmd += ['-tractography.load', streamlines[hemi]]
    return cmd


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
        cmd = _mrview_base_cmd([volume], streamlines) + [
            '-size', f'{CAPTURE_SIZE[0]},{CAPTURE_SIZE[1]}',
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
    """seq_fa=None (no dwi/ directory at all) drops the second row entirely,
    rather than rendering it as a 'not found' placeholder."""
    w, h = CAPTURE_SIZE
    label_t1 = label_strip('T1w_proc + streamlines (mri/)', w)
    label_fa = label_strip('FA (dti) + streamlines (dwi/, warped)', w) if seq_fa is not None else None
    n_rows = 1 if seq_fa is None else 2
    n = len(seq_t1) if seq_fa is None else max(len(seq_t1), len(seq_fa))
    row_h = h + LABEL_H

    frames = []
    for i in range(n):
        canvas = Image.new('RGB', (w, row_h * n_rows), (10, 10, 12))
        canvas.paste(label_t1, (0, 0))
        canvas.paste(seq_t1[i % len(seq_t1)], (0, LABEL_H))
        if seq_fa is not None:
            canvas.paste(label_fa, (0, row_h))
            canvas.paste(seq_fa[i % len(seq_fa)], (0, row_h + LABEL_H))
        frames.append(canvas)

    frames[0].save(
        out_path, save_all=True, append_images=frames[1:],
        duration=FRAME_MS, loop=0, optimize=True,
    )


# ── WM intensity QC figure ──────────────────────────────────────────────────

AP_AXIS = 2   # A-P: index increases toward Anterior
LR_AXIS = 0   # L-R: index increases toward Left

WM_LABELS = {'lh': 2, 'rh': 41}   # FreeSurfer aseg: 2=Left-Cerebral-WM, 41=Right-Cerebral-WM


def slice_profile(data, mask, axis):
    """Mean of data[mask] per slice along `axis`; NaN for slices with no masked voxels."""
    other_axes = tuple(a for a in range(data.ndim) if a != axis)
    masked = np.where(mask, data, np.nan)
    with np.errstate(invalid='ignore'):
        return np.nanmean(masked, axis=other_axes)


def triplanar_composite(vol, pad_value=0.0):
    """Mid-volume sagittal | coronal | axial, hstacked into one array, all
    oriented for a single imshow(..., origin='upper') call: superior up,
    anterior right (sagittal) / up (axial), left on the right-hand side of
    each panel (neurological convention). `vol` must already be in LIA voxel
    order (see `to_lia`) — true as-is for FreeSurfer-conformed (256^3)
    volumes, and after reorientation for anything else (e.g. DWI-space FA,
    which isn't cubic, hence the row-padding below)."""
    li, ii, ai = (s // 2 for s in vol.shape)   # L-R, I, A-P mid-indices
    sag = vol[li, :, :]                 # rows=I (sup->inf), cols=A-P (post->ant)
    cor = vol[:, :, ai].T                # rows=I (sup->inf), cols=L-R (R->L)
    axl = np.flipud(vol[:, ii, :].T)     # rows=A-P flipped (ant->post), cols=L-R (R->L)

    height = max(sag.shape[0], cor.shape[0], axl.shape[0])

    def pad_rows(a):
        extra = height - a.shape[0]
        if extra == 0:
            return a
        top = extra // 2
        return np.pad(a, ((top, extra - top), (0, 0)), constant_values=pad_value)

    return np.hstack([pad_rows(sag), pad_rows(cor), pad_rows(axl)])


def to_lia(data, affine):
    """Reorients a data array to LIA voxel order/direction (axis0=L-R,
    incr->L; axis1=S-I, incr->I; axis2=P-A, incr->A) regardless of the
    volume's native orientation, so slice_profile/triplanar_composite's axis
    assumptions always hold. A no-op for already-LIA data (e.g.
    FreeSurfer-conformed T1w_proc/flair_proc/aparc+aseg), and required for
    anything else (e.g. DWI-space FA, which is typically RAS)."""
    transform = ornt_transform(io_orientation(affine), axcodes2ornt(('L', 'I', 'A')))
    return apply_orientation(data, transform)


def _build_profile_figure(vol, aseg, vol_label, subj_id, out_path,
                           display_clamp, profile_ylim, ref_value):
    """Shared plotting core for build_wm_profile/build_fa_profile: triplanar
    view of `vol` (clamped to `display_clamp` for the colormap and
    histogram x-axis) plus, masked by the aparc+aseg WM labels, intensity
    profiles along the A-P/L-R axes (clamped to `profile_ylim`) and an
    intensity histogram — all referenced against `ref_value` (a dashed
    line), not necessarily 1.0. `vol` and `aseg` must already share a grid
    and be in LIA voxel order (see `to_lia`)."""
    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(2, 3, height_ratios=[1, 1.2])

    ax_tri = fig.add_subplot(gs[0, :])
    im = ax_tri.imshow(triplanar_composite(vol), cmap='turbo',
                        vmin=display_clamp[0], vmax=display_clamp[1], origin='upper')
    ax_tri.set_title(f'Triplanar (mid-volume) — sagittal | coronal | axial — {vol_label}')
    ax_tri.axis('off')
    fig.colorbar(im, ax=ax_tri, fraction=0.025, pad=0.01)

    axes = [fig.add_subplot(gs[1, i]) for i in range(3)]
    for hemi, label in WM_LABELS.items():
        mask = aseg == label
        ap_profile = slice_profile(vol, mask, AP_AXIS)
        lr_profile = slice_profile(vol, mask, LR_AXIS)
        axes[0].plot(np.arange(len(ap_profile)), ap_profile, label=hemi)
        axes[1].plot(np.arange(len(lr_profile)), lr_profile, label=hemi)
        axes[2].hist(vol[mask], bins=100, alpha=0.5, label=hemi)

    axes[0].axhline(ref_value, color='gray', linestyle='--', linewidth=1)
    axes[0].set_title(f'WM intensity, A-P axis — {vol_label}')
    axes[0].set_xlabel('slice index (posterior -> anterior)')
    axes[0].set_ylabel('mean WM intensity')
    axes[0].set_ylim(*profile_ylim)
    axes[0].legend()

    axes[1].axhline(ref_value, color='gray', linestyle='--', linewidth=1)
    axes[1].set_title(f'WM intensity, L-R axis — {vol_label}')
    axes[1].set_xlabel('slice index (right -> left)')
    axes[1].set_ylabel('mean WM intensity')
    axes[1].set_ylim(*profile_ylim)
    axes[1].legend()

    axes[2].axvline(ref_value, color='gray', linestyle='--', linewidth=1)
    axes[2].set_title(f'WM intensity distribution — {vol_label}')
    axes[2].set_xlabel('intensity')
    axes[2].set_ylabel('voxel count')
    axes[2].set_xlim(*display_clamp)
    axes[2].legend()

    fig.suptitle(subj_id)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def build_wm_profile(subj_dir, subj_id, out_path, vol_name='T1w_proc.nii.gz'):
    """Per-hemisphere WM-intensity QC figure for one subject: a triplanar
    view of `vol_name` plus, masked by the aparc+aseg WM labels, intensity
    profiles along the A-P and L-R axes and an intensity histogram,
    referenced against 1.0 (this pipeline normalizes T1w_proc/flair_proc so
    WM's median is ~1.0). Returns False (without writing anything) if
    aparc+aseg.nii.gz or vol_name is missing from the subject's mri/
    directory."""
    mri_dir = os.path.join(subj_dir, 'mri')
    aseg_path = os.path.join(mri_dir, 'aparc+aseg.nii.gz')
    vol_path = os.path.join(mri_dir, vol_name)
    if not (os.path.isfile(aseg_path) and os.path.isfile(vol_path)):
        return False

    aseg_img, vol_img = nib.load(aseg_path), nib.load(vol_path)
    aseg = to_lia(np.asarray(aseg_img.dataobj), aseg_img.affine)
    vol = to_lia(np.asarray(vol_img.dataobj), vol_img.affine)

    _build_profile_figure(vol, aseg, vol_name, subj_id, out_path,
                           display_clamp=(0.2, 1.2), profile_ylim=(0.8, 1.2), ref_value=1.0)
    return True


def build_fa_profile(subj_dir, subj_id, out_path):
    """Same WM-intensity QC figure as build_wm_profile, for the DTI FA map
    (dwi/dti/fa.nii.gz). FA lives in DWI space, not the T1-conformed grid
    aparc+aseg.nii.gz is on, so the WM labels are first warped onto the FA
    grid with the pipeline's own T1->b0 SyN transform
    (cortical_register_t1_to_dwi.sh's dwi/t1native_to_b0_{1Warp,0GenericAffine}),
    nearest-neighbor since it's a label map. Unlike T1w_proc/flair_proc, FA
    isn't normalized to a WM median of 1.0, so the reference line/axis
    clamp are instead anchored to this subject's own WM-median FA on a
    [0, 1] scale. Returns False (without writing anything) if any required
    input is missing or the warp step fails (e.g. antsApplyTransforms isn't
    on PATH)."""
    mri_dir = os.path.join(subj_dir, 'mri')
    dwi_dir = os.path.join(subj_dir, 'dwi')
    aseg_path = os.path.join(mri_dir, 'aparc+aseg.nii.gz')
    fa_path = os.path.join(dwi_dir, 'dti', 'fa.nii.gz')
    warp_path = os.path.join(dwi_dir, 't1native_to_b0_1Warp.nii.gz')
    affine_path = os.path.join(dwi_dir, 't1native_to_b0_0GenericAffine.mat')
    if not all(os.path.isfile(p) for p in (aseg_path, fa_path, warp_path, affine_path)):
        return False

    tmp_dir = tempfile.mkdtemp(prefix='cortical_qc_fa_')
    try:
        aseg_dwispace = os.path.join(tmp_dir, 'aparc+aseg_dwispace.nii.gz')
        cmd = ['antsApplyTransforms', '-d', '3',
               '-i', aseg_path, '-r', fa_path, '-o', aseg_dwispace,
               '-t', warp_path, '-t', affine_path, '-n', 'NearestNeighbor']
        try:
            subprocess.run(cmd, check=True, timeout=120,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

        fa_img, aseg_img = nib.load(fa_path), nib.load(aseg_dwispace)
        fa = to_lia(np.asarray(fa_img.dataobj), fa_img.affine)
        aseg = to_lia(np.asarray(aseg_img.dataobj), aseg_img.affine)

        wm_mask = np.isin(aseg, list(WM_LABELS.values()))
        if not wm_mask.any():
            return False
        ref_value = float(np.median(fa[wm_mask]))

        _build_profile_figure(fa, aseg, 'fa.nii.gz', subj_id, out_path,
                               display_clamp=(0.0, 1.0), profile_ylim=(0.0, 1.0), ref_value=ref_value)
        return True
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── index page ────────────────────────────────────────────────────────────────

def build_index(out_dir, subjects_dir):
    """A left sidebar of subject buttons + a right pane showing the clicked
    subject's GIF. Lists every sub-* directory under subjects_dir (not just
    ones processed this run, so it stays correct across incremental runs);
    any subject with no <id>_qc.gif in out_dir is listed but unclickable —
    in red if that's unexplained (missing input files or a capture that
    errored out), or in green if the subject's own folder contains a file
    named "skip" (an intentional, explicit opt-out). A subject with a GIF
    also gets a mri/ check-or-cross mark (and a dwi/ one too, unless the
    study has no dwi/ metric configured at all — see dwi_metrics_configured),
    read from the <id>_qc_status.json written alongside its GIF, so a
    DWI-space capture that silently fell back to a placeholder is visible
    from the sidebar without opening every GIF."""
    show_dwi_col = dwi_metrics_configured(subjects_dir)
    all_subj = sorted(
        d for d in os.listdir(subjects_dir)
        if d.startswith('sub-') and os.path.isdir(os.path.join(subjects_dir, d))
    )
    have_gif = {f[:-len('_qc.gif')] for f in os.listdir(out_dir) if f.endswith('_qc.gif')}
    have_profile_t1 = {f[:-len('_wm_profile_t1.png')] for f in os.listdir(out_dir) if f.endswith('_wm_profile_t1.png')}
    have_profile_flair = {f[:-len('_wm_profile_flair.png')] for f in os.listdir(out_dir) if f.endswith('_wm_profile_flair.png')}
    have_profile_fa = {f[:-len('_wm_profile_fa.png')] for f in os.listdir(out_dir) if f.endswith('_wm_profile_fa.png')}
    is_skipped = lambda s: os.path.isfile(os.path.join(subjects_dir, s, 'skip'))
    n_skipped = sum(1 for s in all_subj if s not in have_gif and is_skipped(s))
    n_missing = sum(1 for s in all_subj if s not in have_gif) - n_skipped

    def read_status(s):
        """None (not {}) when there's no status file to read — distinct from
        a status file that explicitly recorded a False, so a gif that
        predates this status-file feature doesn't get misread as a failure."""
        p = os.path.join(out_dir, f'{s}_qc_status.json')
        if not os.path.isfile(p):
            return None
        try:
            with open(p) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def mark(state, na=False):
        # state: True/False/None. None splits into two distinct cases:
        #   na=True  -> a status file exists but explicitly has no dwi result
        #               (no dwi/ data for this subject — legitimately N/A)
        #   na=False -> no status file at all (e.g. a gif predating this
        #               feature) — genuinely unknown, not the same claim.
        if state is True:
            return '<span class="mark ok">✓</span>'
        if state is False:
            return '<span class="mark bad">✗</span>'
        if na:
            return '<span class="mark na" title="not applicable (no dwi/ data for this subject)">–</span>'
        return ('<span class="mark unknown" title="unknown (no status recorded — rerun without '
                '--skip-gif-creation)">?</span>')

    def button_html(s):
        if s in have_gif:
            status = read_status(s)
            # mri: a gif can't exist unless its T1 capture succeeded (main()
            # only ever writes one after that), so this is True by
            # construction even when there's no status file (or key) to
            # confirm it — unlike dwi, which genuinely can be unknown or N/A.
            mri_ok = True if status is None else status.get('mri', True)
            marks = mark(mri_ok)
            if show_dwi_col:
                marks += (mark(None) if status is None else mark(status.get('dwi'), na=True))
            attrs = f' data-gif="{s}_qc.gif"'
            if s in have_profile_t1:
                attrs += f' data-profile-t1="{s}_wm_profile_t1.png"'
            if s in have_profile_flair:
                attrs += f' data-profile-flair="{s}_wm_profile_flair.png"'
            if s in have_profile_fa:
                attrs += f' data-profile-fa="{s}_wm_profile_fa.png"'
            return (f'<button{attrs}>'
                    f'<span class="row"><span class="name">{s}</span>'
                    f'<span class="marks">{marks}</span></span></button>')
        if is_skipped(s):
            return f'<button class="skipped" disabled title="skipped (has a \'skip\' file)">{s}</button>'
        return f'<button class="missing" disabled title="no QC data (missing input files or capture failed)">{s}</button>'

    buttons = '\n'.join(button_html(s) for s in all_subj)
    col_headers = ''
    if have_gif:
        dwi_label = '<span class="mark-label">dwi</span>' if show_dwi_col else ''
        col_headers = (f'<div class="row header-row"><span class="name"></span>'
                        f'<span class="marks"><span class="mark-label">mri</span>{dwi_label}</span></div>')
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Cortical QC</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ background: #111; color: #ddd; font-family: sans-serif; margin: 0; display: flex; height: 100vh; }}
  #sidebar {{ width: 180px; flex: none; overflow-y: auto; background: #1a1a1a; border-right: 1px solid #333; padding: 8px; }}
  #sidebar h1 {{ font-size: 13px; color: #e9c46a; margin: 4px 8px 12px; }}
  button {{ display: block; width: 100%; text-align: left; padding: 8px; margin-bottom: 4px;
            background: none; border: none; border-radius: 4px; color: #ddd; font-size: 13px; cursor: pointer; }}
  button:hover {{ background: #2a2a2a; }}
  button.active {{ background: #e9c46a; color: #111; font-weight: 600; }}
  button.missing {{ color: #e06c5e; cursor: not-allowed; }}
  button.missing:hover {{ background: none; }}
  button.skipped {{ color: #6ec06c; cursor: not-allowed; }}
  button.skipped:hover {{ background: none; }}
  .row {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; }}
  .name {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .marks {{ display: flex; flex: none; gap: 3px; }}
  .mark {{ font-size: 11px; }}
  .mark.ok {{ color: #6ec06c; }}
  .mark.bad {{ color: #e06c5e; }}
  .mark.unknown {{ color: #666; }}
  .mark.na {{ color: #666; }}
  .header-row {{ padding: 0 8px 4px; }}
  .mark-label {{ font-size: 10px; color: #888; text-transform: uppercase; letter-spacing: .03em; }}
  #search {{ display: block; width: 100%; box-sizing: border-box; padding: 6px 8px; margin: 0 0 8px;
             background: #111; border: 1px solid #333; border-radius: 4px; color: #ddd; font-size: 13px; }}
  #main {{ flex: 1; display: flex; flex-direction: column; min-width: 0; }}
  #view-controls {{ flex: none; display: flex; gap: 6px; padding: 10px 16px; border-bottom: 1px solid #333; }}
  .view-btn {{ display: inline-block; width: auto; padding: 6px 14px; background: #1a1a1a;
               border: 1px solid #333; border-radius: 4px; color: #ddd; font-size: 13px; cursor: pointer; }}
  .view-btn:hover {{ background: #2a2a2a; }}
  .view-btn.active {{ background: #e9c46a; color: #111; font-weight: 600; border-color: #e9c46a; }}
  #viewer {{ flex: 1; display: flex; align-items: center; justify-content: center; padding: 16px; overflow: auto; }}
  #viewer img {{ max-width: 100%; max-height: 100%; }}
  #placeholder {{ color: #666; font-size: 13px; }}
</style></head>
<body>
<div id="sidebar">
  <h1>{len(all_subj)} subject(s){f', {n_missing} missing QC data' if n_missing else ''}{f', {n_skipped} skipped' if n_skipped else ''}</h1>
  <input id="search" type="text" placeholder="Search subject ID... (&uarr;/&darr; to browse)">
  {col_headers}
  {buttons}
</div>
<div id="main">
  <div id="view-controls">
    <button class="view-btn active" data-view="gif">Streamlines</button>
    <button class="view-btn" data-view="profileT1">T1</button>
    <button class="view-btn" data-view="profileFlair">FLAIR</button>
    <button class="view-btn" data-view="profileFa">FA</button>
  </div>
  <div id="viewer"><span id="placeholder">Click a subject</span></div>
</div>
<script>
  const viewer = document.getElementById('viewer')
  const search = document.getElementById('search')
  const allButtons = () => Array.from(document.querySelectorAll('#sidebar button'))
  const navigable = () => allButtons().filter(b => !b.disabled && b.style.display !== 'none')
  const viewBtns = Array.from(document.querySelectorAll('.view-btn'))
  const viewLabels = {{ gif: 'Streamlines', profileT1: 'T1', profileFlair: 'FLAIR', profileFa: 'FA' }}
  let currentView = 'gif'

  function renderViewer() {{
    const btn = allButtons().find(b => b.classList.contains('active'))
    viewer.innerHTML = ''
    if (!btn) {{
      viewer.innerHTML = '<span id="placeholder">Click a subject</span>'
      return
    }}
    const src = btn.dataset[currentView]
    if (!src) {{
      viewer.innerHTML = `<span id="placeholder">${{viewLabels[currentView]}} not available for ${{btn.querySelector('.name').textContent}}</span>`
      return
    }}
    const img = document.createElement('img')
    img.src = src
    viewer.appendChild(img)
  }}

  function selectButton(btn) {{
    if (!btn) return
    allButtons().forEach(b => b.classList.remove('active'))
    btn.classList.add('active')
    btn.scrollIntoView({{ block: 'nearest' }})
    renderViewer()
  }}

  allButtons().forEach(btn => {{
    if (!btn.disabled) btn.addEventListener('click', () => selectButton(btn))
  }})

  viewBtns.forEach(vb => {{
    vb.addEventListener('click', () => {{
      viewBtns.forEach(b => b.classList.remove('active'))
      vb.classList.add('active')
      currentView = vb.dataset.view
      renderViewer()
    }})
  }})

  search.addEventListener('input', () => {{
    const q = search.value.toLowerCase()
    allButtons().forEach(b => {{ b.style.display = b.textContent.toLowerCase().includes(q) ? '' : 'none' }})
  }})

  document.addEventListener('keydown', e => {{
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
    e.preventDefault()
    const list = navigable()
    if (!list.length) return
    const curIdx = list.findIndex(b => b.classList.contains('active'))
    const nextIdx = curIdx < 0 ? 0
      : e.key === 'ArrowDown' ? Math.min(curIdx + 1, list.length - 1)
      : Math.max(curIdx - 1, 0)
    selectButton(list[nextIdx])
  }})

  selectButton(navigable()[0])
</script>
</body></html>
"""
    path = os.path.join(out_dir, 'index.html')
    with open(path, 'w') as f:
        f.write(html)
    return path


# ── interactive mode ──────────────────────────────────────────────────────────

def run_interactive(subjects_dir, subj_id):
    """Opens two real, interactive mrview windows side by side, at the same
    time, for one subject — T1-space (T1w_proc + flair_proc + mri/
    streamlines) and DWI-space (dti/fa + the dwi/-warped streamlines). Unlike
    capture_pair(), these run directly against the real display (no xvfb) and
    carry none of the capture-only flags, so each is a normal, fully
    interactive session; the script exits once both windows are closed (in
    whichever order). Kept as two separate mrview processes rather than one
    combined session because T1/FLAIR and FA live in different physical
    spaces (that's why the dwi/-warped streamlines exist as a separate file)
    — mrview has no way to apply the nonlinear warp between them, so loading
    both into one window would show them misaligned. That's purely a
    same-window-vs-not issue though, not a timing one, so there's no reason
    the two processes can't run concurrently."""
    print(subj_id)
    files = discover_subject_files(subjects_dir, subj_id, check_dwi=dwi_metrics_configured(subjects_dir))
    if not files['t1'] or not (files['stream_t1']['lh'] or files['stream_t1']['rh']):
        sys.exit('\nMissing T1w_proc and/or mri/ streamlines — nothing to open.')

    t1_volumes = [files['t1']]
    flair = find_flair_volume(os.path.join(subjects_dir, subj_id))
    print(f'  {"found  " if flair else "MISSING"}  flair_proc               {flair or ""}')
    if flair:
        t1_volumes.append(flair)

    procs = [subprocess.Popen(_mrview_base_cmd(t1_volumes, files['stream_t1']) + ['-mode', '2'])]
    if files['has_dwi_dir'] and files['fa'] and (files['stream_fa']['lh'] or files['stream_fa']['rh']):
        procs.append(subprocess.Popen(_mrview_base_cmd([files['fa']], files['stream_fa']) + ['-mode', '2']))
        print('\nOpened T1-space and DWI-space sessions — close both to finish.')
    else:
        print('\nNo DWI-space data available — opened T1-space session only.')

    for p in procs:
        p.wait()


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='mrview-based QC: streamlines-visibility crossfade GIF per subject')
    ap.add_argument('subjects_dir')
    ap.add_argument('subj_ids', nargs='*',
                     help='Subject IDs to QC; default: every sub-* directory in subjects_dir')
    ap.add_argument('--out-dir', help='Output directory for GIFs (default: <subjects_dir>/QC)')
    ap.add_argument('--interactive', action='store_true',
                     help='Open live mrview sessions (T1-space, then DWI-space) for one subject '
                          'instead of building a GIF. Requires exactly one subject ID.')
    ap.add_argument('--skip-gif-creation', action='store_true',
                     help="Don't (re)capture any GIFs — just rebuild index.html from whatever "
                          '<id>_qc.gif files are already in --out-dir. Any subject IDs given are ignored.')
    args = ap.parse_args()

    if args.interactive:
        if len(args.subj_ids) != 1:
            sys.exit('--interactive requires exactly one subject ID.')
        run_interactive(args.subjects_dir, args.subj_ids[0])
        return

    out_dir = args.out_dir or os.path.join(args.subjects_dir, 'QC')
    os.makedirs(out_dir, exist_ok=True)

    if args.skip_gif_creation:
        index_path = build_index(out_dir, args.subjects_dir)
        print(f'Index: {index_path}')
        return

    subj_ids = args.subj_ids or sorted(
        d for d in os.listdir(args.subjects_dir)
        if d.startswith('sub-') and os.path.isdir(os.path.join(args.subjects_dir, d))
    )
    if not subj_ids:
        sys.exit(f'No sub-* subjects found under {args.subjects_dir}')

    check_dwi = dwi_metrics_configured(args.subjects_dir)
    if not check_dwi:
        print('No dwi/ metric configured in browser_metrics — DWI-space QC skipped for all subjects.')

    for i, subj_id in enumerate(subj_ids, 1):
        print(f'\n[{i}/{len(subj_ids)}] {subj_id}')
        try:
            files = discover_subject_files(args.subjects_dir, subj_id, check_dwi=check_dwi)

            t1_with, t1_without = capture_pair(files['t1'], files['stream_t1'])
            if not t1_with:
                # T1w_proc + its streamlines are the one required piece (dwi/ is
                # optional, see has_dwi_dir below) — without them there's nothing
                # worth a GIF for, so skip this subject rather than writing an
                # all-placeholder file. It then shows up as "missing" in the index.
                print('  [SKIP] missing T1w_proc and/or mri/ streamlines')
                continue
            seq_t1 = crossfade_sequence(t1_with, t1_without)

            dwi_status = None   # None = not applicable (not configured, or no dwi/ dir)
            if files['has_dwi_dir']:
                fa_with, fa_without = capture_pair(files['fa'], files['stream_fa'])
                if fa_with:
                    seq_fa = crossfade_sequence(fa_with, fa_without)
                    dwi_status = True
                else:
                    seq_fa = placeholder_sequence('dti/fa / dwi/ streamlines', 2 * HOLD_FRAMES)
                    dwi_status = False
            else:
                seq_fa = None   # not configured, or no dwi/ directory at all: drop the second row entirely

            out_path = os.path.join(out_dir, f'{subj_id}_qc.gif')
            build_combined_gif(seq_t1, seq_fa, out_path)
            status_path = os.path.join(out_dir, f'{subj_id}_qc_status.json')
            with open(status_path, 'w') as f:
                json.dump({'mri': True, 'dwi': dwi_status}, f)
            print(f'  -> {out_path}')

            for view_key, vol_name in (('t1', 'T1w_proc.nii.gz'), ('flair', 'flair_proc.nii.gz')):
                profile_path = os.path.join(out_dir, f'{subj_id}_wm_profile_{view_key}.png')
                try:
                    if build_wm_profile(os.path.join(args.subjects_dir, subj_id), subj_id, profile_path, vol_name=vol_name):
                        print(f'  -> {profile_path}')
                    else:
                        print(f'  [INFO] No aparc+aseg.nii.gz or {vol_name} — skipping {view_key} WM intensity profile')
                except Exception as exc:   # noqa: BLE001 — optional figure, shouldn't kill the GIF result
                    print(f'  [WARN] WM intensity profile ({view_key}) failed: {exc}')

            fa_profile_path = os.path.join(out_dir, f'{subj_id}_wm_profile_fa.png')
            try:
                if build_fa_profile(os.path.join(args.subjects_dir, subj_id), subj_id, fa_profile_path):
                    print(f'  -> {fa_profile_path}')
                else:
                    print('  [INFO] No FA map and/or T1->b0 transform — skipping FA WM intensity profile')
            except Exception as exc:   # noqa: BLE001 — optional figure, shouldn't kill the GIF result
                print(f'  [WARN] FA WM intensity profile failed: {exc}')
        except Exception as exc:   # noqa: BLE001 — one bad subject shouldn't kill the batch
            print(f'  [ERROR] {subj_id}: {exc}')

    index_path = build_index(out_dir, args.subjects_dir)
    print(f'\nIndex: {index_path}')


if __name__ == '__main__':
    main()
