#!/bin/bash
source `which my_do_cmd`

subjID=$1
hemi=$2
target_type=$3; # fsLR-5k or fsLR-32k
fixel_dir=$4; # mrds_fixels (or something else, but it has to be mrds)
angle=$5
nDepths=$6; # number of depth points to keep in the txt file. The tsf saves them all.


########### NOT FINISHED, change afd for FA and stuff!!!###########

isOK=1

fixel_dir=${SUBJECTS_DIR}/${subjID}/dwi/${fixel_dir}
if [ ! -d $fixel_dir ]
then
  echolor red "[ERROR] Fixel directory does not exist: $fixel_dir"
  isOK=0
  #exit 2
fi


tck=${SUBJECTS_DIR}/${subjID}/dwi/${hemi}_${target_type}_laplace-wm-streamlines_dwispace.tck
for v in FA MD COMP_SIZE
do
    this_f=${fixel_dir}/MRDS_Diff_BIC_${v}.mif
    for f in $tck $this_f
    do
    if [ ! -f $f ]
    then
        echolor red "[ERROR] Cannot find file: $f"
        isOK=0
    else
        echolor green "[INFO] Found file: $f"
    fi
    done


    fcheck=${fixel_dir}/${hemi}_${target_type}_${v}-par-perp-indices.tsf
    echo "looking for $fcheck"
    if [ -f $fcheck ]
    then
    echolor yellow "[WARN] File exists, will not overwrite: $fcheck"
    exit 0
    fi


    if [ $isOK -eq 1 ]
    then
    my_do_cmd tcksamplefixels \
    -angle $angle \
    $this_f \
    $tck \
    ${fixel_dir}/${hemi}_${target_type}_${v}-par-perp-indices.tsf \
    ${fixel_dir}/${hemi}_${target_type}_${v}-par.tsf \
    ${fixel_dir}/${hemi}_${target_type}_${v}-perp.tsf \
    ${fixel_dir}/${hemi}_${target_type}_${v}-perp-av.tsf
    else
    echolor red "[ERROR] Cannot continue, see above errors"
    exit 2
    fi
done

for tsf in ${fixel_dir}/*.tsf
do
  txt=${tsf%.tsf}.txt
  my_do_cmd  cortical_tsf2txt_matlab.sh $tsf $txt $nDepths
done