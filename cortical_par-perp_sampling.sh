#!/bin/bash
source `which my_do_cmd`

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
#mrds_PDD=${SUBJECTS_DIR}/${sID}/dwi/${sID}_MRDS_Diff_BIC_PDDs_CARTESIAN.nii.gz


isOK=1
for f in $tck_lh $tck_rh $mrds_PDD
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


csd_fixeldir=${SUBJECTS_DIR}/${sID}/dwi/csd_fixels
my_do_cmd fixel2voxel \
  ${csd_fixeldir}/afd_fixels.nii.gz \
  none \
  ${csd_fixeldir}/afd_voxel.nii.gz


#peaks2fixel $mrds_PDD $mrds_fixeldir