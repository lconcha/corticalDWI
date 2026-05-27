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
import subprocess
import os
import tempfile
import shutil
import subprocess

# Function to print help message
def print_help():
    print(f"""
Usage: {sys.argv[0]} <in_surf> <in_surf_pial> <in_vec> <nsteps> <step_size> <out_tck>

Arguments:
  in_surf        Input white surface (.gii) in scanner coordinates
  in_surf_pial   Input pial surface (.gii) in scanner coordinates, or 'no' to skip
  in_vec         4D NIfTI file with vector field
  nsteps         Number of steps for streamline tracing (e.g., 200)
  step_size      Step size (in mm) for streamline tracing (e.g., 0.1)
  out_tck        Output .tck file

Example:
  python {sys.argv[0]} lh.white.surf.gii no laplace_vectors.nii.gz 200 0.1 output.tck
""")

if len(sys.argv) < 7 or sys.argv[1] in ("-h", "--help"):
    print_help()
    sys.exit(0)



in_surf      = sys.argv[1]   # Should be a .gii file in scanner coordinates
in_surf_pial = sys.argv[2]   # Should be a .gii file in scanner coordinates
in_vec       = sys.argv[3]   # .nii 4D
nsteps       = sys.argv[4]   # 200
step_size    = sys.argv[5]   # 0.1
out_tck      = sys.argv[6]

nsteps       = int(nsteps)
step_size    = float(step_size)

print(f'Starting the creation of streamlines with the following arguments:')
print(f'  - in_surf      : {in_surf}')
print(f'  - in_surf_pial : {in_surf_pial}')
print(f'  - in_vec       : {in_vec}')
print(f'  - nsteps       : {nsteps}')
print(f'  - step_size    : {step_size}')
print(f'  - out_tck      : {out_tck}')


if in_surf_pial == 'no' :
    connect_to_pial = False
    print('    Will NOT connect pial and white surfaces. Streamlines will begin at white surface.')
else :
    connect_to_pial = True
    print('    Streamlines will begin at pial surface')


def prepend_surface_to_streamlines(tracer, surface, vec):
    print(f'      Prepending {surface}')
    surf_to_append = nib.load(surface)
    vertices = surf_to_append.get_arrays_from_intent('NIFTI_INTENT_POINTSET')[0].data
    
    # transform vertex coordinates from scanner/RAS space to voxel index space
    inv_affine = np.linalg.inv(vec.affine)
    V2pial = nib.affines.apply_affine(inv_affine, vertices)
    nvertices = vertices.shape[0]
    for vindex in range(nvertices):
        xyz_pial = V2pial[vindex]
        xyz_streamline = tracer.xs[vindex]
        xyz_both = np.insert(xyz_streamline,0,xyz_pial,axis=0)
        tracer.xs[vindex] = xyz_both
    return tracer


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


# transform vertex coordinates from scanner/RAS space to voxel index space
inv_affine = np.linalg.inv(vec.affine)
V2 = nib.affines.apply_affine(inv_affine, V)
nvertices = V.shape[0]


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
    
    tmpdir = tempfile.mkdtemp(prefix='cortical_streamlines_')
    print(f'   Connecting WM streamlines to mid surfaces...')
    for dist in [0.1, 0.3, 0.5, 0.7, 0.9]:
        tmpfile = os.path.join(tmpdir, f'tmp_layersurf_dist_{dist}.surf.gii')
        print(f'     -- Create layer surface at distance {dist} from WM: {tmpfile}')
        subprocess.run([
            "wb_command",
            "-surface-cortex-layer",
            in_surf_pial,
            in_surf,
            str(dist),
            tmpfile
        ], check=True)
        tracer = prepend_surface_to_streamlines(tracer, tmpfile, vec) # add the layer surfaces
    
    print(f'  Connecting to pial surface:  {in_surf_pial}')
    tracer = prepend_surface_to_streamlines(tracer,in_surf_pial, vec) # add the pial surface
    shutil.rmtree(tmpdir)

print(f'  saving tck : {out_tck}')
laplacian_streamlines = nib.streamlines.tractogram.Tractogram(streamlines=tracer.xs)
laplacian_streamlines.affine_to_rasmm = vec.affine
nib.streamlines.save(laplacian_streamlines, out_tck )
print('done.')