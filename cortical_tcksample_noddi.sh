#!/bin/bash
source `which my_do_cmd`

help() {
  echo "
  Usage: $(basename $0) <subjID> <nDepths> <target_type>
  
  <subjID>    subject ID in the form of sub-74277
  <nDepths>   number of depth points to keep in the txt file.
              This is in steps, not mm, 
              and has to be less than or equal to the number of depth points in the tsf file.
  <target_type>  target type, e.g.  ico6_sym
  This script samples DKI metrics from a tck file and saves them in  tsf format.

  "
}


if [ $# -lt 1 ]
then
  echolor red "Wrong number of arguments (subjID is required)"
  help
  exit 0
fi

# ── Defaults / config / CLI args ──────────────────────────────────────────────
nDepths=30
target_type=ico6_sym
source cortical_load_params.sh 2>/dev/null || true
subjID=$1
[ -n "$2" ] && nDepths=$2
[ -n "$3" ] && target_type=$3


fcheck=${SUBJECTS_DIR}/${subjID}/dwi/noddi/lh_${target_type}_ODI.tsf
if [ -f $fcheck ]
then
  echolor green "[INFO] File exists, will not overwrite: $fcheck"
  exit 0
fi

    
metrics="FWF NDI ODI"

for hemi in lh rh
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
    map=${SUBJECTS_DIR}/${subjID}/dwi/noddi/${metric}.nii.gz
    tsfout=${SUBJECTS_DIR}/${subjID}/dwi/noddi/${hemi}_${target_type}_${metric}.tsf
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
    my_do_cmd   cortical_tcksample_safe.sh  $tck $map $tsfout
  done

done



