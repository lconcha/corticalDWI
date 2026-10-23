#!/usr/bin/env python3
"""
cortical_indices2gifti.py — turn a list of vertex indices into a binary
(0/1) .func.gii overlay.

Reads the vertex count from a gifti file (either a surface .surf.gii, whose
first data array is [N,3] XYZ points, or a functional .func.gii, whose
first data array is one value per vertex — either works, only the length of
that first array is used) and a plain-text list of vertex indices (one
non-negative integer per line — the same format the cortical browser's
"Save"/"Load" vertex-IDs buttons use, see cortical_browser_manual.md's
*Vertex IDs* section), then writes a .func.gii with one float32 value per
vertex: 1.0 for every vertex in the list, 0.0 everywhere else.

Usage:
    python cortical_indices2gifti.py <gifti_file> <indices_file> [output.func.gii]

If the output path is omitted, it defaults to <indices_file stem>.func.gii.
"""
import os, sys, argparse
import numpy as np
import nibabel as nib


def read_vertex_count(gifti_path):
    """Number of vertices in a gifti file — works for either a surface
    (.surf.gii) or a functional (.func.gii) file; only the first data
    array's length is used."""
    g = nib.load(gifti_path)
    if not g.darrays:
        sys.exit(f'{gifti_path}: no data arrays found')
    return g.darrays[0].data.shape[0]


def read_indices(path):
    """Non-negative integer vertex indices, one per line — the same plain
    .txt format the cortical browser's vertex-IDs Save/Load buttons use.
    Blank lines are skipped; anything else that isn't a non-negative
    integer is a fatal error (mirrors the browser's own strict parsing)."""
    indices = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            if not line.isdigit():
                sys.exit(f'{path}:{lineno}: expected a non-negative integer, got {line!r}')
            indices.append(int(line))
    if not indices:
        sys.exit(f'{path}: no vertex indices found')
    return indices


def write_func_gii(path, values):
    da = nib.gifti.GiftiDataArray(values.astype(np.float32), intent='NIFTI_INTENT_ESTIMATE',
                                   datatype='NIFTI_TYPE_FLOAT32')
    nib.save(nib.gifti.GiftiImage(darrays=[da]), path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('gifti_file', help='.surf.gii or .func.gii — only used for its vertex count')
    ap.add_argument('indices_file', help='plain .txt file, one non-negative integer vertex index per line')
    ap.add_argument('output', nargs='?', help='output .func.gii path (default: <indices_file stem>.func.gii)')
    args = ap.parse_args()

    if not os.path.isfile(args.gifti_file):
        sys.exit(f'Gifti file not found: {args.gifti_file}')
    if not os.path.isfile(args.indices_file):
        sys.exit(f'Indices file not found: {args.indices_file}')

    n_verts = read_vertex_count(args.gifti_file)
    indices = read_indices(args.indices_file)

    in_range = [i for i in indices if i < n_verts]
    out_of_range = len(indices) - len(in_range)
    if not in_range:
        sys.exit(f'{args.indices_file}: no vertex index is within range for {args.gifti_file} (0-{n_verts - 1})')
    if out_of_range:
        print(f'  [warn] {out_of_range} index/indices out of range (0-{n_verts - 1}), dropped')

    values = np.zeros(n_verts, dtype=np.float32)
    values[in_range] = 1.0

    output = args.output or os.path.splitext(os.path.basename(args.indices_file))[0] + '.func.gii'
    write_func_gii(output, values)
    n_set = len(set(in_range))
    print(f'Wrote {output}: {n_set}/{n_verts} vertices set to 1')


if __name__ == '__main__':
    main()
