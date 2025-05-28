#!/bin/bash

sID=$1


help() {
  echo "
  Usage: $(basename $0) <subjID>

  <subjID>         subject ID in the form of sub-74277

  This script will register the T1 image to the b0 image in the DWI folder.
  It will create a set of files in the DWI folder:
  - t1native_to_b0_1Warp.nii.gz
  - t1native_to_b0_0GenericAffine.mat
  - t1native_to_b0.nii.gz
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


fcheck=${SUBJECTS_DIR}/${sID}/dwi/t1native_to_b0_1Warp.nii.gz
if [ -f $fcheck ]
then
  echolor orange "[INFO] File found $fcheck"
  echolor orange "       Will not overwrite. Exitting now."
  exit 0
fi


## Intermodal registration
t1=${SUBJECTS_DIR}/${sID}/mri/brain.mgz
b0=${SUBJECTS_DIR}/${sID}/dwi/b0.nii.gz



isOK=1
for f in $t1 $b0
do
  if [ -f "$f" ]
  then
    echo "."
  else
    echolor red "[ERROR] File not found: $f"
    isOK=0
  fi
done
if [ $isOK -eq 0 ]; then exit 2; fi



inb_synthreg.sh \
  -fixed $b0 \
  -moving $t1 \
  -outbase ${SUBJECTS_DIR}/${sID}/dwi/t1native_to_b0_ \
  -threads_max