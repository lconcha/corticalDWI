#!/bin/bash
source `which my_do_cmd`

export SUBJECTS_DIR=/misc/lauterbur/lconcha/TMP/glaucoma/fs_glaucoma
sID=sub-74277
hemi=lh
nsteps=200
step_size="0.1"
tck_step_size=0.5
#surf_type=white
target_type=fsLR-32k
doSimplify=1

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
    for surf_type in white pial
    do
      echolor yellow "[INFO] Simplify the ${surf_type} surface to $target_type"
      my_do_cmd resample_surface.sh \
      $sID \
      $hemi \
      $surf_type \
      $target_type
    done
    surf=${SUBJECTS_DIR}/${sID}/surf/${hemi}_white_${target_type}.surf.gii
    surf_pial=${SUBJECTS_DIR}/${sID}/surf/${hemi}_pial_${target_type}.surf.gii
else
    echolor yellow "[INFO] Not simplifying surface"
    surf=${SUBJECTS_DIR}/${sID}/surf/${hemi}.white
    surf_pial=${SUBJECTS_DIR}/${sID}/surf/${hemi}.pial
    target_type="fsnative"
fi



### Streamlines
 echolor yellow "[INFO] Computing streamlines"


# # convert surfaces to scanner coordinates
# my_do_cmd mris_convert --to-scanner \
#   $surf \
#   ${SUBJECTS_DIR}/${sID}/surf/${hemi}_white_${target_type}_scanner.surf.gii
# surf=${SUBJECTS_DIR}/${sID}/surf/${hemi}_white_${target_type}_scanner.surf.gii
# my_do_cmd mris_convert --to-scanner \
#   $surf_pial \
#   ${SUBJECTS_DIR}/${sID}/surf/${hemi}_pial_${target_type}_scanner.surf.gii
# surf_pial=${SUBJECTS_DIR}/${sID}/surf/${hemi}_pial_${target_type}_scanner.surf.gii

# echolor orange "Check: freeview -f $surf $surf_pial"
# exit 2

#in_surf=${SUBJECTS_DIR}/${sID}/surf/${hemi}_white_scanner.surf.gii
in_surf=$surf
in_vec=${SUBJECTS_DIR}/${sID}/mri/laplace-wm_vec.nii.gz
tmp_tck=/tmp/temp_$$.tck
out_tck=${SUBJECTS_DIR}/${sID}/mri/${hemi}_${target_type}_laplace-wm-streamlines.tck
my_do_cmd python cortical_streamlines.py \
  $in_surf \
  $surf_pial \
  $in_vec \
  $nsteps \
  $step_size \
  $tmp_tck
my_do_cmd tckresample -force -quiet -step_size $tck_step_size $tmp_tck $out_tck
rm $tmp_tck


my_do_cmd tckresample -force -quiet -endpoints $out_tck ${out_tck%.tck}_orig.tck
my_do_cmd tckresample -force -quiet -endpoints $out_tck ${out_tck%.tck}_endsOnly.tck

echolor cyan "mrview ${SUBJECTS_DIR}/${sID}/mri/aparc+aseg.nii.gz ${SUBJECTS_DIR}/${sID}/mri/laplace-wm_vec.nii.gz \
  -tractography.load $out_tck -tractography.geometry lines \
  -tractography.load ${out_tck%.tck}_endsOnly.tck -tractography.geometry points"


## Intermodal registration
t1=$SUBJECTS_DIR/$sID/mri/brain.mgz
dwi=

#inb_synthreg.sh