#!/bin/bash
source `which my_do_cmd`
# module load freesurfer/7.3.2

sID=$1;      # subject ID in the form of sub-74277


help() {
  echo "
  Usage: $(basename $0) <subjID>

  <subjID>         subject ID in the form of sub-74277

  This script will process the T1w image: <SUBJECTS_DIR>/<sID>/mri/orig.mgz
  It will denoise, bias correct, and create the gradient image.
  The processed T1w image will be saved as:
  <SUBJECTS_DIR>/<sID>/mri/T1w_proc.nii.gz
  The gradient image will be saved as:
  <SUBJECTS_DIR>/<sID>/mri/T1w_proc_grad.nii.gz

  Oddly, this script needs freesurfer 7.3.2.
  "
}

if [ $# -lt 1 ]
then
  echolor red "[ERROR] Not enough arguments"
  help
  exit 0
fi




T1w=$SUBJECTS_DIR/${sID}/mri/orig.mgz
outT1w=${SUBJECTS_DIR}/${sID}/mri/T1w_proc.nii.gz

if [ ! -z "$T1w" -a -f $T1w ]
then
  echolor green "[INFO] Found T1w image: $T1w"
else
  echolor red "[ERROR] Did not find T1w image"
  exit 2
fi



echolor cyan "Forcing freesurfer 7.3.2"
export subjects_dir=$SUBJECTS_DIR
module unload freesurfer
module load freesurfer/7.3.2
export SUBJECTS_DIR=$subjects_dir
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


tmpDir=$(mktemp -d)

my_do_cmd mrconvert $T1w ${tmpDir}/T1w.nii

my_do_cmd DenoiseImage -d 3 -v \
  -i ${tmpDir}/T1w.nii \
  -o ${tmpDir}/T1w_denoised.nii

T1w_brain=$SUBJECTS_DIR/${sID}/mri/brain.mgz
my_do_cmd mrcalc \
  $T1w_brain \
  0 -gt \
  ${tmpDir}/T1w_denoised.nii \
  -mul \
  ${tmpDir}/T1w_brain.nii


# my_do_cmd mri_synthstrip \
#   -i $T1w \
#   -o ${tmpDir}/T1w_brain.nii.gz


my_do_cmd N4BiasFieldCorrection \
  -d 3 \
  -i ${tmpDir}/T1w_brain.nii \
  -o ${tmpDir}/T1w_brain_biascorrected.nii


wm_mask=${SUBJECTS_DIR}/${sID}/mri/wm.seg.mgz
wm_value=110; # this is the value of WM in the fs automatic segmentation
my_do_cmd mrcalc $wm_mask $wm_value -eq ${tmpDir}/wm_mask.nii
median_wm_value=$(mrstats -mask ${tmpDir}/wm_mask.nii ${tmpDir}/T1w_brain_biascorrected.nii -output median)
echolor green "[INFO] Median T1w value in white matter: $median_wm_value"
my_do_cmd mrcalc \
  ${tmpDir}/T1w_brain_biascorrected.nii \
  $median_wm_value -div \
  $outT1w


T1w_mag=${outT1w%.nii.gz}_grad.nii.gz
my_do_cmd ImageMath 3 $T1w_mag Grad $outT1w 0.5 1


fs_T1w_brain=${SUBJECTS_DIR}/${sID}/mri/brain.mgz
echolor green "[INFO] Done. Check with:"
echolor green "       mrview $fs_T1w_brain $outT1w $T1w_mag"






rm -fR $tmpDir





# my_do_cmd antsIntroduction.sh \
#   -d 3 \
#   -t RI \
#   -s MI \
#   -n 1 \
#   -i $T1w \
#   -r $t1 \
#   -o ${SUBJECTS_DIR}/${sID}/mri/T1w_brain