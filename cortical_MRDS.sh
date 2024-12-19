#!/bin/bash
source `which my_do_cmd`

sID=$1;      # subject ID in the form of sub-74277
doParallel=1

print_help () {
  echo "
  `basename $0` <sID> [-no_parallel]

  Options:

  -no_parallel  : Do not multiplex this command as jobs sent to the cluster.
                  Compute locally (a lot longer).

  "
}


if [ $# -lt 1 ]
then
  echolor red "Not enough arguments"
  print_help
  exit 0
fi

for arg in "$@"
do
  case "${arg}" in
    -h|-help)
        print_help
        exit 0
    ;;
    -no_parallel)
      doParallel=0
    ;;
  esac
done



if [ ! -d ${SUBJECTS_DIR}/${sID} ]
then
  echolor red "[ERROR] Cannot find directory ${SUBJECTS_DIR}/${sID}"
  echolor red "        Check your SUBJECTS_DIR and sID"
  exit 2
fi


dwi=${SUBJECTS_DIR}/${sID}/dwi/dwi.nii.gz
bvec=${SUBJECTS_DIR}/${sID}/dwi/dwi.bvec
bval=${SUBJECTS_DIR}/${sID}/dwi/dwi.bval
scheme=${SUBJECTS_DIR}/${sID}/dwi/dwi.scheme
mask=${SUBJECTS_DIR}/${sID}/dwi/mask.nii.gz
outbase=${SUBJECTS_DIR}/${sID}/dwi/${sID}
nVoxPerJob=10000
scratch_dir=${SUBJECTS_DIR}/${sID}/dwi/tmp


isOK=1
for f in $dwi $scheme $mask
do
  if [ -f "$f" ]
  then
    echolor green "[INFO] Found $f"
  else
    echolor red "[ERROR] File not found: $f"
    isOK=0
  fi
done
if [ $isOK -eq 0 ]; then exit 2; fi


doComputeMRDS=1
fcheck=$(imglob -extension ${outbase}_MRDS_Diff_BIC_FA)
if [ ! -z ${fcheck} ]
then
  echolor orange "[INFO] File found $fcheck"
  echolor orange "       Will not overwrite."
  doComputeMRDS=0
fi




## Define if parallel or not
if [ $doParallel -eq 1 ]
then
  if [ ! -d $scratch_dir ]
  then
    echolor green "[INFO] Creating directory $scratch_dir"
    mkdir $scratch_dir
  fi
  my_do_cmd inb_mrds_sge.sh
    $dwi \
    $scheme \
    $mask \
    $outbase \
    $nVoxPerJob \
    $scratch_dir
else
  my_do_cmd inb_mrds.sh \
    $dwi \
    $bvec $bval \
    $mask \
    $outbase

fi





# if [ $doComputeMRDS -eq 1 ]
# then
#     my_do_cmd $mrds_command \
#     $dwi \
#     $scheme \
#     $mask \
#     $outbase \
#     $nVoxPerJob \
#     $scratch_dir
# fi


# doFixels=1
# fcheck=${SUBJECTS_DIR}/${sID}/dwi/mrds_fixels/index.mif
# #echolor cyan  "[INFO] Looking for file: $fcheck"
# if [ -f $fcheck ]
# then
#   echolor orange "[INFO] File found $fcheck"
#   echolor orange "       Will not overwrite."
#   doFixels=0
# fi


# for f in ${outbase}_MRDS_Diff_BIC_{PDDs_CARTESIAN,COMP_SIZE}.nii.gz
# do
#   if [ ! -f $f ]
#   then
#     echolor red "[ERROR] File not found: $f "
#     doFixels=0
#   fi 
# done


# if [ $doFixels -eq 1 ]
# then
#     my_do_cmd inb_mrds_scalePDDs.sh \
#         ${outbase}_MRDS_Diff_BIC_PDDs_CARTESIAN.nii.gz \
#         ${outbase}_MRDS_Diff_BIC_COMP_SIZE.nii.gz \
#         ${outbase}_MRDS_Diff_BIC_PDDs_CARTESIAN_scaled.nii.gz

#     my_do_cmd peaks2fixel \
#         ${outbase}_MRDS_Diff_BIC_PDDs_CARTESIAN_scaled.nii.gz \
#         ${SUBJECTS_DIR}/${sID}/dwi/mrds_fixels
# fi