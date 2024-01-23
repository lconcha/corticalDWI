#!/bin/bash

sID=$1

if [ ! -d ${SUBJECTS_DIR}/${sID} ]
then
  echolor red "[ERROR] Cannot find directory ${SUBJECTS_DIR}/${sID}"
  echolor red "        Check your SUBJECTS_DIR and sID"
  exit 2
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
  -threads_max \
  -neocortex