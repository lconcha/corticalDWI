#!/bin/bash
source `which my_do_cmd`

# ── Defaults (lowest priority) ────────────────────────────────────────────────
target_type=fsLR-32k
nsteps=100
step_size=0.1
tck_step_size=0.5

# ── Config file(s) ────────────────────────────────────────────────────────────
source cortical_load_params.sh 2>/dev/null || true

# ── CLI args (highest priority) ───────────────────────────────────────────────
sID=$1
hemi=$2
[ -n "$3" ] && target_type=$3
[ -n "$4" ] && nsteps=$4
[ -n "$5" ] && step_size=$5

CODEDIR=$(dirname $0)
PYTHON=$(which python3)
echolor cyan "Using Python: $PYTHON ($(${PYTHON} --version 2>&1))"

help() {
  echo "
  Usage: $(basename $0) <subjID> <hemi> [target_type] [nsteps] [step_size]

  <subjID>         subject ID in the form of sub-74277
  <hemi>           hemisphere (lh or rh)
  [target_type]    type of target (default: ${target_type})
  [nsteps]         number of steps to take along the streamline (default: ${nsteps})
  [step_size]      step size in mm (default: ${step_size})

  Optional args default to values in corticalDWI_params.conf when not provided.
  Please note that the tck is resampled to a step size of ${tck_step_size} mm at the end of the process.

  This script will compute streamlines from the white matter surface to the pial surface
  using the Laplacian field.
  "
}

if [ $# -lt 2 ]
then
  echolor red "Incorrect number of arguments (subjID and hemi are required)"
  help
  exit 0
fi


surf_white=${SUBJECTS_DIR}/${sID}/surf/${hemi}_white_${target_type}.surf.gii
surf_pial=${SUBJECTS_DIR}/${sID}/surf/${hemi}_pial_${target_type}.surf.gii
in_vec=${SUBJECTS_DIR}/${sID}/mri/laplace-wm_vec.nii.gz


isOK=1
for f in $surf_white $surf_pial $in_vec
do
  if [ ! -f "$f" ]; then
    echolor red "[ERROR] File not found: $f"
    isOK=0
  fi
done
if [ $isOK -eq 0 ]; then exit 2; fi


tmp_tck=/tmp/temp_$$.tck
tmp_tck_withheader=/tmp/temp2_$$.tck
out_tck=${SUBJECTS_DIR}/${sID}/mri/${hemi}_${target_type}_laplace-wm-streamlines.tck

if [ -f $out_tck ]; then
  echolor yellow "[WARN] Output tck already exists, will not overwrite: $out_tck"
  exit 0
fi


echolor cyan "Running cortical_streamlines.py"
$PYTHON $CODEDIR/cortical_streamlines.py \
  $surf_white \
  $surf_pial \
  $in_vec \
  $nsteps \
  $step_size \
  $tmp_tck

if [ ! -f $tmp_tck ]; then
  echolor red "Failed to create tck: $tmp_tck"
  exit 3
fi

my_do_cmd tckedit $tmp_tck $tmp_tck_withheader; # this will put a header that cortical_treamlines.py cannot write

echolor cyan "Resampling and truncating streamlines to step size ${tck_step_size} mm"
$PYTHON $(which tckresample_and_truncate) $tmp_tck_withheader $out_tck --step_size $tck_step_size
if [ -f $out_tck ]; then
  echolor bold "Successfully created output tck: $out_tck"
else
  echolor red "Failed to create output tck: $out_tck"
  exit 3
fi

#echolor green "Retaining $tmp_tck and $tmp_tck_withheader"
rm $tmp_tck $tmp_tck_withheader

# ls $tmp_tck
# ls $tmp_tck_withheader
# ls $out_tck

my_do_cmd tckresample -force -quiet -endpoints $out_tck ${out_tck%.tck}_endsOnly.tck

echolor cyan "mrview ${SUBJECTS_DIR}/${sID}/mri/aparc+aseg.nii.gz ${SUBJECTS_DIR}/${sID}/mri/laplace-wm_vec.nii.gz \
  -tractography.load $out_tck -tractography.geometry lines \
  -tractography.load ${out_tck%.tck}_endsOnly.tck -tractography.geometry points"