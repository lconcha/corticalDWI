#!/bin/bash
source `which my_do_cmd`

subjID=$1
hemi=$2
surf_type=$3
target_type=$4

sub_orig_surf=${SUBJECTS_DIR}/${subjID}/surf/${hemi}.${surf_type}
sub_orig_sphere=${SUBJECTS_DIR}/${subjID}/surf/${hemi}.sphere
out_surface=${SUBJECTS_DIR}/${subjID}/surf/${hemi}_${surf_type}_${target_type}.surf.gii


case $hemi in
  lh)
    h=L;;
  rh)
    h=R;;
esac

case $target_type in
  fsLR-5k)
    target_surf=$(dirname $0)/fsLR-5k/surf/fsLR-5k.${h}.sphere.surf.gii
    ;;
  fsLR-32k)
    target_surf=$(dirname $0)/fsLR-32k/surf/fsLR-32k.${h}.sphere.surf.gii
    ;;
  fsaverage5)
    target_surf=$(dirname $0)/fsaverage5/surf/${hemi}.sphere
    ;;
  *)
    echolor red "[ERROR] Unrecognized target_type : $target_type"
    exit 2
    ;;
esac


isOK=1
for f in $sub_orig_surf $sub_orig_sphere $target_surf
do
  if [ ! -f $f ]
  then
    echolor red "[ERROR] File not found: $f"
    isOK=0
  else
    echolor green "[INFO] Found file: $f"
  fi
done

if [ $isOK -eq 0 ]
then
  exit 2
fi


echolor yellow "sub_orig_surf   : $sub_orig_surf"
echolor yellow "sub_orig_sphere : $sub_orig_sphere"
echolor yellow "out_surface     : $out_surface"
echolor yellow "target_surf     : $target_surf"


tmpDir=$(mktemp -d)

my_do_cmd mris_convert \
  $sub_orig_surf \
  ${tmpDir}/sub_orig.surf.gii

my_do_cmd mris_convert \
  $sub_orig_sphere \
  ${tmpDir}/sub_orig_sphere.surf.gii


my_do_cmd mris_convert \
  $target_surf \
  ${tmpDir}/target_sphere.surf.gii

echo -------------

my_do_cmd wb_command -surface-resample \
  ${tmpDir}/sub_orig.surf.gii \
  ${tmpDir}/sub_orig_sphere.surf.gii \
  ${tmpDir}/target_sphere.surf.gii \
  BARYCENTRIC \
  $out_surface


echo "
freeview -v ${SUBJECTS_DIR}/${subjID}/mri/brain.mgz -f $sub_orig_surf $out_surface
"


rm -fR $tmpDir