#!/bin/bash
source `which my_do_cmd`

help() {
  echo "
  Usage: $(basename $0) <subjID> <nDepths> <target_type> [metrics]

  <subjID>    subject ID in the form of sub-74277
  <nDepths>   number of depth points to keep in the txt file.
              This is in steps, not mm,
              and has to be less than or equal to the number of depth points in the tsf file.
  <target_type>  target type, e.g. fsLR-32k or ico6_sym
  [metrics]   optional space-separated list of metrics to sample (quoted as one
              argument), e.g. \"T1w_proc T1w_proc_grad\". Defaults to all four:
              T1w_proc flair_proc T1w_proc_grad T1_over_FLAIR. Use this to
              sample just the T1-only metrics for a subject with no
              flair.nii.gz/flair_proc.nii.gz.
  This script samples mri/ conventional images from a tck file and saves them in tsf format.
  It expects images like mri/T1w_proc.nii.gz and mri/flair_proc.nii.gz to exist in the subject's directory.

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
metrics="T1w_proc flair_proc T1w_proc_grad T1_over_FLAIR"
source cortical_load_params.sh 2>/dev/null || true
subjID=$1
[ -n "$2" ] && nDepths=$2
[ -n "$3" ] && target_type=$3
[ -n "$4" ] && metrics=$4


fcheck=${SUBJECTS_DIR}/${subjID}/dwi/mri/lh_${target_type}_T1w_proc.tsf
if [ -f $fcheck ]
then
  echolor green "[INFO] File exists, will not overwrite: $fcheck"
  exit 0
fi


for hemi in lh rh
do

  tck=${SUBJECTS_DIR}/${subjID}/mri/${hemi}_${target_type}_laplace-wm-streamlines.tck
  
  if [ ! -f $tck ]
  then
    echolor red "[ERROR] File does not exist: $f"
    exit 2
  fi


  for metric in $metrics
  do
    #echolor green "Sampling $metric in $tck in $target_type in $hemi"
    map=${SUBJECTS_DIR}/${subjID}/mri/${metric}.nii.gz
    tsfout=${SUBJECTS_DIR}/${subjID}/mri/${hemi}_${target_type}_${metric}.tsf
    if [ -f $tsfout ]
    then
      echolor green "[INFO] File exists, will not overwrite: $tsfout"
      continue
    fi

    if [ ! -f $map ]
    then
      echolor red "[ERROR] File does not exist: $map"
      exit 2
    fi
    my_do_cmd   cortical_tcksample_safe.sh  $tck $map $tsfout
  done

done
