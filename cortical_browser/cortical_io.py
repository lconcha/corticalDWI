"""Python readers mirroring the MATLAB helpers used by cortical_browser_2.m.

read_surface       -> read_surface()      (BrainStat) for .surf.gii
read_mrtrix_tsf     -> read_mrtrix_tsf()   for MRtrix track-scalar files
cortical_cell2mat   -> pad_to_matrix()
buildVolGeom        -> build_vol_geom()
"""
import os, glob
import numpy as np
import nibabel as nib


def read_surface(path):
    """Return (vertices [N,3] float32, faces [M,3] int32) from a .surf.gii file."""
    g = nib.load(path)
    vertices = g.darrays[0].data
    faces = g.darrays[1].data
    return vertices, faces


def read_mrtrix_tsf(path):
    """Parse an MRtrix track-scalar (.tsf) file.

    Returns (header dict, list of float32 arrays, one per track). The list
    preserves empty tracks as zero-length arrays so list index == vertex
    index stays aligned with the surface even if a track has no samples.
    """
    with open(path, 'rb') as f:
        header = {}
        while True:
            line = f.readline().decode('utf-8').strip()
            if line == 'END':
                break
            if ':' not in line:
                continue
            key, value = line.split(':', 1)
            header[key.strip()] = value.strip()

        datatype = header['datatype']
        if datatype == 'Float32LE':
            dtype = np.dtype('<f4')
        elif datatype == 'Float64LE':
            dtype = np.dtype('<f8')
        else:
            raise ValueError(f'Unsupported datatype: {datatype}')

        offset = int(header['file'].split()[1])
        f.seek(offset)
        data = np.fromfile(f, dtype=dtype)

    count = int(header['count'])
    finite_eof = np.flatnonzero(np.isinf(data))
    if finite_eof.size:
        data = data[:finite_eof[0]]

    nan_idx = np.flatnonzero(np.isnan(data))
    tracks = []
    start = 0
    for idx in nan_idx:
        tracks.append(data[start:idx].astype(np.float32))
        start = idx + 1
    if len(tracks) != count:
        raise ValueError(f'Expected {count} tracks, parsed {len(tracks)} from {path}')
    return header, tracks


# ── Metric labels ─────────────────────────────────────────────────────────────
# A metric is identified by "<folder>/<name>", e.g. dwi/dti/fa, dwi/dki/fa,
# mri/T1w_proc, dwi/mrds/mrds_fixels/BIC/FA-par. <folder> is the FULL path,
# every directory name from the subject directory down, of the directory that
# holds the .tsf; <name> is the metric part of the file name
# {hemi}_{template}_<name>.tsf. The folder is what tells apart metrics that
# several methods (or, for MRDS, the same method's different model-selection
# variants) produce under the same name — fa from both dwi/dti and dwi/dki,
# FA-par from both .../mrds_fixels/BIC and .../mrds_fixels/FTest. Being the
# full path (not just the immediate parent directory) means a metric can sit
# however many folders deep and still be looked up unambiguously, with no
# guessing about how many of the leading directories to include.

def split_metric(label):
    folder, _, name = label.rpartition('/')
    if not folder or not name:
        raise ValueError(f"Metric '{label}' must be written as <folder>/<name>, e.g. dwi/dti/fa "
                         f"(folder = the full path, from the subject directory down, to the "
                         f"directory holding the .tsf)")
    return folder, name


def metric_label(tsf_path, hemi, template, subj_dir):
    """Inverse of find_tsf: label for a {hemi}_{template}_<name>.tsf path,
    folder = its full path relative to subj_dir."""
    fname = os.path.basename(tsf_path)
    prefix = f'{hemi}_{template}_'
    if not (fname.startswith(prefix) and fname.endswith('.tsf')):
        raise ValueError(f'{fname} is not a {prefix}<name>.tsf file')
    folder = os.path.relpath(os.path.dirname(tsf_path), subj_dir)
    return f'{folder}/{fname[len(prefix):-len(".tsf")]}'


def metric_id(label):
    """File-name / URL-safe form of a metric label (dwi/dti/fa -> dwi__dti__fa)."""
    return label.replace('/', '__')


def find_tsf(subj_dir, hemi, template, label):
    """Path of {subj_dir}/{folder}/{hemi}_{template}_{name}.tsf, as a single-item
    list if it exists (else empty), where {folder} is the label's full,
    exact directory path relative to subj_dir. Returned as a list (rather than
    a plain path-or-None) to keep this a drop-in for callers written against
    the old glob-based multi-match version."""
    folder, name = split_metric(label)
    path = os.path.join(subj_dir, folder, f'{hemi}_{template}_{name}.tsf')
    return [path] if os.path.isfile(path) else []


