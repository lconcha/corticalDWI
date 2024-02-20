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



resp_wm=${SUBJECTS_DIR}/${sID}/dwi/response_wm.txt
resp_gm=${SUBJECTS_DIR}/${sID}/dwi/response_gm.txt
resp_csf=${SUBJECTS_DIR}/${sID}/dwi/response_csf.txt

my_do_cmd dwi2response dhollander \
  -mask $mask \
  -grad $scheme \
  $dwi \
  $resp_wm $resp_gm $resp_csf


fod_wm=${SUBJECTS_DIR}/${sID}/dwi/fod_wm.nii.gz
fod_gm=${SUBJECTS_DIR}/${sID}/dwi/fod_gm.nii.gz
fod_csf=${SUBJECTS_DIR}/${sID}/dwi/fod_csf.nii.gz

my_do_cmd dwi2fod msmt_csd \
  -mask $mask \
  -grad $scheme \
  $dwi \
  $resp_wm $fod_wm \
  $resp_gm $fod_gm \
  $resp_csf $fod_csf

csd_fixeldir=${SUBJECTS_DIR}/${sID}/dwi/csd_fixels
my_do_cmd fod2fixel \
  -fmls_no_thresholds \
  -afd afd_fixels.nii.gz \
  -peak peak_fixels.nii.gz \
  -disp disp_fixels.nii.gz \
  $fod_wm \
  $csd_fixeldir