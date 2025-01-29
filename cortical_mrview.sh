#!/bin/bash
source `which my_do_cmd `

sID=$1
target_type=$2; # 5k or 32k


t1_brain=${SUBJECTS_DIR}/${sID}/mri/brain.mgz
fa=${SUBJECTS_DIR}/${sID}/dwi/fa.nii.gz
#rh_pial_surf=${SUBJECTS_DIR}/${sID}/surf/rh_pial_fsLR-${target_type}.surf.gii
#lh_pial_surf=${SUBJECTS_DIR}/${sID}/surf/lh_pial_fsLR-${target_type}.surf.gii
#rh_white_surf=${SUBJECTS_DIR}/${sID}/surf/rh_white_fsLR-${target_type}.surf.gii
#lh_white_surf=${SUBJECTS_DIR}/${sID}/surf/lh_white_fsLR-${target_type}.surf.gii
rh_laplace_tck=${SUBJECTS_DIR}/${sID}/mri/rh_fsLR-${target_type}_laplace-wm-streamlines.tck
lh_laplace_tck=${SUBJECTS_DIR}/${sID}/mri/lh_fsLR-${target_type}_laplace-wm-streamlines.tck


rh_fa_tsf=${SUBJECTS_DIR}/${sID}/dwi/rh_fsLR-${target_type}_fa.tsf
lh_fa_tsf=${SUBJECTS_DIR}/${sID}/dwi/lh_fsLR-${target_type}_fa.tsf

my_do_cmd -fake mrview \
  $t1_brain \
  $fa \
  -tractography.load  $rh_laplace_tck \
    -tractography.geometry points -tractography.thickness -0.2 \
    -tractography.tsf_load $rh_fa_tsf -tractography.tsf_range 0 0.5 \
  -tractography.load  $lh_laplace_tck \
    -tractography.geometry points -tractography.thickness -0.2 \
    -tractography.tsf_load $lh_fa_tsf -tractography.tsf_range 0 0.5



  #--vertexData varios.txt  \