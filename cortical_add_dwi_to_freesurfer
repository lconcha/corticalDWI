#!/bin/bash
source `which my_do_cmd`


sID=$1;      # subject ID in the form of sub-74277
dwimif=$2;   # full path to preprocessed dwi.mif
             # example /misc/lauterbur/lconcha/TMP/glaucoma/bids/derivatives/sub-74277/dwi/sub-74277_acq-hb_dwi_de.mif



if [ ! -d ${SUBJECTS_DIR}/${sID} ]
then
  echolor red "[ERROR] Cannot find directory ${SUBJECTS_DIR}/${sID}"
  echolor red "        Check your SUBJECTS_DIR and sID"
  exit 2
fi


mkdir -p ${SUBJECTS_DIR}/${sID}/dwi

dwinii=${SUBJECTS_DIR}/${sID}/dwi/dwi.nii.gz
bvec=${SUBJECTS_DIR}/${sID}/dwi/dwi.bvec
bval=${SUBJECTS_DIR}/${sID}/dwi/dwi.bval
scheme=${SUBJECTS_DIR}/${sID}/dwi/dwi.scheme

mrconvert -strides 1,2,3,4 \
  -export_grad_fsl $bvec $bval \
  -export_grad_mrtrix $scheme \
  $dwimif \
  $dwinii

sed -i '/^#/d' $scheme

maskdwi=${SUBJECTS_DIR}/${sID}/dwi/mask.nii.gz
b0=${SUBJECTS_DIR}/${sID}/dwi/b0.nii.gz
dt=${SUBJECTS_DIR}/${sID}/dwi/dt.nii.gz
fa=${SUBJECTS_DIR}/${sID}/dwi/fa.nii.gz
md=${SUBJECTS_DIR}/${sID}/dwi/md.nii.gz
ad=${SUBJECTS_DIR}/${sID}/dwi/ad.nii.gz
rd=${SUBJECTS_DIR}/${sID}/dwi/rd.nii.gz
v1=${SUBJECTS_DIR}/${sID}/dwi/v1.nii.gz

dwi2mask   -fslgrad $bvec $bval $dwinii $maskdwi
dwiextract -fslgrad $bvec $bval -bzero $dwinii - | \
  mrmath -axis 3 - mean - | \
  mrcalc $maskdwi - -mul $b0
dwi2tensor -mask $maskdwi -fslgrad $bvec $bval $dwinii $dt
tensor2metric \
  -fa  $fa \
  -adc $md \
  -rd  $rd \
  -ad  $ad \
  -vector $v1 \
  $dt