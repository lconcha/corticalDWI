#!/bin/bash
source `which my_do_cmd`

subjID=$1
hemi=$2
target_type=$3


fsLUT=${FREESURFER_HOME}/luts/FreeSurferColorLUT.txt
aparc=${SUBJECTS_DIR}/${subjID}/mri/aparc.a2009s+aseg.mgz
streamlines_t1=${SUBJECTS_DIR}/${subjID}/mri/${hemi}_${target_type}_laplace-wm-streamlines.tck
streamlines_dwi=${SUBJECTS_DIR}/${subjID}/dwi/${hemi}_${target_type}_laplace-wm-streamlines_dwispace.tck

tmpDir=$(mktemp -d)

# convert the aparc and make it all zeroes. We will then update it for each ROI
mrconvert $aparc ${tmpDir}/aparc.mif
aparc=${tmpDir}/aparc.mif


# Create a linearly increasing "weights" text file. WIll be used to extract the indices of the streamlines
# see https://community.mrtrix.org/t/individual-streamline-index-included-in-tck-file/1104
nTracks=$(tckinfo -quiet -count $streamlines_t1 | grep "actual count in file" | awk -F: '{print $2}')
i_in=${tmpDir}/indices_in.txt  
seq 0 $(($nTracks -1)) > $i_in


grep -v '#' $fsLUT | grep ctx_${hemi}_ | while read r
do
  
  # Create a binary mask of the cortical region
  labelID=$(echo $r | awk '{print $1}')
  name=$(echo $r | awk '{print $2}')
  echolor cyan " labelID: $labelID , name: $name"
  my_do_cmd mrcalc -quiet $aparc $labelID -eq ${tmpDir}/${labelID}.mif

  # check that it is not empty
  nVox=$(mrstats -quiet -ignorezero -output count ${tmpDir}/${labelID}.mif)
  echolor green "[INFO] Region $labelID has $nVox voxels"
  if [ $nVox -eq 0 ]; then echolor yellow "[INFO] Going to next region"; continue;fi

  # tckedit in T1 streamlines
  selectedtracto=${SUBJECTS_DIR}/${subjID}/mri/${hemi}_${target_type}_laplace-wm-streamlines_${labelID}.tck
  indices_to_keep=${selectedtracto%.tck}_indices.txt; #indices of the selected tracks
  my_do_cmd tckedit -quiet \
    -include ${tmpDir}/${labelID}.mif \
    -tck_weights_in $i_in \
    -tck_weights_out $indices_to_keep \
    $streamlines_t1 \
    $selectedtracto

  # now in dwi space
  yes 0 | head -n $nTracks > ${tmpDir}/indices.txt;   # create a file with zeros with $nTracks rows
  ikeep=$(cat $indices_to_keep)
  nKeep=$(wc -w $indices_to_keep | awk '{print $1}')
  echolor green "[INFO] $labelID ($name) has $nKeep streamlines"
  if [ $nKeep -eq 0 ]; then echolor yellow "[INFO] No streamlines selected"; continue; fi
  for i in $ikeep; # cange zeros to ones only in the rows of the indices to keep
    do
    sed -i "${i}s/0/1/" ${tmpDir}/indices.txt
  done
  selectedtracto=${SUBJECTS_DIR}/${subjID}/dwi/${hemi}_${target_type}_laplace-wm-streamlines_dwispace_${labelID}.tck
  my_do_cmd tckedit -quiet \
    -tck_weights_in ${tmpDir}/indices.txt \
    -minweight 0.1  \
    $streamlines_dwi \
    $selectedtracto

done


rm -fR $tmpDir