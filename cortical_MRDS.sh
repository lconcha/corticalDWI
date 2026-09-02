#!/bin/bash
source `which my_do_cmd`



print_help () {
  echo "
  `basename $0`  [options]  <sID>

  Options:

  -roi <roi>     : Binary mask (nii[.gz], but NOT mif format) to use for MRDS fitting.
                   If not provided, will use the mask in the dwi directory.
                   Remember that you can use cortical_select_streamlines_by_label.sh
                   to create a mask from a parcellation.
                   Caution: If the mask is too small and does not contain enough white matter voxels,
                   then the response function should be provided explicitly (not implemented yet).
  -help          : Print this help message and exit.
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
    -roi)
      roi=$2
      if [ ! -f $roi ]
      then
        echolor red "[ERROR] Cannot find roi file: $roi"
        exit 2
      fi
      shift;shift
    ;;
    -h|help)
      print_help
      exit 0
    ;;
  esac
done


sID=$1;      # subject ID in the form of sub-74277
echolor green "[INFO] sID is $sID"

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
outdir=${SUBJECTS_DIR}/${sID}/dwi/mrds
outbase=${outdir}/${sID}

if [ ! -z "$roi" ]
then
  echolor green "[INFO] Using roi: $roi"
  mask=$roi
else
  mask=${SUBJECTS_DIR}/${sID}/dwi/mask.nii.gz
  echolor green "[INFO] No roi provided, using mask: $mask"
fi


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








# If any of the MRDS outputs does not exist, recompute all MRDS outputs.
doComputeMRDS=0
for modsel in FTest BIC
do
  for v in FA MD COMP_SIZE
  do
    fcheck=${outbase}_MRDS_Diff_${modsel}_${v}.nii.gz
    if [ ! -f $fcheck ]
    then
      echolor green "[INFO] File not found, will compute: $fcheck"
      doComputeMRDS=1
    else
      echolor green "[INFO] File found, will not overwrite: $fcheck"
    fi
  done
done



if [ $doComputeMRDS -eq 1 ]
then
  nVoxels=$(mrstats -ignorezero $mask -output count)
  echolor green "[INFO] Will fit MRDS in $nVoxels voxels"
  mkdir -pv $outdir
  my_do_cmd dti \
    -mask $mask \
    -response 0 \
    -correction 0 \
    -fa -md \
    $dwi \
    $scheme \
    ${outbase}
  nAnisoVoxels=`fslstats ${outbase}_DTInolin_ResponseAnisotropicMask.nii -V | awk '{print $1}'`
  if [ $nAnisoVoxels -lt 1 ]
  then
    echolor red "[ERROR] Not enough anisotropic voxels found for estimation of response. Found $nAnisoVoxels"
  fi
  echolor yellow "Getting lambdas for response (from $nAnisoVoxels voxels)"
  response=`cat ${outbase}_DTInolin_ResponseAnisotropic.txt | awk '{OFS = "," ;print $1,$2}'`

  
  cmd="mdtmrds \
  $dwi \
  $scheme \
  ${outbase} \
  -correction 0 \
  -response "$response" \
  -mask $mask \
  -modsel ftest,bic \
  -fa -md -mse \
  -method diff \
  -lowb 2000 \
  -ntensors 3 \
  -iso \
  1"
  # save the command to a text file for reproducibility
  echo "$cmd" > ${outbase}_MRDS_cmd.txt
  my_do_cmd $cmd

  gzip -v ${outbase}_DTInolin*.nii ${outbase}_MRDS_*.nii
else
  echolor green "[INFO] Will not run MRDS"
fi



for modsel in FTest BIC
do
  haveFixelInputs=1
  for f in ${outbase}_MRDS_Diff_${modsel}_{PDDs_CARTESIAN,COMP_SIZE,FA,MD}.ni*
  do
    if [ ! -f $f ]
    then
      echolor red "[ERROR] File not found: $f "
      haveFixelInputs=0
    fi
  done


  if [ $haveFixelInputs -eq 1 ]
  then
    # Each modsel gets its own fixel subdirectory
    mkdir -pv ${outdir}/mrds_fixels/${modsel}
    for v in FA MD COMP_SIZE
    do
      fcheck=${outdir}/mrds_fixels/${modsel}/MRDS_Diff_${modsel}_${v}.mif
      if [ -f $fcheck ]
      then
        echolor green "[INFO] File found, will not overwrite: $fcheck"
        continue
      fi
      tmpDir=$(mktemp -u)
      my_do_cmd inb_mrds_scalePDDs.sh \
          -e 0.0000000000000001 \
          ${outbase}_MRDS_Diff_${modsel}_PDDs_CARTESIAN.nii.gz \
          ${outbase}_MRDS_Diff_${modsel}_${v}.nii.gz \
          ${outbase}_MRDS_Diff_${modsel}_PDDs_CARTESIAN_scaled-by-${v}.nii.gz

      my_do_cmd peaks2fixel \
          ${outbase}_MRDS_Diff_${modsel}_PDDs_CARTESIAN_scaled-by-${v}.nii.gz \
          $tmpDir
      cp -v ${tmpDir}/amplitudes.mif \
          ${outdir}/mrds_fixels/${modsel}/MRDS_Diff_${modsel}_${v}.mif
      cp -v ${tmpDir}/{directions,index}.mif ${outdir}/mrds_fixels/${modsel}/
      my_do_cmd rm -fR $tmpDir
      done
  fi
done

echolor green "[INFO] Finished MRDS for $sID"