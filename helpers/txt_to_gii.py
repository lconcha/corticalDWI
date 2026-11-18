#!/usr/bin/env python3
"""Usage:
  txt_to_gii.py --surf <surf.gii> --metric <metric.txt> --out <out.func.gii>
  txt_to_gii.py --surf <surf.gii> --label <indices.txt> --out <out.label.gii> [--label-name NAME]

Builds a metric (.func.gii/.shape.gii) or label (.label.gii) GIFTI file from a
plain text file, checking the vertex count against <surf.gii> so the output
is guaranteed to line up with that mesh. This is the inverse of
gifti_metric_to_txt.sh.

--metric <file>  whitespace-separated text, one row per vertex, one or more
                  columns; each column becomes a separate data map.
--label  <file>  one 0-based vertex index per line; those vertices get key 1
                  in the output label table, everything else key 0 ("???").
"""
import argparse
import sys

import nibabel as nib
import numpy as np
from nibabel.gifti import GiftiDataArray, GiftiImage, GiftiLabel, GiftiLabelTable


def surf_vertex_count(surf_path):
    surf = nib.load(surf_path)
    pointset = surf.get_arrays_from_intent('NIFTI_INTENT_POINTSET')[0]
    return pointset.data.shape[0]


def write_metric(surf_path, txt_path, out_path):
    n = surf_vertex_count(surf_path)
    data = np.loadtxt(txt_path)
    if data.ndim == 1:
        data = data[:, None]
    if data.shape[0] != n:
        sys.exit(f'{txt_path} has {data.shape[0]} rows, {surf_path} has {n} vertices')

    darrays = [
        GiftiDataArray(data=col.astype(np.float32), intent='NIFTI_INTENT_NONE',
                        datatype='NIFTI_TYPE_FLOAT32')
        for col in data.T
    ]
    GiftiImage(darrays=darrays).to_filename(out_path)


def write_label(surf_path, txt_path, out_path, label_name):
    n = surf_vertex_count(surf_path)
    indices = np.loadtxt(txt_path, dtype=int).reshape(-1)
    if indices.size and (indices.max() >= n or indices.min() < 0):
        sys.exit(f'{txt_path} has indices outside [0, {n}) for {surf_path}')

    label_data = np.zeros(n, dtype=np.int32)
    label_data[indices] = 1

    table = GiftiLabelTable()
    background = GiftiLabel(key=0, red=1, green=1, blue=1, alpha=0)
    background.label = '???'
    table.labels.append(background)
    region = GiftiLabel(key=1, red=1, green=0, blue=0, alpha=1)
    region.label = label_name
    table.labels.append(region)

    darray = GiftiDataArray(data=label_data, intent='NIFTI_INTENT_LABEL',
                             datatype='NIFTI_TYPE_INT32')
    GiftiImage(labeltable=table, darrays=[darray]).to_filename(out_path)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--surf', required=True, help='.surf.gii to check vertex count against')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--metric', help='text file, one row per vertex, 1+ columns')
    group.add_argument('--label', help='text file, one 0-based vertex index per line')
    parser.add_argument('--out', required=True, help='output .func.gii/.shape.gii or .label.gii')
    parser.add_argument('--label-name', default='label',
                         help='name for the labeled region (--label mode only)')
    args = parser.parse_args()

    if args.metric:
        write_metric(args.surf, args.metric, args.out)
    else:
        write_label(args.surf, args.label, args.out, args.label_name)


if __name__ == '__main__':
    main()
