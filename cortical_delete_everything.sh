#!/bin/bash

subjid=$1



rm ${SUBJECTS_DIR}/${subjid}/mri/laplace-*
rm ${SUBJECTS_DIR}/${subjid}/mri/?h_fsLR-*tck
rm ${SUBJECTS_DIR}/${subjid}/mri/aparc+aseg.nii.gz
rm -fR ${SUBJECTS_DIR}/${subjid}/mri/split

rm ${SUBJECTS_DIR}/${subjid}/surf/*fsLR*.gii

rm -fR ${SUBJECTS_DIR}/${subjid}/dwi