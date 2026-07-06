"""Python readers mirroring the MATLAB helpers used by cortical_browser_2.m.

read_surface       -> read_surface()      (BrainStat) for .surf.gii
read_mrtrix_tsf     -> read_mrtrix_tsf()   for MRtrix track-scalar files
cortical_cell2mat   -> pad_to_matrix()
buildVolGeom        -> build_vol_geom()
"""
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
