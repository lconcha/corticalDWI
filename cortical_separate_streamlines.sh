#!/bin/bash
source `which my_do_cmd`

subjID=$1
hemi=$2
target_type=$3


fsLUT=${FREESURFER_HOME}/luts/FreeSurferColorLUT.txt
aparc=${SUBJECTS_DIR}/${subjID}/mri/aparc.a2009s+aseg.mgz
streamlines=${SUBJECTS_DIR}/${subjID}/mri/${hemi}_${target_type}_laplace-wm-streamlines.tck


tmpDir=$(mktemp -d)

# convert the aparc and make it all zeroes. We will then update it for each ROI
mrconvert $aparc ${tmpDir}/aparc.mif
aparc=${tmpDir}/aparc.mif


# Create a linearly increasing "weights" text file. WIll be used to extract the indices of the streamlines
# see https://community.mrtrix.org/t/individual-streamline-index-included-in-tck-file/1104
nTracks=$(tckinfo -quiet -count $streamlines | grep "actual count in file" | awk -F: '{print $2}')
i_in=${tmpDir}/indices_in.txt  
seq 0 $(($nTracks -1)) > $i_in


grep -v '#' $fsLUT | grep ctx_${hemi}_ | while read r
do
  
  # Create a binary mask of the cortical region
  labelID=$(echo $r | awk '{print $1}')
  name=$(echo $r | awk '{print $2}')
  echolor cyan " labelID: $labelID , name: $name"
  my_do_cmd mrcalc -quiet $aparc $labelID -eq ${tmpDir}/${labelID}.mif

  seletedtracto=${SUBJECTS_DIR}/${subjID}/mri/${hemi}_${target_type}_laplace-wm-streamlines_${labelID}.tck
  i_out=${seletedtracto%.tck}_indices.txt; #indices of the selected tracks

  my_do_cmd tckedit -quiet \
    -include ${tmpDir}/${labelID}.mif \
    -tck_weights_in $i_in \
    -tck_weights_out $i_out \
    $streamlines \
    $seletedtracto

done


rm -fR $tmpDir