def write_mrtrix_tsf(path, tracks, template_path=None):
    """Write a list of 1D float arrays as an MRtrix .tsf (Float32LE).

    If template_path is given, its header (command_history etc.) is carried
    over, with count/datatype/file rewritten. NaN is the per-track delimiter
    and Inf terminates the file, as MRtrix expects.
    """
    extra = []
    if template_path is not None:
        with open(template_path, 'rb') as f:
            for raw in f:
                line = raw.decode('utf-8').rstrip('\n')
                if line.strip() == 'END':
                    break
                key = line.split(':', 1)[0].strip()
                if ':' in line and key not in ('count', 'datatype', 'file', 'mrtrix track scalars'):
                    extra.append(line)
    lines = ['mrtrix track scalars', 'datatype: Float32LE'] + extra + [f'count: {len(tracks)}']
    offset = 0
    for _ in range(3):   # offset depends on its own digit count; converges fast
        header = '\n'.join(lines + [f'file: . {offset}', 'END']) + '\n'
        offset = len(header.encode('utf-8'))
    header = '\n'.join(lines + [f'file: . {offset}', 'END']) + '\n'
    chunks = []
    for t in tracks:
        chunks.append(np.asarray(t, dtype='<f4'))
        chunks.append(np.array([np.nan], dtype='<f4'))
    chunks.append(np.array([np.inf], dtype='<f4'))
    with open(path, 'wb') as f:
        f.write(header.encode('utf-8'))
        np.concatenate(chunks).tofile(f)


def pad_to_matrix(tracks):
    """Equivalent of cortical_cell2mat.m: list of 1D arrays -> [N, maxLen] with NaN padding."""
    max_len = max(len(t) for t in tracks)
    M = np.full((len(tracks), max_len), np.nan, dtype=np.float32)
    for i, t in enumerate(tracks):
        if len(t):
            M[i, :len(t)] = t
    return M


def read_volume(path):
    """Return (data float64 [nx,ny,nz], affine [4,4]) for NIfTI/MGZ — nibabel reads both natively."""
    img = nib.load(path)
    data = np.asarray(img.dataobj, dtype=np.float64)
    return data, img.affine


def build_vol_geom(affine, dims):
    """Per-panel orthoslice geometry from an arbitrary orthogonal affine.

    Port of buildVolGeom() in cortical_browser_2.m, adapted to nibabel's
    column-vector convention (world = affine[:3,:3] @ voxel + affine[:3,3],
    0-based voxel indices) instead of MATLAB's row-vector Transform.T.

    Returns a list of 3 dicts (sagittal, coronal, axial), each with the
    voxel dim to fix/slice, which voxel dims map to horizontal/vertical
    display axes, the world-mm coordinate arrays for those axes, whether
    the extracted 2D slice needs transposing, and the scale/translation
    needed to convert a slice index to its world position.
    """
    A33 = affine[:3, :3]
    transl = affine[:3, 3]

    # vox2world[d] = world axis (0=X,1=Y,2=Z) most affected by voxel dim d
    vox2world = np.argmax(np.abs(A33), axis=0)
    world2vox = np.zeros(3, dtype=int)
    for d in range(3):
        world2vox[vox2world[d]] = d

    panel_h = [1, 0, 0]   # horizontal world axis per panel [sag, cor, ax]
    panel_v = [2, 2, 1]   # vertical   world axis per panel
    names = ['Sagittal', 'Coronal', 'Axial']
    wnames = ['X', 'Y', 'Z']

    geom = []
    for w in range(3):
        fix_vox = world2vox[w]
        hw, vw = panel_h[w], panel_v[w]
        hvd, vvd = world2vox[hw], world2vox[vw]

        h_coords = A33[hw, hvd] * np.arange(dims[hvd]) + transl[hw]
        v_coords = A33[vw, vvd] * np.arange(dims[vvd]) + transl[vw]

        other_sorted = sorted({0, 1, 2} - {fix_vox})
        needs_T = (other_sorted[0] == hvd)

        geom.append(dict(
            fix_vox=fix_vox, h_vox=hvd, v_vox=vvd,
            h_world=hw, v_world=vw,
            h_coords=h_coords, v_coords=v_coords,
            needs_T=needs_T,
            scale_fix=A33[w, fix_vox], transl_fix=transl[w],
            n_slices=dims[fix_vox],
            name=names[w], wname=wnames[w],
        ))
    return geom


def get_slice(vol_data, geom_w, k):
    """2D image (rows=vertical, cols=horizontal) at slice index k for one panel's geometry."""
    idx = [slice(None)] * 3
    idx[geom_w['fix_vox']] = k
    img = vol_data[tuple(idx)]
    if geom_w['needs_T']:
        img = img.T
    return img


def world_to_voxel(affine, world_xyz):
    """Inverse affine: world mm -> (i,j,k) voxel index (float, not rounded)."""
    inv = np.linalg.inv(affine)
    vox = inv[:3, :3] @ np.asarray(world_xyz) + inv[:3, 3]
    return vox
