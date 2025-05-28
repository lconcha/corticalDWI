#!/bin/bash
source `which my_do_cmd`


help() {
  echo "
  Usage: $(basename $0) <subjID> <hemi> <target_type> <fixel_dir>

  <subjID>         subject ID in the form of sub-74277
  <hemi>           hemisphere (lh or rh)
  <target_type>    type of target (e.g., 'fsLR-32k')
  <fixel_dir>      directory containing fixels (e.g., csd_fixels or mrds_fixels)

  Will compute the dot product between each streamline segment and the underlying fixels,

  
  "
}


subjID=$1
hemi=$2
target_type=$3
fixel_dir=$4; # csd_fixels or mrds_fixels (or something else)


tck=${SUBJECTS_DIR}/${subjID}/dwi/${hemi}_${target_type}_laplace-wm-streamlines_dwispace.tck
fixel_dir=${SUBJECTS_DIR}/${subjID}/dwi/${fixel_dir}
dots=${hemi}_fsLR_${target_type}_fixeldots.mif

isOK=1

if [ ! -f $tck ]
then
  echolor red "[ERROR] Cannot find file: $tck"
  isOK=0
fi

if [ ! -d $fixel_dir ]
then
  echolor red "[ERROR] Fixel directory does not exist: $fixel_dir"
  isOK=0
fi

if [ -f ${fixel_dir}/${dots} ]
then
  echolor yellow "[WARN] File exists. Not overwriting: ${fixel_dir}/${dots}"
  echolor green "[INFO] Check result with:"
  echolor green "       mrview ${subjID}/dwi/fa.nii.gz -tractography.load $tck -tractography.colour 0,0,1 -fixel.load ${fixel_dir}/${dots}"
  isOK=0
fi


if [ $isOK -eq 1 ]
then
my_do_cmd  tck2fixeldots \
    $tck \
    $fixel_dir \
    $fixel_dir \
    $dots
fi

echolor green "[INFO] Check result with:"
echolor green "       mrview ${SUBJECTS_DIR}/${subjID}/dwi/fa.nii.gz \
                        -tractography.load $tck \
                        -fixel.load ${fixel_dir}/${dots}"