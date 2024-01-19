#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jan  5 14:22:17 2024

@author: lconcha
"""

# create streamlines for the laplacian field





import nibabel as nib
import numpy as np
import sys
from streamtracer import StreamTracer, VectorGrid

in_surf      = sys.argv[1]           # Should be a .gii file in scanner coordinates
in_surf_pial = sys.argv[2]           # Should be a .gii file in scanner coordinates
in_vec       = sys.argv[3]            # .nii 4D
nsteps       = sys.argv[4]            # 200
step_size    = sys.argv[5]         # 0.1
out_tck      = sys.argv[6]

nsteps    = int(nsteps)
step_size = float(step_size)

print(f'Starting the creation of streamlines with the following arguments:')
print(f'  - in_surf      : {in_surf}')
print(f'  - in_surf_pial : {in_surf_pial}')
print(f'  - in_vec       : {in_vec}')
print(f'  - nsteps       : {nsteps}')
print(f'  - step_size    : {step_size}')
print(f'  - out_tck      : {out_tck}')


if in_surf_pial == 'no' :
    connect_to_pial = False
    print('    Will NOT connect pial and white surfaces. Streamlines will begin at white suerface.')
else :
    connect_to_pial = True
    print('    Streamlines will begin at pial surface')

# load data
surf = nib.load(in_surf)
V = surf.get_arrays_from_intent('NIFTI_INTENT_POINTSET')[0].data
F = surf.get_arrays_from_intent('NIFTI_INTENT_TRIANGLE')[0].data

vec = nib.load(in_vec)
volvec = vec.get_fdata()



# normalization of vectors
L2 = np.atleast_1d(np.linalg.norm(volvec, 2, 3))
L2[L2==0] = 1
volvecnorm = volvec / np.expand_dims(L2, 3)


# transform vertex coordinates
V2 = V.copy()
nvertices = V.shape[0]
for vindex in range(nvertices):
    thisv = V[vindex,:];
    thisv = thisv - vec.affine[:3,3].T
    thisvpad = np.append(thisv,1)
    thisvpadtransformed = thisvpad.dot(vec.affine)
    V2[vindex,:] = thisvpadtransformed[0:3]

   

## Use streamtracer https://streamtracer.readthedocs.io/en/latest/#
print(f'  seeding {nvertices} streamlines...')
tracer = StreamTracer(nsteps, step_size)
grid_spacing = [1, 1, 1]
grid = VectorGrid(volvecnorm, grid_spacing)
seeds = V2
tracer.trace(seeds, grid, direction=1)
print(f'   ... finished tracing.')


# prepend the coordinate for pial surface before streamline
if connect_to_pial :
    print(f'   Connecting WM streamlines to pial-white lines.')
    # Deal with the pial surface
    print(f'  Load {in_surf_pial}')
    surf_pial = nib.load(in_surf_pial)
    Vpial = surf_pial.get_arrays_from_intent('NIFTI_INTENT_POINTSET')[0].data
    Fpial = surf_pial.get_arrays_from_intent('NIFTI_INTENT_TRIANGLE')[0].data

    # transform vertex coordinates
    V2pial = Vpial.copy()
    nvertices = Vpial.shape[0]
    for vindex in range(nvertices):
        thisv = Vpial[vindex,:];
        thisv = thisv - vec.affine[:3,3].T
        thisvpad = np.append(thisv,1)
        thisvpadtransformed = thisvpad.dot(vec.affine)
        V2pial[vindex,:] = thisvpadtransformed[0:3]
        xyz_pial = V2pial[vindex]
        xyz_streamline = tracer.xs[vindex]
        xyz_both = np.insert(xyz_streamline,0,xyz_pial,axis=0)
        #print(f'xyz_pial : {xyz_pial}, nvertices was {len(xyz_streamline)}, and now is {len(xyz_both)}')
        #print(f' v0 : {xyz_both[0,]}')
        tracer.xs[vindex] = xyz_both
    

print(f'  saving tck : {out_tck}')
laplacian_streamlines = nib.streamlines.tractogram.Tractogram(streamlines=tracer.xs)
laplacian_streamlines.affine_to_rasmm = vec.affine
nib.streamlines.save(laplacian_streamlines, out_tck )

#print(f'  You can check the output with:\n    mrview {in_vec} -tractography.load {out_tck}')
print('done.')