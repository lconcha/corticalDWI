#!/bin/bash
source `which my_do_cmd`

# ── Defaults (lowest priority) ────────────────────────────────────────────────
target_type=fsLR-32k
tck_step_size=0.5
max_length=10

# ── Config file(s) ────────────────────────────────────────────────────────────
source cortical_load_params.sh 2>/dev/null || true

help() {
  echo "
  Usage: $(basename $0) <subjID> <hemi> [target_type] [tck_step_size] [max_length]

  <subjID>        subject ID in the form of sub-74277
  <hemi>          hemisphere, lh or rh
  [target_type]   target type (default: ${target_type})
  [tck_step_size] step size for tck resampling in mm (default: ${tck_step_size})
  [max_length]    maximum length for tck truncation in mm (default: ${max_length})
  This script warps the Laplacian streamlines tck from T1 space to DWI space.
  
  For this to work, you should have run:
   - cortical_laplacian_wm_streamlines.sh
   - cortical_register_t1_to_dwi.sh

  The output is saved as $<hemi>_<target_type>_laplace-wm-streamlines_dwispace.tck.
  "
}


if [ $# -lt 2 ]
then
  echolor red "Wrong number of arguments (subjID and hemi are required)"
  help
  exit 0
fi

# ── CLI args (highest priority) ───────────────────────────────────────────────
sID=$1
hemi=$2
[ -n "$3" ] && target_type=$3
[ -n "$4" ] && tck_step_size=$4
[ -n "$5" ] && max_length=$5

xfm_lin_t1_to_b0=${SUBJECTS_DIR}/${sID}/dwi/t1native_to_b0_0GenericAffine.mat
xfm_nlin_t1_to_b0=${SUBJECTS_DIR}/${sID}/dwi/t1native_to_b0_1Warp.nii.gz
xfm_nlin_t1_to_b0_inv=${SUBJECTS_DIR}/${sID}/dwi/t1native_to_b0_1InverseWarp.nii.gz
b0=${SUBJECTS_DIR}/${sID}/dwi/b0.nii.gz
tck_t1space=${SUBJECTS_DIR}/${sID}/mri/${hemi}_${target_type}_laplace-wm-streamlines.tck


tck_dwispace=${SUBJECTS_DIR}/${sID}/dwi/${hemi}_${target_type}_laplace-wm-streamlines_dwispace.tck
if [ -f $tck_dwispace ]
then
  echolor green "[INFO] File exists, will not overwrite: $tck_dwispace"
  exit 0
fi

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
my_do_cmd tcktransform \
  $tck_t1space \
  ${tmpDir}/inv_mrtrix_warp_corrected.mif \
  ${tmpDir}/warped.tck

my_do_cmd tckresample_and_truncate \
  ${tmpDir}/warped.tck \
  $tck_dwispace \
  --step_size $tck_step_size \
  --max_length $max_length

rm -fR $tmpDir

echolor green "[INFO] Done. Check with: "
echolor green "       mrview $b0 -tractography.load $tck_dwispace"