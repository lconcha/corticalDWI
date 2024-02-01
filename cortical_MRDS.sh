#!/bin/bash
source `which my_do_cmd`


sID=$1;      # subject ID in the form of sub-74277

if [ ! -d ${SUBJECTS_DIR}/${sID} ]
then
  echolor red "[ERROR] Cannot find directory ${SUBJECTS_DIR}/${sID}"
  echolor red "        Check your SUBJECTS_DIR and sID"
  exit 2
fi


dwi=${SUBJECTS_DIR}/${sID}/dwi/dwi.nii.gz
bvec=${SUBJECTS_DIR}/${sID}/dwi/dwi.bvec
bval=${SUBJECTS_DIR}/${sID}/dwi/dwi.bval
scheme=${SUBJECTS_DIR}/${sID}/dwi/dwi.scheme
mask=${SUBJECTS_DIR}/${sID}/dwi/mask.nii.gz
outbase=${SUBJECTS_DIR}/${sID}/dwi/${sID}
nVoxPerJob=1000
scratch_dir=${SUBJECTS_DIR}/${sID}/dwi/tmp/


fcheck=${outbase}_MRDS_Diff_BIC_FA.nii.gz
echo "Looking for file: $fcheck"
if [ -f $fcheck ]
then
  echolor orange "[INFO] File found $fcheck"
  echolor orange "       Will not overwrite. Exiting now."
  exit 0
fi


isOK=1
for f in $dwi $scheme $mask
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


my_do_cmd  inb_mrds_sge.sh \
  $dwi \
  $scheme \
  $mask \
  $outbase \
  $nVoxPerJob \
  $scratch_dir