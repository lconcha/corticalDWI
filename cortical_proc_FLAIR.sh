#!/bin/bash
source `which my_do_cmd`
# module load freesurfer/7.3.2

sID=$1;      # subject ID in the form of sub-74277


help() {
  echo "
  Usage: $(basename $0) <subjID>

  <subjID>         subject ID in the form of sub-74277

  This script will process the FLAIR image: <SUBJECTS_DIR>/<sID>/mri/flair.nii.gz
  It will denoise, bias correct, intensity normalize, and register to the T1 volume.
  The processed T1w image will be saved as:
  <SUBJECTS_DIR>/<sID>/mri/flair_proc.nii.gz
  
  "
}


flair=${SUBJECTS_DIR}/${sID}/mri/flair.nii.gz
t1=${SUBJECTS_DIR}/${sID}/mri/T1.mgz
aseg=${SUBJECTS_DIR}/${sID}/mri/aseg.mgz
brainmask=${SUBJECTS_DIR}/${sID}/mri/brainmask.mgz

flair_proc=${SUBJECTS_DIR}/${sID}/mri/flair_proc.nii.gz

if [ -f $flair_proc ]
then
  echolor green "[INFO] Processed flair already exists: $flair_proc"
  echolor green "[INFO] Will not overwrite."
  exit 0
fi

if [ ! -f $flair ]
then
  echolor red "[ERROR] File does not exist: $flair"
  exit 2
fi

tmpDir=$(mktemp -d)

# register to T1 space
t1nii=${tmpDir}/t1.nii
asegnii=${tmpDir}/aseg.nii
brainmasknii=${tmpDir}/brainmasknii.nii
brainmasknii_flairspace=${tmpDir}/brainmasknii_flairspace.nii
asegnii_flairspace=${tmpDir}/aseg_flairspace.nii

my_do_cmd mrconvert $t1 $t1nii
my_do_cmd mrconvert $brainmask $brainmasknii
my_do_cmd mrconvert $aseg $asegnii
my_do_cmd antsIntroduction.sh -d 3 \
  -i $flair \
  -r $t1nii \
  -t RA \
  -o ${tmpDir}/ants_
my_do_cmd WarpImageMultiTransform 3 \
  $asegnii \
  $asegnii_flairspace \
  -i ${tmpDir}/ants_Affine.txt \
  -R $flair \
  --use-NN
my_do_cmd WarpImageMultiTransform 3 \
  $brainmasknii \
  $brainmasknii_flairspace \
  -i ${tmpDir}/ants_Affine.txt \
  -R $flair \
  --use-NN


# Perform N4
flairN4=${tmpDir}/flair_N4.nii
my_do_cmd N4BiasFieldCorrection \
  -x $brainmasknii_flairspace \
  -i $flair \
  -o $flairN4

# denoise
flairDenoised=${tmpDir}/flair_denoised.nii
my_do_cmd DenoiseImage \
  -i $flairN4 \
  -x $brainmasknii_flairspace \
  -o $flairDenoised

# Create mask from WM segmentation
wmmask_flairspace=${tmpDir}/wmmaskflair.nii
my_do_cmd mrcalc \
  $asegnii_flairspace 41 -eq \
  $asegnii_flairspace 2 -eq \
  -add \
  $wmmask_flairspace




# obtain median flair value
medianFlairValue=$(mrstats -quiet -output median \
  -mask $wmmask_flairspace \
  $flairDenoised)

echolor green "[INFO] Median FLAIR value in white matter: $medianFlairValue"

# normalize values by median
flairnormalized=${tmpDir}/flairnormalized.nii
my_do_cmd mrcalc \
  $flairDenoised \
  $medianFlairValue \
  -div \
  $flairnormalized

# Finally, apply transformation to T1 space
my_do_cmd WarpImageMultiTransform 3 \
  $flairnormalized \
  ${tmpDir}/flair_in_t1space.nii \
  -R $t1nii \
  ${tmpDir}/ants_Affine.txt


my_do_cmd mrcalc \
  $brainmasknii  \
  ${tmpDir}/flair_in_t1space.nii\
  -mul \
  $flair_proc

if [ -f $flair_proc ]
then
  echolor green "[INFO] Finished processing FLAIR."
  echolor green "[INFO] Resulting file is $flair_proc"
else
  echolor red "[ERROR] Processing FLAIR finished with error and did not produce output file."
fi



rm -fR $tmpDir
#echolor green "tmpDir is $tmpDir"