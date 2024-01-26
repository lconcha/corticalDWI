#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jan 25 08:51:27 2024

@author: lconcha
"""

import mayavi.mlab as mlab
import nibabel as nib


f_fa  = '/misc/lauterbur/lconcha/TMP/glaucoma/fs_glaucoma/sub-74277/dwi/fa.nii.gz'
f_tck = '/misc/lauterbur/lconcha/TMP/glaucoma/fs_glaucoma/sub-74277/dwi/rh_fsLR-32k_laplace-wm-streamlines_dwispace.tck'


fa       = nib.load(f_fa)
favalues = fa.get_fdata(fa, caching="unchanged")
