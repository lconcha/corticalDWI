#!/bin/bash
source `which my_do_cmd`

subjID=$1
nDepths=$2; # number of depth points to keep in the txt file. The tsf saves them all.


metrics="fa md ad rd"


for hemi in lh rh
do
  for target_type in fsLR-5k fsLR-32k
  do

    tck=${SUBJECTS_DIR}/${subjID}/dwi/${hemi}_${target_type}_laplace-wm-streamlines_dwispace.tck
    
    if [ ! -f $tck ]
    then
      echolor red "[ERROR] File does not exist: $f"
      exit 2
    fi
    
    for metric in $metrics
    do
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
      
      my_do_cmd  tcksample $tck $map $tsfout

    done


  done
done



my_do_cmd cortical_tsf2txt_matlab.sh ${SUBJECTS_DIR}/${subjID}/dwi/ $nDepths