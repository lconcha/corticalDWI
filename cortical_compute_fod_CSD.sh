#!/bin/bash
source `which my_do_cmd`

sID=$1


help() {
  echo "
  Usage:
    $(basename $0) <subjID> 

  Compute multi-tissue and singletissue FODs using group-average response functions.
  "
}

if [ $# -lt 1 ]
then
  help
  exit 1
fi

# dir where group responses are located
group_response_dir=${SUBJECTS_DIR}/grupalresponse

# dwi variables
dwi=${SUBJECTS_DIR}/${sID}/dwi/dwi.nii.gz
scheme=${SUBJECTS_DIR}/${sID}/dwi/dwi.scheme
mask=${SUBJECTS_DIR}/${sID}/dwi/mask.nii.gz

# group responses 
group_resp_wm=${group_response_dir}/grupalresponse_wm.txt
group_resp_gm=${group_response_dir}/grupalresponse_gm.txt
group_resp_csf=${group_response_dir}/grupalresponse_csf.txt


# Compute multitissue fod's and fixels
echolor green "[INFO] Performing multi-tissue CSD"

fod_wm=${SUBJECTS_DIR}/${sID}/dwi/fod_wm.mif
fod_gm=${SUBJECTS_DIR}/${sID}/dwi/fod_gm.mif
fod_csf=${SUBJECTS_DIR}/${sID}/dwi/fod_csf.mif

my_do_cmd dwi2fod msmt_csd \
  -mask $mask \
  -grad $scheme \
  $dwi \
  $group_resp_wm $fod_wm \
  $group_resp_gm $fod_gm \
  $group_resp_csf $fod_csf

csd_fixeldir=${SUBJECTS_DIR}/${sID}/dwi/csd_fixels

my_do_cmd fod2fixel \
  -afd afd_fixels.mif \
  -peak peak_fixels.mif \
  -disp disp_fixels.mif \
  $fod_wm \
  $csd_fixeldir



# Compute single tissue fod's and fixels
echolor green "[INFO] Performing single-tissue WM CSD"

fod_wm_single=${SUBJECTS_DIR}/${sID}/dwi/fod_wm_singletissue.mif

my_do_cmd dwi2fod msmt_csd \
  -mask $mask \
  -grad $scheme \
  $dwi \
  $group_resp_wm $fod_wm_single

csd_fixeldir=${SUBJECTS_DIR}/${sID}/dwi/csd_fixels_singletissue

my_do_cmd fod2fixel \
  -afd afd_fixels.mif \
  -peak peak_fixels.mif \
  -disp disp_fixels.mif \
  $fod_wm_single \
  $csd_fixeldir