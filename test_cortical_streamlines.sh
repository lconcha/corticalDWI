#!/bin/bash

export SUBJECTS_DIR=/misc/lauterbur/lconcha/TMP/glaucoma/fs_glaucoma
sID=sub-74277

### Laplacian field
echolor yellow "[INFO] Calculating Laplace Field"

# Convert segmentation to NIFTI
mri_convert ${SUBJECTS_DIR}/${sID}/mri/aparc+aseg.mgz \
            ${SUBJECTS_DIR}/${sID}/mri/aparc+aseg.nii.gz

# 1. Calculate the Laplace field
fcheck=${SUBJECTS_DIR}/${sID}/mri/laplace-wm.nii.gz
if [ -f $fcheck ]
then
  echolor cyan "[INFO] File exists: $fcheck"
else
  python sWM/laplace_solver.py \
    ${SUBJECTS_DIR}/${sID}/mri/aparc+aseg.nii.gz \
    ${SUBJECTS_DIR}/${sID}/mri/laplace-wm
fi



### Streamlines
# echolor yellow "[INFO] Computing streamlines"


# # convert surfaces for later use
# mris_convert --to-scanner \
#   ${SUBJECTS_DIR}/${sID}/surf/lh.white \
#   ${SUBJECTS_DIR}/${sID}/surf/lh_white_scanner.surf.gii 


# in_surf=${SUBJECTS_DIR}/${sID}/surf/lh_white_scanner.surf.gii
# in_vec=
# nsteps=200
# step_size=0.1
# out_tck=


# python cortical_streamlines.py \
#   $in_surf \
#   $in_vec \
#   $nsteps \
#   $step_size \
#   $out_tck