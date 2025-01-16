#!/bin/bash
source `which my_do_cmd`

subjID=$1
fixel_dir=$2; # csd_fixels or mrds_fixels (or something else)
angle=$3



isOK=1

fixel_dir=${SUBJECTS_DIR}/${subjID}/dwi/${fixel_dir}
if [ ! -d $fixel_dir ]
then
  echolor red "[ERROR] Fixel directory does not exist: $fixel_dir"
  isOK=0
  #exit 2
fi


for hemi in lh rh
do
  for target_type in fsLR-5k fsLR-32k
  do

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
      echolor yellow "[WARN] File exists, will not overwrite: $fcheck"
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
  done
done

nDepths=20
for tsf in ${fixel_dir}/*.tsf
do
  txt=${tsf%.tsf}.txt
  my_do_cmd  cortical_tsf2txt_matlab.sh $tsf $txt $nDepths
done