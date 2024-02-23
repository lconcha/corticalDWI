#!/bin/bash
source `which my_do_cmd`

mymrtrix=/misc/lauterbur/lconcha/code/mrtrix3
tckfixeldots=${mymrtrix}/bin/tckfixeldots

sID=$1
hemi=$2
surf_type=$3
max_angle=$4

if [ ! -d ${SUBJECTS_DIR}/${sID} ]
then
  echolor red "[ERROR] Cannot find directory ${SUBJECTS_DIR}/${sID}"
  echolor red "        Check your SUBJECTS_DIR and sID"
  exit 2
fi


if [ ! -f $tckfixeldots ]
then
  echolor red "[ERROR] Cannot find tckfixeldots at $tckfixeldots"
  exit 2
fi

tck=${SUBJECTS_DIR}/${sID}/dwi/${hemi}_${surf_type}_laplace-wm-streamlines_dwispace.tck
FA4D=${SUBJECTS_DIR}/${sID}/dwi/${sID}_MRDS_Diff_BIC_FA.nii.gz
MD4D=${SUBJECTS_DIR}/${sID}/dwi/${sID}_MRDS_Diff_BIC_MD.nii.gz
COMP4D=${SUBJECTS_DIR}/${sID}/dwi/${sID}_MRDS_Diff_BIC_COMP_SIZE.nii.gz
mrds_amplitudes=${SUBJECTS_DIR}/${sID}/dwi/mrds_fixels/amplitudes.mif


isOK=1
for f in $tck $fa4D $MD4D $COMP4D
do
  if [ ! -f $f ]
  then
    echolor red "[ERROR] (Variable ${!f@}) Cannot find file: $f"
    isOK=0
  fi
done
if [ $isOK -eq 0 ]; then exit 2;fi


tmpDir=$(mktemp -d)


echolor green "[INFO] Identifying parallel and perpendicular components using custom-built tckfixeldots"
tsf_index=${SUBJECTS_DIR}/${sID}/dwi/mrds_fixels/${hemi}_${surf_type}_mrds_par_indices.tsf
tsf_par=${SUBJECTS_DIR}/${sID}/dwi/mrds_fixels/${hemi}_${surf_type}_mrds_par_compsize.tsf
tsf_perp=${SUBJECTS_DIR}/${sID}/dwi/mrds_fixels/${hemi}_${surf_type}_mrds_perp_compsize.tsf
$tckfixeldots -angle $max_angle \
  $mrds_amplitudes \
  $tck \
  $tsf_index \
  $tsf_par \
  $tsf_perp

#echo "converting to txt"
#tsfinfo -ascii ${tmpDir}/indices $tsf_index
#echo "n txt files:"
#ls $tmpDir/indices*txt | wc -l
#echo "# Parallel indices converted to txt from $tsf_index" > ${tmpDir}/indices_streamline_per_row.txt
#for f in ${tmpDir}/indices*txt
#do
#  echo $f
#  sed -z 's/\n/ /g' $f >> ${tmpDir}/indices_streamline_per_row.txt
#  cp -r ${tmpDir}/indices_streamline_per_row.txt ${tsf_index%.tsf}.txt
#done

for t in $(seq 0 2)
do
  for f in $FA4D $MD4D $COMP4D
  do
    my_do_cmd mrconvert -force -quiet \
      -coord 3 $t \
      $f \
      ${tmpDir}/file_to_sample.mif
    tsfout=${SUBJECTS_DIR}/${sID}/dwi/mrds_fixels/${hemi}_${surf_type}_$(basename ${f%.nii.gz})_${t}.tsf
    my_do_cmd tcksample \
      $tck ${tmpDir}/file_to_sample.mif \
      $tsfout
  done
done




rm -fR $tmpDir