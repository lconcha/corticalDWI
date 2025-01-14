#!/bin/bash
source `which my_do_cmd `

sID=$1


t1_brain=${SUBJECTS_DIR}/${sID}/mri/brain.mgz
fa=${SUBJECTS_DIR}/${sID}/dwi/fa.nii.gz
rh_pial_surf=${SUBJECTS_DIR}/${sID}/surf/rh_pial_fsLR-32k.surf.gii
lh_pial_surf=${SUBJECTS_DIR}/${sID}/surf/lh_pial_fsLR-32k.surf.gii
rh_white_surf=${SUBJECTS_DIR}/${sID}/surf/rh_white_fsLR-32k.surf.gii
lh_white_surf=${SUBJECTS_DIR}/${sID}/surf/lh_white_fsLR-32k.surf.gii
rh_laplace_tck=${SUBJECTS_DIR}/${sID}/mri/rh_fsLR-32k_laplace-wm-streamlines.tck
lh_laplace_tck=${SUBJECTS_DIR}/${sID}/mri/lh_fsLR-32k_laplace-wm-streamlines.tck


pial_colour="0 0 1"
white_colour="1 0 0"

my_do_cmd fsleyes \
  --scene ortho3d --displaySpace world  --bgColour 0 0 0 --showColourBar \
  $t1_brain \
  $fa \
  $rh_pial_surf  -o --colour "$pial_colour" -w 2 \
  $rh_white_surf -o --colour "$white_colour" -w 2  \
  $lh_pial_surf  -o --colour "$pial_colour" -w 2  \
  $lh_white_surf -o --colour "$white_colour" -w 2  \
  $rh_laplace_tck --lineWidth 2 \
  $lh_laplace_tck --lineWidth 2



  #--vertexData varios.txt  \