#!/bin/bash
source `which my_do_cmd`

help() {
  echo "
  Usage: $(basename $0) <subjID> <nDepths>
  
  <subjID>    subject ID in the form of sub-74277
  <nDepths>   number of depth points to keep in the txt file.
              This is in steps, not mm, 
              and has to be less than or equal to the number of depth points in the tsf file.
  
  This script samples DTI metrics from a tck file and saves them in both tsf and txt formats.

  Matlab is needed for this script, as it calls cortical_tsf2txt_matlab.sh.
  "
}


if [ $# -ne 2 ]
then
  echolor red "Wrong number of arguments"
  help
  exit 0
fi

subjID=$1
nDepths=$2; # number of depth points to keep in the txt file. The tsf saves them all.


    
metrics="fa md ad rd"

for hemi in lh rh
do
  for target_type in fsLR-32k
  do

    tck=${SUBJECTS_DIR}/${subjID}/dwi/${hemi}_${target_type}_laplace-wm-streamlines_dwispace.tck
    
    if [ ! -f $tck ]
    then
      echolor red "[ERROR] File does not exist: $f"
      exit 2
    fi


    for metric in $metrics
    do
      #echolor green "Sampling $metric in $tck in $target_type in $hemi"
      map=${SUBJECTS_DIR}/${subjID}/dwi/${metric}.nii.gz
      tsfout=${SUBJECTS_DIR}/${subjID}/dwi/${hemi}_${target_type}_${metric}.tsf
      if [ -f $tsfout ]
      then
        echolor yellow "[WARN] File exists, will not overwrite: $tsfout"
        echolor yellow "[WARN] Not going to sample any metric."
        exit 0
      fi

      if [ ! -f $map ]
      then
        echolor red "[ERROR] File does not exist: $map"
        exit 2
      fi
      my_do_cmd   tcksample  $tck $map $tsfout
    done
  done
done



my_do_cmd cortical_tsf2txt_matlab.sh ${SUBJECTS_DIR}/${subjID}/dwi/ $nDepths