#!/bin/bash
source `which my_do_cmd`

sID=$1
surf_type=$2
tmpDir=$3

if [ ! -d ${SUBJECTS_DIR}/${sID} ]
then
  echolor red "[ERROR] Cannot find directory ${SUBJECTS_DIR}/${sID}"
  echolor red "        Check your SUBJECTS_DIR and sID"
  exit 2
fi


#tmpDir=$(mktemp -d)

fixels_csd=${SUBJECTS_DIR}/${sID}/dwi/csd_fixels/directions.mif


afd=${SUBJECTS_DIR}/${sID}/dwi/csd_fixels/afd4D.mif

my_do_cmd fixel2voxel $fixels_csd none $afd



rm -fR $tmpDir