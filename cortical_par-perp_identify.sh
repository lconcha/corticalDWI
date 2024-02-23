#!/bin/bash
source `which my_do_cmd`

# Use my custom-made mrtrix function
# must download and compile to $mymrtrix directory
# https://github.com/lconcha/mrtrix3 
mymrtrix=/misc/lauterbur/lconcha/code/mrtrix3
tckfixeldots=${mymrtrix}/bin/tckfixeldots

sID=$1
surf_type=$2
max_angle=60

if [ ! -d ${SUBJECTS_DIR}/${sID} ]
then
  echolor red "[ERROR] Cannot find directory ${SUBJECTS_DIR}/${sID}"
  echolor red "        Check your SUBJECTS_DIR and sID"
  exit 2
fi


tck_lh=${SUBJECTS_DIR}/${sID}/dwi/lh_${surf_type}_laplace-wm-streamlines_dwispace.tck
tck_rh=${SUBJECTS_DIR}/${sID}/dwi/rh_${surf_type}_laplace-wm-streamlines_dwispace.tck
fixels_csd=${SUBJECTS_DIR}/${sID}/dwi/csd_fixels/afd_fixels.nii.gz
fixels_mrds=${SUBJECTS_DIR}/${sID}/dwi/mrds_fixels/directions.mif

isOK=1
for f in $tckfixeldots $tck_lh $tck_rh $fixels_csd
do
  if [ -f "$f" ]
  then
    echolor green "[INFO] Found $f"
  else
    echolor red "[ERROR] File not found: $f"
    isOK=0
  fi
done
if [ $isOK -eq 0 ]; then exit 2; fi



echolor cyan "[INFO] Identifying fixels for CSD"
tsf_lh_csd=${SUBJECTS_DIR}/${sID}/dwi/lh_${surf_type}_laplace-wm-streamlines_dwispace_parIndices_csd.tsf
tsf_rh_csd=${SUBJECTS_DIR}/${sID}/dwi/rh_${surf_type}_laplace-wm-streamlines_dwispace_parIndices_csd.tsf
my_do_cmd $tckfixeldots -angle $max_angle $fixels_csd $tck_lh $tsf_lh_csd
my_do_cmd $tckfixeldots -angle $max_angle $fixels_csd $tck_rh $tsf_rh_csd

echolor cyan "[INFO] Identifying fixels for MRDS"
tsf_lh_mrds=${SUBJECTS_DIR}/${sID}/dwi/lh_${surf_type}_laplace-wm-streamlines_dwispace_parIndices_mrds.tsf
tsf_rh_mrds=${SUBJECTS_DIR}/${sID}/dwi/rh_${surf_type}_laplace-wm-streamlines_dwispace_parIndices_mrds.tsf
my_do_cmd $tckfixeldots -angle $max_angle $fixels_mrds $tck_lh $tsf_lh_mrds
my_do_cmd $tckfixeldots -angle $max_angle $fixels_mrds $tck_rh $tsf_rh_mrds


echo mrview ${SUBJECTS_DIR}/${sID}/dwi/fa.nii.gz \
  -tractography.load $tck_lh \
  -tractography.tsf_load $tsf_lh_csd \
  -tractography.tsf_thresh -1,0.1