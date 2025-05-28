#!/bin/bash
source `which my_do_cmd`

sID=$1
CODEDIR=$(dirname $0)

help() {
  echo "
  Usage: $(basename $0) <subjID>

  <subjID>         subject ID in the form of sub-74277

  This script will calculate the Laplacian field for the given subject.
  It requires the aparc+aseg.mgz file to be present in the subject's mri directory.

  Important:
  The heart of this script is the laplace_solver.py script, which computes the Laplacian field
  from the white matter segmentation and outputs a vector field in NIFTI format. 
  It was written by Jordan DeKraker and is available at:
  https://github.com/khanlab/hippunfold/blob/master/hippunfold/workflow/scripts/laplace_coords.py

  "
}


if [ $# -lt 1 ]
then
  echolor red "[ERROR] Not enough arguments"
  help
  exit 0
fi

### Laplacian field
echolor cyan "[INFO] Calculating Laplace Field"

# Convert segmentation to NIFTI
mri_convert ${SUBJECTS_DIR}/${sID}/mri/aparc+aseg.mgz \
            ${SUBJECTS_DIR}/${sID}/mri/aparc+aseg.nii.gz

# Calculate the Laplace field
fcheck=${SUBJECTS_DIR}/${sID}/mri/laplace-wm_vec.nii.gz
if [ -f $fcheck ]
then
  echolor cyan "[INFO] File exists: $fcheck"
else
  echolor cyan "[INFO] Calling laplace_solver.py"
  python ${CODEDIR}/sWM/laplace_solver.py \
    ${SUBJECTS_DIR}/${sID}/mri/aparc+aseg.nii.gz \
    ${SUBJECTS_DIR}/${sID}/mri/laplace-wm
  my_do_cmd mrcat -axis 3 \
    ${SUBJECTS_DIR}/${sID}/mri/laplace-wm_d{x,y,z}.nii.gz \
    ${SUBJECTS_DIR}/${sID}/mri/laplace-wm_vec.nii.gz
fi
echo "Done."