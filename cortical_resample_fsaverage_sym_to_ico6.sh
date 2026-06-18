#!/bin/bash
# cortical_resample_fsaverage_sym_to_ico6.sh
#
# Builds the ico6 symmetric anatomical template surfaces (pial and white)
# used to display group-level / normative data computed on the ico6_sym
# mesh built by cortical_resample_surface_ico6_sym.sh.
#
# fsaverage_sym's own lh and rh surfaces do NOT share vertex correspondence
# (that property only arises when individual subjects' lh and flipped-rh
# are registered onto the same target sphere; the atlas's own native rh
# anatomy has no per-vertex relationship to its own lh anatomy). So rather
# than resampling fsaverage_sym's real rh surfaces, only the left
# hemisphere is resampled to ico6, and the right hemisphere template is
# built by mirroring it — guaranteeing exact vertex correspondence with the
# left, consistent with the rest of this "_sym" pipeline treating lh/rh as
# mirror images of one another.
#
# Usage: cortical_resample_fsaverage_sym_to_ico6.sh
#
# Requirements: FreeSurfer, Connectome Workbench
# Output: $SUBJECTS_DIR/templates/fsaverage_sym.{lh,rh}_{white,pial}.ico6_sym.surf.gii
source `which my_do_cmd`

set -e

# ── User-defined paths ────────────────────────────────────────────────────────
TEMPLATE=$SUBJECTS_DIR/templates/fsaverage_sym.sphere.ico6.surf.gii
WB=$(which wb_command)
FS_SYM=$FREESURFER_HOME/subjects/fsaverage_sym
OUT=$SUBJECTS_DIR/templates/surf
# ─────────────────────────────────────────────────────────────────────────────

if [[ ! -f $TEMPLATE ]]; then
    echo "ERROR: ico6 template sphere not found: $TEMPLATE"
    echo "Run cortical_resample_surface_ico6_sym.sh for at least one subject first."
    exit 1
fi

mkdir -p $OUT

if [[ -f $OUT/rh_pial.ico6_sym.surf.gii ]]; then
    echo ">>> fsaverage_sym surfaces already resampled to ico6, skipping."
    exit 0
fi

echo "========================================"
echo " FS_SYM   : $FS_SYM"
echo " TEMPLATE : $TEMPLATE"
echo " OUT      : $OUT"
echo "========================================"

# c_ras — shift from TkReg RAS to scanner RAS, matching the convention used
# for per-subject surfaces in cortical_resample_surface_ico6_sym.sh
read C_RAS_X C_RAS_Y C_RAS_Z \
    <<< $(mri_info --cras $FS_SYM/mri/orig.mgz)

echo ""
echo ">>> Converting lh.sphere to GIFTI"
mris_convert $FS_SYM/surf/lh.sphere $OUT/lh.sphere.surf.gii

for SURF_NAME in white pial; do

    echo ""
    echo ">>> Resampling lh.$SURF_NAME to ico6"

    mris_convert $FS_SYM/surf/lh.${SURF_NAME} \
                 $OUT/lh_${SURF_NAME}.surf.gii

    $WB -surface-resample \
        $OUT/lh_${SURF_NAME}.surf.gii \
        $OUT/lh.sphere.surf.gii \
        $TEMPLATE \
        BARYCENTRIC \
        $OUT/lh_${SURF_NAME}.ico6_sym.surf.gii

    $WB -set-structure \
        $OUT/lh_${SURF_NAME}.ico6_sym.surf.gii \
        CORTEX_LEFT \
        -surface-type ANATOMICAL

    echo ">>> Mirroring lh.$SURF_NAME to build the rh template"

    $WB -surface-flip-lr \
        $OUT/lh_${SURF_NAME}.ico6_sym.surf.gii \
        $OUT/rh_${SURF_NAME}.ico6_sym.surf.gii

    $WB -set-structure \
        $OUT/rh_${SURF_NAME}.ico6_sym.surf.gii \
        CORTEX_RIGHT \
        -surface-type ANATOMICAL

done

# ── Shift surfaces from TkReg RAS to scanner RAS ─────────────────────────────
TKRFILE=$(mktemp /tmp/tkr2scanner_XXXXXX.mat)
printf "1 0 0 %s\n0 1 0 %s\n0 0 1 %s\n0 0 0 1\n" \
    "$C_RAS_X" "$C_RAS_Y" "$C_RAS_Z" > "$TKRFILE"

for hemi in lh rh; do
    for SURF_NAME in white pial; do
        $WB -surface-apply-affine \
            $OUT/${hemi}_${SURF_NAME}.ico6_sym.surf.gii \
            "$TKRFILE" \
            $OUT/${hemi}_${SURF_NAME}.ico6_sym.surf.gii
    done
done
rm -f "$TKRFILE"

specfile=$OUT/fsaverage_sym_ico6.spec
my_do_cmd $WB -add-to-spec-file $specfile CORTEX_LEFT  $OUT/lh_white.ico6_sym.surf.gii
my_do_cmd $WB -add-to-spec-file $specfile CORTEX_LEFT  $OUT/lh_pial.ico6_sym.surf.gii
my_do_cmd $WB -add-to-spec-file $specfile CORTEX_RIGHT $OUT/rh_white.ico6_sym.surf.gii
my_do_cmd $WB -add-to-spec-file $specfile CORTEX_RIGHT $OUT/rh_pial.ico6_sym.surf.gii

echo ""
echo "========================================"
echo " Done."
echo " Output files in $OUT:"
ls $OUT/*_*.ico6_sym.surf.gii
echo "========================================"
echolor green "[INFO] wb_view `readlink -f $specfile`"
echo "========================================"
