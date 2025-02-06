#!/bin/bash
source `which my_do_cmd`
# module load freesurfer/7.3.2

sID=$1;      # subject ID in the form of sub-74277
flair=$2;   # full path to preprocessed dwi.mif
             # example /misc/lauterbur/lconcha/TMP/glaucoma/bids/derivatives/sub-74277/dwi/sub-74277_acq-hb_dwi_de.mif

outflair=${SUBJECTS_DIR}/${sID}/mri/flair.nii.gz


vers=$(recon-all -version | grep 7.3)
echo $vers
if [ -z "$vers" ]
then
  echolor red "[ERROR] Please load module for freesurfer 7.3"
  exit 2
else
  echolor green "[INFO] Using: $vers"
fi




if [ ! -d ${SUBJECTS_DIR}/${sID} ]
then
  echolor red "[ERROR] Cannot find directory ${SUBJECTS_DIR}/${sID}"
  echolor red "        Check your SUBJECTS_DIR and sID"
  exit 2
fi

t1=${SUBJECTS_DIR}/${sID}/mri/brain.mgz


if [ ! -f $flair ]; then echolor red "[ERROR] Cannot find file: $flair"; exit 2;fi
if [ ! -f $t1 ];    then echolor red "[ERROR] Cannot find file: $t1"; exit 2;fi


tmpDir=$(mktemp -d)

my_do_cmd mri_synthstrip \
  -i $flair \
  -o ${tmpDir}/flair_brain.nii.gz

my_do_cmd N4BiasFieldCorrection \
  -d 3 \
  -i ${tmpDir}/flair_brain.nii.gz \
  -o ${tmpDir}/flair_brain_biascorrected.nii

my_do_cmd mrconvert $t1 ${tmpDir}/t1.nii
t1=${tmpDir}/t1.nii

my_do_cmd flirt \
  -in ${tmpDir}/flair_brain_biascorrected.nii \
  -ref $t1 \
  -dof 6 \
  -out ${tmpDir}/flair_brain_biascorrected_to-t1.nii.gz


wm_mask=${SUBJECTS_DIR}/${sID}/mri/wm.seg.mgz
wm_value=110; # this is the value of WM in the fs automatic segmentation
my_do_cmd mrcalc $wm_mask $wm_value -eq ${tmpDir}/wm_mask.nii
median_wm_value=$(mrstats -mask ${tmpDir}/wm_mask.nii ${tmpDir}/flair_brain_biascorrected_to-t1.nii.gz -output median)
echolor green "[INFO] Median FLAIR value in white matter: $median_wm_value"
my_do_cmd mrcalc \
  ${tmpDir}/flair_brain_biascorrected_to-t1.nii.gz \
  $median_wm_value -div \
  $outflair


flair_mag=${outflair%.nii.gz}_grad.nii.gz
my_do_cmd ImageMath 3 $flair_mag Grad $outflair 0.5 1


t1=${SUBJECTS_DIR}/${sID}/mri/brain.mgz
echolor green "[INFO] Done. Check with:"
echolor green "       mrview $t1 $outflair $flair_mag"






rm -fR $tmpDir





# my_do_cmd antsIntroduction.sh \
#   -d 3 \
#   -t RI \
#   -s MI \
#   -n 1 \
#   -i $flair \
#   -r $t1 \
#   -o ${SUBJECTS_DIR}/${sID}/mri/flair_brain