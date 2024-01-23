#!/bin/bash
source `which my_do_cmd`


sID=$1
hemi=$2;        #lh, rh
target_type=$3; #fsLR-32k

xfm_lin_t1_to_b0=${SUBJECTS_DIR}/${sID}/dwi/t1native_to_b0_0GenericAffine.mat
xfm_nlin_t1_to_b0=${SUBJECTS_DIR}/${sID}/dwi/t1native_to_b0_1Warp.nii.gz
xfm_nlin_t1_to_b0_inv=${SUBJECTS_DIR}/${sID}/dwi/t1native_to_b0_1InverseWarp.nii.gz
b0=${SUBJECTS_DIR}/${sID}/dwi/b0.nii.gz
tck_t1space=${SUBJECTS_DIR}/${sID}/mri/${hemi}_${target_type}_laplace-wm-streamlines.tck


isOK=1
for f in $b0 $xfm_lin_t1_to_b0 $xfm_nlin_t1_to_b0 $xfm_nlin_to_b0_inv
do
  if [ -f "$f" ]
  then
    echo "."
  else
    echolor red "[ERROR] File not found: $f"
    isOK=0
  fi
done

if [ $isOK -eq 0 ]; then exit 2; fi


# warp tck
# https://community.mrtrix.org/t/registration-using-transformations-generated-from-other-packages/2259
tmpDir=$(mktemp -d)
my_do_cmd warpinit $b0 ${tmpDir}/inv_identity_warp[].nii
for i in {0..2}; do
    my_do_cmd antsApplyTransforms -d 3 \
    -e 0 \
    -i ${tmpDir}/inv_identity_warp${i}.nii \
    -o ${tmpDir}/inv_mrtrix_warp${i}.nii \
    -r $b0 \
    -t [$xfm_lin_t1_to_b0, 1] \
    -t $xfm_nlin_t1_to_b0_inv \
    --default-value 2147483647
done
my_do_cmd warpcorrect ${tmpDir}/inv_mrtrix_warp[].nii ${tmpDir}/inv_mrtrix_warp_corrected.mif -marker 2147483647
tck_dwispace=${SUBJECTS_DIR}/${sID}/dwi/$(basename ${out_tck%.tck}_dwispace.tck)
my_do_cmd tcktransform $tck_t1space ${tmpDir}/inv_mrtrix_warp_corrected.mif $tck_dwispace
rm -fR $tmpDir

echolor green "[INFO] Done. Check with: "
echolor green "       mrview $b0 -tractography.load $tck_dwispace"