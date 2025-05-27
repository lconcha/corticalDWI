#!/bin/bash
source `which my_do_cmd`


writeMask=0
writeTck_t1=0
writeTck_dwi=0
while getopts "m:t:d:" opt
do
  case $opt in
    m)
      writeMask=1
      mask_out=${OPTARG}
    ;;
    t)
      writeTck_t1=1
      tck_out_t1=${OPTARG}
    ;;
    d)
      writeTck_dwi=1
      tck_out_dwi=${OPTARG}
 ;;
    \?)
      echolor red "[ERROR] Invalid flag."
      exit 2
    ;;
  esac
done
shift $((OPTIND-1))



subjID=$1
labelID=$2
target_type=$3

fsLUT=${FREESURFER_HOME}/luts/FreeSurferColorLUT.txt
aparc=${SUBJECTS_DIR}/${subjID}/mri/aparc.a2009s+aseg.mgz
dwi=${SUBJECTS_DIR}/${subjID}/dwi/dwi.nii.gz


tmpDir=$(mktemp -d)

line=$(grep $labelID $fsLUT)
name=$(echo $line | awk '{print $2}')

echolor cyan "$name"


streamlines_t1=$tmpDir/streamlines_t1.tck
streamlines_dwi=$tmpDir/streamlines_dwi.tck

my_do_cmd tckedit ${SUBJECTS_DIR}/${subjID}/mri/?h_${target_type}_laplace-wm-streamlines.tck $streamlines_t1
my_do_cmd tckedit ${SUBJECTS_DIR}/${subjID}/dwi/?h_${target_type}_laplace-wm-streamlines_dwispace.tck $streamlines_dwi


my_do_cmd mrcalc -quiet $aparc $labelID -eq ${tmpDir}/${labelID}.mif
# check that it is not empty
nVox=$(mrstats -quiet -ignorezero -output count ${tmpDir}/${labelID}.mif)
echolor green "[INFO] Region $labelID has $nVox voxels"
if [ $nVox -eq 0 ]; then echolor red "[ERROR] Zero voxels in this region"; exit 2;fi




# Create a linearly increasing "weights" text file. WIll be used to extract the indices of the streamlines
# see https://community.mrtrix.org/t/individual-streamline-index-included-in-tck-file/1104
nTracks=$(tckinfo -quiet -count $streamlines_t1 | grep "actual count in file" | awk -F: '{print $2}')
i_in=${tmpDir}/indices_in.txt  
seq 0 $(($nTracks -1)) > $i_in


# tckedit in T1 streamlines
selectedtracto_t1=${tmpDir}/${labelID}.tck
indices_to_keep=${tmpDir}/indices_to_keep.txt; #indices of the selected tracks
my_do_cmd tckedit -quiet \
-include ${tmpDir}/${labelID}.mif \
-tck_weights_in $i_in \
-tck_weights_out $indices_to_keep $streamlines_t1 $selectedtracto_t1

# now in dwi space
yes 0 | head -n $nTracks > ${tmpDir}/indices.txt;   # create a file with zeros with $nTracks rows
ikeep=$(cat $indices_to_keep)
nKeep=$(wc -w $indices_to_keep | awk '{print $1}')
echolor green "[INFO] $labelID ($name) has $nKeep streamlines"
if [ $nKeep -eq 0 ]; then echolor yellow "[INFO] No streamlines selected"; exit 2; fi
for i in $ikeep; # cange zeros to ones only in the rows of the indices to keep
do
    sed -i "${i}s/0/1/" ${tmpDir}/indices.txt
done
selectedtracto_dwi=$tmpDir/${labelID}_dwispace.tck
my_do_cmd tckedit -quiet \
-tck_weights_in ${tmpDir}/indices.txt \
-minweight 0.1 $streamlines_dwi $selectedtracto_dwi
cat "$indices_to_keep" > ${selectedtracto_dwi%.tck}_indices.txt


if [ $writeMask -eq 1 ]; then
  echolor green "[INFO] Writing mask in dwispace"
  tckmap -template $dwi $selectedtracto_dwi - | mrcalc - 0 -gt - | maskfilter - dilate $mask_out
fi
if [ $writeTck_t1 -eq 1 ]; then
  echolor green "[INFO] Writing t1 tck"
  my_do_cmd cp $selectedtracto_t1 $tck_out_t1
fi
if [ $writeTck_dwi -eq 1 ]; then
  echolor green "[INFO] Writing dwi tck"
  my_do_cmd cp $selectedtracto_dwi $tck_out_dwi
fi

rm -fR $tmpDir
#echo mrview $aparc -roi.load ${tmpDir}/${labelID}.mif -tractography.load $selectedtracto_dwi
