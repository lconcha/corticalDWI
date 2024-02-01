#!/bin/bash
source `which my_do_cmd`

# Use my custom-made mrtrix function
# must download and compile to $mymrtrix directory
# https://github.com/lconcha/mrtrix3 
mymrtrix=/misc/lauterbur/lconcha/code/mrtrix3
tckfixeldots=${mymrtrix}/bin/tckfixeldots

sID=$1
surf_type=$2

if [ ! -d ${SUBJECTS_DIR}/${sID} ]
then
  echolor red "[ERROR] Cannot find directory ${SUBJECTS_DIR}/${sID}"
  echolor red "        Check your SUBJECTS_DIR and sID"
  exit 2
fi


# fcheck=${SUBJECTS_DIR}/${sID}/dwi/t1native_to_b0_1Warp.nii.gz
# if [ -f $fcheck ]
# then
#   echolor orange "[INFO] File found $fcheck"
#   echolor orange "       Will not overwrite. Exitting now."
#   exit 0
# fi

tck_lh=${SUBJECTS_DIR}/${sID}/dwi/lh_${surf_type}_laplace-wm-streamlines_dwispace.tck
tck_rh=${SUBJECTS_DIR}/${sID}/dwi/rh_${surf_type}_laplace-wm-streamlines_dwispace.tck
fixels_csd=${SUBJECTS_DIR}/${sID}/dwi/csd_fixels/directions.mif

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




tsf_lh=${SUBJECTS_DIR}/${sID}/dwi/lh_${surf_type}_laplace-wm-streamlines_dwispace_parIndices_csd.tsf
tsf_rh=${SUBJECTS_DIR}/${sID}/dwi/rh_${surf_type}_laplace-wm-streamlines_dwispace_parIndices_csd.tsf
my_do_cmd $tckfixeldots $fixels_csd $tck_lh $tsf_lh
my_do_cmd $tckfixeldots $fixels_csd $tck_rh $tsf_rh