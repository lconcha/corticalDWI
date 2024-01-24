#!/bin/bash
source `which my_do_cmd`

sID=$1
hemi=$2
target_type=$3
nsteps=$4; #200
step_size=$5; #"0.1"
tck_step_size=0.5

CODEDIR=$(dirname $0)




surf_white=${SUBJECTS_DIR}/${sID}/surf/${hemi}_white_${target_type}.surf.gii
surf_pial=${SUBJECTS_DIR}/${sID}/surf/${hemi}_pial_${target_type}.surf.gii
in_vec=${SUBJECTS_DIR}/${sID}/mri/laplace-wm_vec.nii.gz


# convert surfaces to scanner coordinates
my_do_cmd mris_convert --to-scanner \
  $surf_white \
  ${SUBJECTS_DIR}/${sID}/surf/${hemi}_white_${target_type}_scanner.surf.gii
surf_white=${SUBJECTS_DIR}/${sID}/surf/${hemi}_white_${target_type}_scanner.surf.gii
my_do_cmd mris_convert --to-scanner \
  $surf_pial \
  ${SUBJECTS_DIR}/${sID}/surf/${hemi}_pial_${target_type}_scanner.surf.gii
surf_pial=${SUBJECTS_DIR}/${sID}/surf/${hemi}_pial_${target_type}_scanner.surf.gii


#in_surf=${SUBJECTS_DIR}/${sID}/surf/${hemi}_white_scanner.surf.gii



tmp_tck=/tmp/temp_$$.tck
out_tck=${SUBJECTS_DIR}/${sID}/mri/${hemi}_${target_type}_laplace-wm-streamlines.tck
my_do_cmd python $CODEDIR/cortical_streamlines.py \
  $surf_white \
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