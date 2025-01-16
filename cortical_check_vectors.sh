#!/bin/bash
source `which my_do_cmd`

sID=$1
type=$2



fa=${SUBJECTS_DIR}/${sID}/dwi/fa.nii.gz


case $type in 
  mrds)
    echo "Will check MRDS"
    fixels=${SUBJECTS_DIR}/${sID}/dwi/mrds_fixels/directions.mif
    ;;
  csd)
    echo "Will check CSD"
    fixels=${SUBJECTS_DIR}/${sID}/dwi/csd_fixels/directions.mif
    ;;
  dti)
    echo "Will check DTI"
    fixels=${SUBJECTS_DIR}/${sID}/dwi/${sID}_DTInolin_PDDs_CARTESIAN.nii.gz
    ;;
  *)
    echolor red "[ERROR] Unknown diffusion modality. Must be one of mrds, csd or dti"
    exit 2
    ;;
esac



my_do_cmd mrview $fa -fixel.load $fixels