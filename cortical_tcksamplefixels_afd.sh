#!/bin/bash
source `which my_do_cmd`

subjID=$1
hemi=$2
target_type=$3; # fsLR-5k or fsLR-32k
fixel_dir=$4; # csd_fixels or mrds_fixels (or something else)
angle=$5



isOK=1

fixel_dir=${SUBJECTS_DIR}/${subjID}/dwi/${fixel_dir}
if [ ! -d $fixel_dir ]
then
  echolor red "[ERROR] Fixel directory does not exist: $fixel_dir"
  isOK=0
  #exit 2
fi


tck=${SUBJECTS_DIR}/${subjID}/dwi/${hemi}_${target_type}_laplace-wm-streamlines_dwispace.tck
afd=${fixel_dir}/afd_fixels.mif
for f in $tck $afd
do
  if [ ! -f $f ]
  then
    echolor red "[ERROR] Cannot find file: $f"
    isOK=0
  else
    echolor green "[INFO] Found file: $f"
  fi
done


fcheck=${fixel_dir}/${hemi}_${target_type}_afd-par-perp-indices.tsf
echo "looking for $fcheck"
if [ -f $fcheck ]
then
  echolor red "[ERROR] File exists, will not overwrite: $fcheck"
  exit 0
fi


if [ $isOK -eq 1 ]
then
  my_do_cmd tcksamplefixels \
  -angle $angle \
  $afd \
  $tck \
  ${fixel_dir}/${hemi}_${target_type}_afd-par-perp-indices.tsf \
  ${fixel_dir}/${hemi}_${target_type}_afd-par.tsf \
  ${fixel_dir}/${hemi}_${target_type}_afd-perp.tsf \
  ${fixel_dir}/${hemi}_${target_type}_afd-perp-av.tsf
else
  echolor red "[ERROR] Cannot continue, see above errors"
  exit 2
fi
