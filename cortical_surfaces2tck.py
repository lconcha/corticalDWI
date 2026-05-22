#!/usr/bin/env python3

import argparse
import sys
import numpy as np
import nibabel as nib
from nibabel.streamlines import TckFile, Tractogram


def main():
    parser = argparse.ArgumentParser(
        description='Create a TCK file where each streamline connects corresponding '
                    'vertices between a white matter and pial GIFTI surface.'
    )
    parser.add_argument('white', help='White matter boundary surface (GIFTI .surf.gii)')
    parser.add_argument('pial',  help='Pial surface (GIFTI .surf.gii)')
    parser.add_argument('output', help='Output tractography file (.tck)')
    args = parser.parse_args()
    

    print(f'[INFO] Loading surfaces:\n\twhite:\t{args.white}\n\tpial:\t{args.pial}')
    white_surf = nib.load(args.white)
    pial_surf  = nib.load(args.pial)

    # darrays[0] = NIFTI_INTENT_POINTSET (vertex coordinates)
    white_coords = white_surf.darrays[0].data.astype(np.float32)
    pial_coords  = pial_surf.darrays[0].data.astype(np.float32)

    if white_coords.shape != pial_coords.shape:
        sys.exit(f'[ERROR] Vertex count mismatch: white={white_coords.shape[0]}, pial={pial_coords.shape[0]}')

    n = white_coords.shape[0]
    print(f'[INFO] {n} vertices — creating {n} streamlines')

    streamlines = [np.array([white_coords[i], pial_coords[i]]) for i in range(n)]
    
    # GIFTI coordinates are in RAS mm — matches MRtrix convention
    tractogram = Tractogram(streamlines=streamlines, affine_to_rasmm=np.eye(4))
    TckFile(tractogram).save(args.output)
    print(f'[INFO] Saved: {args.output}')


if __name__ == '__main__':
    main()
