#!/bin/bash
source `which my_do_cmd`

export SUBJECTS_DIR=/misc/lauterbur/lconcha/TMP/glaucoma/fs_glaucoma
sID=sub-74277
hemi=lh
nsteps=200
step_size="0.1"
surf_type=white
target_type=fsaverage5
doSimplify=0

### Laplacian field
echolor yellow "[INFO] Calculating Laplace Field"

# Convert segmentation to NIFTI
mri_convert ${SUBJECTS_DIR}/${sID}/mri/aparc+aseg.mgz \
            ${SUBJECTS_DIR}/${sID}/mri/aparc+aseg.nii.gz

# 1. Calculate the Laplace field
fcheck=${SUBJECTS_DIR}/${sID}/mri/laplace-wm_vec.nii.gz
if [ -f $fcheck ]
then
  echolor cyan "[INFO] File exists: $fcheck"
else
  python sWM/laplace_solver.py \
    ${SUBJECTS_DIR}/${sID}/mri/aparc+aseg.nii.gz \
    ${SUBJECTS_DIR}/${sID}/mri/laplace-wm
  my_do_cmd mrcat -axis 3 \
    ${SUBJECTS_DIR}/${sID}/mri/laplace-wm_d{x,y,z}.nii.gz \
    ${SUBJECTS_DIR}/${sID}/mri/laplace-wm_vec.nii.gz
fi


if [ $doSimplify -eq 1 ]
then
    ### Simplify the surface
    echolor yellow "[INFO] Simplify the ${surf_type} surface to $target_type"
    my_do_cmd resample_surface.sh \
    $sID \
    $hemi \
    $surf_type \
    $target_type
    surf=${SUBJECTS_DIR}/${sID}/surf/${hemi}_${surf_type}_${target_type}.surf.gii
else
    echolor yellow "[INFO] Not simplifying surface"
    surf=${SUBJECTS_DIR}/${sID}/surf/${hemi}.white
    target_type="fsnative"
fi



### Streamlines
 echolor yellow "[INFO] Computing streamlines"


# convert surfaces to scanner coordinates
my_do_cmd mris_convert --to-scanner \
  $surf \
  ${SUBJECTS_DIR}/${sID}/surf/${hemi}_${surf_type}_${target_type}_scanner.surf.gii
surf=${SUBJECTS_DIR}/${sID}/surf/${hemi}_${surf_type}_${target_type}_scanner.surf.gii


#in_surf=${SUBJECTS_DIR}/${sID}/surf/${hemi}_white_scanner.surf.gii
in_surf=$surf
in_vec=${SUBJECTS_DIR}/${sID}/mri/laplace-wm_vec.nii.gz
out_tck=${SUBJECTS_DIR}/${sID}/mri/${hemi}_${surf_type}_${target_type}_laplace-wm-streamlines.tck
python cortical_streamlines.py \
  $in_surf \
  $in_vec \
  $nsteps \
  $step_size \
  $out_tck