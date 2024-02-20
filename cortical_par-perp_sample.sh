#!/bin/bash
source `which my_do_cmd`

sID=$1
hemi=$2
surf_type=$3

if [ ! -d ${SUBJECTS_DIR}/${sID} ]
then
  echolor red "[ERROR] Cannot find directory ${SUBJECTS_DIR}/${sID}"
  echolor red "        Check your SUBJECTS_DIR and sID"
  exit 2
fi


tmpDir=$(mktemp -d)

tck=${SUBJECTS_DIR}/${sID}/dwi/${hemi}_${surf_type}_laplace-wm-streamlines_dwispace.tck
FA4D=${SUBJECTS_DIR}/${sID}/dwi/${sID}_MRDS_Diff_BIC_FA.nii.gz
MD4D=${SUBJECTS_DIR}/${sID}/dwi/${sID}_MRDS_Diff_BIC_MD.nii.gz
COMP4D=${SUBJECTS_DIR}/${sID}/dwi/${sID}_MRDS_Diff_BIC_COMP_SIZE.nii.gz

for t in $(seq 0 2)
do
  for f in $FA4D $MD4D $COMP4D
  do
    my_do_cmd mrconvert -force -quiet \
      -coord 3 $t \
      $f \
      ${tmpDir}/file_to_sample.mif
    tsfout=${SUBJECTS_DIR}/${sID}/dwi/mrds_fixels/$(basename ${f%.nii.gz})_${t}.tsf
    my_do_cmd tcksample \
      $tck ${tmpDir}/file_to_sample.mif \
      $tsfout
  done
done



rm -fRv $tmpDir