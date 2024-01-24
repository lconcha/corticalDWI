#!/bin/bash


sID=$1
command=$2

case $command in
  show)
    cmd="ls -v"
  ;;
  delete)
    cmd="rm -v"
  ;;
  *)
    echolor red "[ERROR] Must specify either show or delete as second argument."
    exit 2
esac




$cmd ${SUBJECTS_DIR}/${sID}/mri/laplace*
$cmd ${SUBJECTS_DIR}/${sID}/mri/?h_*tck
$cmd ${SUBJECTS_DIR}/${sID}/dwi/t1native_to_b0*
$cmd ${SUBJECTS_DIR}/${sID}/dwi/?h_*.tck