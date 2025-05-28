#!/bin/bash
source `which my_do_cmd`

help() {
  echo "
  Usage: $(basename $0) <subjID> <fixel_dir> <angle> <nDepths>
  
  <subjID>     subject ID in the form of sub-74277
  <fixel_dir>  directory containing fixel files, e.g., csd_fixel
  <angle>      Maximum angle (in degrees) between the streamline and the fixel direction.
               This is in degrees, e.g., 45.
  <nDepths>    number of depth points to keep in the txt file.
               This is in steps, not mm,
               and has to be less than or equal to the number of depth points in the tsf file.

  Only AFD values are sampled, and separated into parallel and perpendicular components.
  Perpendicular can be defined in two ways:
  - The fixel with the lowest dot product to the streamline segment (afd-perp)
  - The average of all fixels except for the most parallel to the streamline segment (afd-perp-av)
  "
}

if [ $# -ne 4 ]
then
  echolor red "Wrong number of arguments"
  help
  exit 0
fi


subjID=$1
fixel_dir=$2; # csd_fixels
angle=$3
nDepths=$4; # number of depth points to keep in the txt file. The tsf saves them all.


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


# for tsf in ${fixel_dir}/*.tsf
# do
#   txt=${tsf%.tsf}.txt
#   my_do_cmd  cortical_tsf2txt_matlab.sh $tsf $txt $nDepths
# done

cortical_tsf2txt_matlab.sh $fixel_dir $nDepths