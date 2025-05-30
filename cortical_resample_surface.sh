#!/bin/bash
source `which my_do_cmd`

subjID=$1
hemi=$2
surf_type=$3
target_type=$4


help( ) {
  echo "
  Usage: $(basename $0) <subjID> <hemi> <surf_type> <target_type>

  <subjID>         subject ID in the form of sub-74277
  <hemi>           hemisphere (lh or rh)
  <surf_type>      type of surface (e.g., 'pial', 'white', 'inflated')
  <target_type>    type of target (e.g., 'fsLR-5k', 'fsLR-32k', 'fsaverage5')

  This script will resample the original surface to the target surface.
  "
}

if [ $# -lt 4 ]
then
  echolor red "[ERROR] Not enough arguments"
  help
  exit 0
fi


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
  fi
done

if [ $isOK -eq 0 ]
then
  exit 2
fi


echo "  sub_orig_surf   : $sub_orig_surf"
echo "  sub_orig_sphere : $sub_orig_sphere"
echo "  out_surface     : $out_surface"
echo "  target_surf     : $target_surf"


tmpDir=$(mktemp -d)


my_do_cmd mris_convert --to-scanner \
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


my_do_cmd wb_command -surface-generate-inflated \
  $out_surface \
  ${out_surface%.surf.gii}_inflated.surf.gii \
  ${out_surface%.surf.gii}_veryInflated.surf.gii


# my_do_cmd cortical_transform_to_scanner_coords.sh \
#   $out_surface \
#   $sub_orig_surf \
#   ${out_surface%.surf.gii}_scanner.surf.gii



echo "
freeview -v ${SUBJECTS_DIR}/${subjID}/mri/brain.mgz \
  -f $sub_orig_surf $out_surface"

rm -fR $tmpDir