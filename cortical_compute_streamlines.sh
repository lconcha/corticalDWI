#!/bin/bash
source `which my_do_cmd`

sID=$1
hemi=$2
target_type=$3
nsteps=$4; #200
step_size=$5; #"0.1"
tck_step_size=0.5

CODEDIR=$(dirname $0)

help() {
  echo "
  Usage: $(basename $0) <subjID> <hemi> <target_type> <nsteps> <step_size>

  <subjID>         subject ID in the form of sub-74277
  <hemi>           hemisphere (lh or rh)
  <target_type>    type of target (e.g., 'fsLR-32k')
  <nsteps>         number of steps to take along the streamline (suggested: 200)
  <step_size>      step size in mm (suggested: '0.1')

  Please note that the tck is resampled to a step size of ${tck_step_size} mm at the end of the process.

  This script will compute streamlines from the white matter surface to the pial surface
  using the Laplacian field.
  "
}

if [ $# -ne 5 ]
then
  echolor red "Incorrect number of arguments"
  help
  exit 0
fi


surf_white=${SUBJECTS_DIR}/${sID}/surf/${hemi}_white_${target_type}.surf.gii
surf_pial=${SUBJECTS_DIR}/${sID}/surf/${hemi}_pial_${target_type}.surf.gii
in_vec=${SUBJECTS_DIR}/${sID}/mri/laplace-wm_vec.nii.gz


## NOTE THis is now done inside cortical_resample_surface.sh
# convert surfaces to scanner coordinates
# my_do_cmd mris_convert --to-scanner \
#   $surf_white \
#   ${SUBJECTS_DIR}/${sID}/surf/${hemi}_white_${target_type}_scanner.surf.gii
# surf_white=${SUBJECTS_DIR}/${sID}/surf/${hemi}_white_${target_type}_scanner.surf.gii
# my_do_cmd mris_convert --to-scanner \
#   $surf_pial \
#   ${SUBJECTS_DIR}/${sID}/surf/${hemi}_pial_${target_type}_scanner.surf.gii
# surf_pial=${SUBJECTS_DIR}/${sID}/surf/${hemi}_pial_${target_type}_scanner.surf.gii


#in_surf=${SUBJECTS_DIR}/${sID}/surf/${hemi}_white_scanner.surf.gii



tmp_tck=/tmp/temp_$$.tck
tmp_tck_withheader=/tmp/temp2_$$.tck
out_tck=${SUBJECTS_DIR}/${sID}/mri/${hemi}_${target_type}_laplace-wm-streamlines.tck
my_do_cmd python $CODEDIR/cortical_streamlines.py \
  $surf_white \
  $surf_pial \
  $in_vec \
  $nsteps \
  $step_size \
  $tmp_tck
my_do_cmd tckedit -force -quiet $tmp_tck $tmp_tck_withheader; # this will put a header that cortical_treamlines.py cannot write
my_do_cmd tckresample_and_truncate $tmp_tck_withheader $out_tck --step_size $tck_step_size
rm $tmp_tck $tmp_tck_withheader


my_do_cmd tckresample -force -quiet -endpoints $out_tck ${out_tck%.tck}_endsOnly.tck

echolor cyan "mrview ${SUBJECTS_DIR}/${sID}/mri/aparc+aseg.nii.gz ${SUBJECTS_DIR}/${sID}/mri/laplace-wm_vec.nii.gz \
  -tractography.load $out_tck -tractography.geometry lines \
  -tractography.load ${out_tck%.tck}_endsOnly.tck -tractography.geometry points"