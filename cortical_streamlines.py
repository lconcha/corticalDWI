#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Nov 15 19:57:59 2023

@author: lconcha
"""


import copy
import nibabel as nib
import numpy as np
#from scipy.interpolate import RegularGridInterpolator
import sys
from mayavi import mlab
from mayavi.tools.show import show
import yt
from yt.visualization.api import Streamlines

from streamtracer import StreamTracer, VectorGrid


# in mansfield: /misc/lauterbur/lconcha/TMP/swm/
# in syphon: /datos/syphon/lconcha/tmp/laplace

in_surf_scanner = 'lh_white_scanner.gii'
in_surf_trk = 'lh_white_scanner.trk'
in_laplace = 'sub-74277_lap_100.nii'
out_surf_prefix = 'sub-74277_lap_100_beeee'
in_vec = 'sub-74277_lap_100_vec.nii'

depth = 2


in_surf = in_surf_scanner

# load data
surf = nib.load(in_surf)
V = surf.get_arrays_from_intent('NIFTI_INTENT_POINTSET')[0].data
F = surf.get_arrays_from_intent('NIFTI_INTENT_TRIANGLE')[0].data
laplace = nib.load(in_laplace)
lp = laplace.get_fdata()
vec = nib.load(in_vec)
volvec = vec.get_fdata()
L2 = np.atleast_1d(np.linalg.norm(volvec, 2, 3))
L2[L2==0] = 1
volvecnorm = volvec / np.expand_dims(L2, 3)


norm = np.linalg.norm(volvec, axis=3)
res = volvec / norm[:, :, :, np.newaxis]

print('loaded data and parameters')



vX = volvec[:,:,120,0]
vY = volvec[:,:,120,1]
vZ = volvec[:,:,120,2]


vX = res[:,:,120,0]
vY = res[:,:,120,1]
vZ = res[:,:,120,2]

#mlab.quiver3d(vX,vY,vZ)



V2 = V.copy()


V2 = V2 - laplace.affine[:3,3].T

nvertices = V.shape[0]

for vindex in range(nvertices):
    thisv = V[vindex,:];
    
    thisv = thisv - laplace.affine[:3,3].T
    
    thisvpad = np.append(thisv,1)
    thisvpadtransformed = thisvpad.dot(laplace.affine)
    V2[vindex,:] = thisvpadtransformed[0:3]

    #thisvpad = np.append(thisv,1)
    #thisvpadtransformed = thisvpad.dot(np.linalg.inv(laplace.affine))
    #V3[vindex,:] = thisvpadtransformed[0:3]

#93,93,95

    

#mlab.points3d(V[:,0],  V[:,1],  V[:,2], color=(1,1,1) )
mlab.points3d(V2[:,0], V2[:,1], V2[:,2], color=(1,0,0) )
#mlab.points3d(V3[:,0], V3[:,1], V3[:,2], color=(0,0,1) )
mlab.volume_slice(lp)
mlab.volume_slice(volvec[:,:,:,0])

## Use streamtracer https://streamtracer.readthedocs.io/en/latest/#
nsteps = 200
step_size = 0.1
tracer = StreamTracer(nsteps, step_size)
grid_spacing = [1, 1, 1]
grid = VectorGrid(volvecnorm, grid_spacing)
seeds = V2
tracer.trace(seeds, grid, direction=1)

radius = 0.1
scolor=(1,0,0)
#nstreamlines = np.asarray(np.shape(tracer.xs))[0,]
nstreamlines = len(tracer.xs)
nskip = 100
nfirst=100
for s in range(0,nstreamlines,nskip):
    this_streamline = tracer.xs[s]
    mlab.plot3d(this_streamline[:,0],this_streamline[:,1],this_streamline[:,2],tube_radius=radius,color=scolor)

lend=np.shape(V2)[0]
#mlab.points3d(V2[0:lend:nskip,0], V2[0:lend:nskip,1], V2[0:lend:nskip,2], color=(1,1,1), scale_factor=3 )
mlab.points3d(V2[:,0], V2[:,1], V2[:,2], color=(1,1,1), scale_factor=1, mask_points=nskip )

mlab.points3d(V2[0:nfirst,0], V2[0:nfirst,1], V2[0:nfirst,2], color=(1,0,1), scale_factor=1)
scolor=(0,1,0)
for s in range(0,nfirst):
    this_streamline = tracer.xs[s]
    #mlab.plot3d(this_streamline[:,0],this_streamline[:,1],this_streamline[:,2],tube_radius=radius,color=scolor)
    mlab.plot3d(this_streamline[:,0],this_streamline[:,1],this_streamline[:,2],tube_radius=radius,color=scolor)


# a ver, ya casi:
#newstreamline = nib.streamlines.tractogram.Tractogram(streamlines=tracer.xs)
#newstreamline.affine_to_rasmm = laplace.affine
#nib.streamlines.save(newstreamline,'test2.tck' )

# shape = np.shape(lp)
# x,y,z      = np.mgrid[ 0:1.0:1j*shape[0] , 0:1.0:1j*shape[1] , 0:1.0:1j*shape[2] ]
# x,y,z      = np.mgrid[ 0:shape[0], 0:shape[1], 0:shape[2] ]



# st = mlab.flow(x, y, z, u, v, w, line_width=1, seedtype='plane', integration_direction='forward')



# # Draw vector field                                                                                                                                                              
# u,v,w      = volvecnorm[...,0], volvecnorm[...,1], volvecnorm[...,2]
# vect_field = mlab.pipeline.vector_field(x,y,z, u,v,w)
# # https://elektromagnetisme.no/2010/09/25/using-mayavi-to-visualize-electric-fields/index.html
# #streams = mlab.pipeline.streamline(vect_field,  seedtype='plane', seed_scale=2.0, color=(1.0,0.0,0.0))
# listofstreams = list() # create a list to hold all our streamlines (or flows if you speak MayaVi)
# for s in range(200):#len(V2)): # for each vertex, create a streamline seed
#     print(s)
#     thisvertex = V2[s,:]
#     stream = mlab.pipeline.streamline(vect_field,  seedtype='point')
#     stream.stream_tracer.initial_integration_step = 0.01 # the integration step for the runge kutta method
#     stream.stream_tracer.maximum_propagation = 20.0 # the maximum length each step should reach - lowered to avoid messy output
#     stream.stream_tracer.integration_direction = 'forward' # integrate only in forward direction
#     stream.stream_tracer.compute_vorticity = False
#     stream.seed.widget.enabled = False # hide the widget itself
#     stream.actor.actor.visibility = True
#     stream.seed.widget.position = thisvertex # set the stream widget to the same position as the vertex
#     listofstreams.append(stream) # and eventually, add the stream to our list for convenience
# show()

