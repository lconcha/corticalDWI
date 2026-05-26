#!/bin/bash
source `which my_do_cmd`


sID=$1;      # subject ID in the form of sub-74277

help() {
  echo "
  Usage: $(basename $0) <subjID>

  <subjID>         subject ID in the form of sub-74277

  This script will compute DTI metrics using mrtrix.

  "
}


if [ $# -lt 1 ]
then
  echolor red "[ERROR] Not enough arguments"
  help
  exit 0
fi


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

isOK=1
for f in $dwi $mask $scheme
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


dwi2tensor -mask $mask \
    -grad $scheme \
    $dwi \
    - | \
tensor2metric - \
    -fa ${SUBJECTS_DIR}/${sID}/dwi/fa.nii.gz \
    -adc ${SUBJECTS_DIR}/${sID}/dwi/md.nii.gz \
    -ad ${SUBJECTS_DIR}/${sID}/dwi/ad.nii.gz \
    -rd ${SUBJECTS_DIR}/${sID}/dwi/rd.nii.gz \
    -vector ${SUBJECTS_DIR}/${sID}/dwi/v1.nii.gz