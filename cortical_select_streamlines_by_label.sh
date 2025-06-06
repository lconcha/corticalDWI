#!/bin/bash
source `which my_do_cmd`

help() {
  echo "
  Usage: $(basename $0) [options] <subjID> <labelID> <target_type>

  <subjID>          subject ID
  <labelID>         label ID(s) to select streamlines from.
                    If more than one, use a space-delimited list of labels between double quotes
  <target_type>     type of target (e.g., 'fsLR-32k')

  Options: 

  -m <mask_out>     output mask in dwispace (nii[.gz] or mif format).
                    Please note that there is a dilation step applied to the mask, 
                    therefore the number of voxels in the mask may not match a tckmap output.
  -t <out.tck>      output tck in T1 space
  -d <out_dwi.tck>  output tck in DWI space
  

  "
}


if [ $# -lt 3 ]
then
  echolor red "Not enough arguments"
  help
  exit 0
fi


writeMask=0
writeTck_t1=0
writeTck_dwi=0
while getopts "m:t:d:h" opt
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
    h)
      help
      exit 0
    ;;
    *)
      echolor red "[ERROR] Invalid flag."
      exit 2
    ;;
  esac
done
shift $((OPTIND-1))



subjID=$1
labelID=$2; # can be a list of labels, space separated, in double quotes. e.g. "11145 12145".
target_type=$3

fsLUT=${FREESURFER_HOME}/luts/FreeSurferColorLUT.txt
aparc=${SUBJECTS_DIR}/${subjID}/mri/aparc.a2009s+aseg.mgz
dwi=${SUBJECTS_DIR}/${subjID}/dwi/dwi.nii.gz


tmpDir=$(mktemp -d)

streamlines_t1=$tmpDir/streamlines_t1.tck
streamlines_dwi=$tmpDir/streamlines_dwi.tck
my_do_cmd tckedit ${SUBJECTS_DIR}/${subjID}/mri/?h_${target_type}_laplace-wm-streamlines.tck $streamlines_t1
my_do_cmd tckedit ${SUBJECTS_DIR}/${subjID}/dwi/?h_${target_type}_laplace-wm-streamlines_dwispace.tck $streamlines_dwi


# Generate the mask based on the label(s)
my_do_cmd mrcalc $aparc 0 -mul ${tmpDir}/labels.mif
for r in $labelID
do
  line=$(grep $r $fsLUT)
  name=$(echo $line | awk '{print $2}')
  my_do_cmd mrcalc -quiet $aparc $r -eq ${tmpDir}/label_${r}.mif
  nVox=$(mrstats -quiet -ignorezero -output count ${tmpDir}/label_${r}.mif)
  echolor green "[INFO] Region $labelID ($name) has $nVox voxels"
if [ $? -ne 0 ]; then echolor red "[ERROR] Label $r not found in aparc"; exit 2; fi
  my_do_cmd mrcalc -force -quiet ${tmpDir}/label_${r}.mif ${tmpDir}/labels.mif -add ${tmpDir}/labels.mif
done

# check that it is not empty
nVox=$(mrstats -quiet -ignorezero -output count ${tmpDir}/labels.mif)
echolor green "[INFO] Region $labelID has $nVox voxels"
if [ $nVox -eq 0 ]; then echolor red "[ERROR] Zero voxels in this region"; exit 2;fi



# Create a linearly increasing "weights" text file. WIll be used to extract the indices of the streamlines
# see https://community.mrtrix.org/t/individual-streamline-index-included-in-tck-file/1104
nTracks=$(tckinfo -quiet -count $streamlines_t1 | grep "actual count in file" | awk -F: '{print $2}')
i_in=${tmpDir}/indices_in.txt  
seq 0 $(($nTracks -1)) > $i_in


# tckedit in T1 streamlines
selectedtracto_t1=${tmpDir}/selectedtracto_t1.tck
indices_to_keep=${tmpDir}/indices_to_keep.txt; #indices of the selected tracks
my_do_cmd tckedit -quiet \
-include ${tmpDir}/labels.mif \
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
selectedtracto_dwi=$tmpDir/selectedtracto_dwispace.tck
my_do_cmd tckedit -quiet \
-tck_weights_in ${tmpDir}/indices.txt \
-minweight 0.1 $streamlines_dwi $selectedtracto_dwi
cat "$indices_to_keep" > ${selectedtracto_dwi%.tck}_indices.txt


# Write the output files
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
