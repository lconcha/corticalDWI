#!/bin/bash
# surface_to_ico6_sym.sh
#
# Registers FreeSurfer surfaces to fsaverage_sym (with xhemi for rh),
# resamples pial, white, and morphological metrics to a ico6 symmetric mesh,
# and flips rh back to native space.
#
# Usage: surface_to_ico6_sym.sh [-n nthreads] <subject_id>
#
# Requirements: FreeSurfer, Connectome Workbench
# Output: lh/rh.{pial,white,sulc,curv,thickness}.ico6_sym.{surf,func}.gii
#         in $SUBJECTS_DIR/<subject>/surf/
source `which my_do_cmd`

set -e

nthreads=1
while getopts "n:" opt; do
    case $opt in
        n) nthreads=$OPTARG ;;
        *) echo "Usage: $(basename $0) [-n num_threads] <subject_id>"; exit 1 ;;
    esac
done
shift $((OPTIND - 1))


# ── User-defined paths ────────────────────────────────────────────────────────
TEMPLATE=$SUBJECTS_DIR/templates/fsaverage_sym.sphere.ico6.surf.gii
WB=$(which wb_command)
# ─────────────────────────────────────────────────────────────────────────────

if [[ $# -ne 1 ]]; then
    echo "Usage: $(basename $0) <subject_id>"
    exit 1
fi

SUBJECT=$1
SURF=$SUBJECTS_DIR/$SUBJECT/surf
XHEMI=$SUBJECTS_DIR/$SUBJECT/xhemi/surf

echo "========================================"
echo " Subject : $SUBJECT"
echo " SURF    : $SURF"
echo " XHEMI   : $XHEMI"
echo " TEMPLATE: $TEMPLATE"
echo "========================================"

if [ -f $SURF/lh_white_ico6_sym.surf.gii ] && [ -f $SURF/rh_white_ico6_sym.surf.gii ]; then
    echo ">>> Surfaces already resampled to ico6_sym, skipping."
    exit 0
fi

# Sanity checks
[[ -d $SURF ]]     || { echo "ERROR: surf dir not found: $SURF";     exit 1; }

# Voxel size in x — used to correct the xhemi half-voxel flip-axis offset (Step 5)
VOX_SIZE_X=$(mri_info --cres $SUBJECTS_DIR/$SUBJECT/mri/orig.mgz)

# c_ras — used in final step to shift surfaces from TkReg RAS to scanner RAS
read C_RAS_X C_RAS_Y C_RAS_Z \
    <<< $(mri_info --cras $SUBJECTS_DIR/$SUBJECT/mri/orig.mgz)

# ── Step 0: Create ico6 symmetric template if it does not exist ───────────────
if [[ -f $TEMPLATE ]]; then
    echo ">>> Template already exists: $TEMPLATE"
else
    echo ""
    echo ">>> Step 0: Creating ico6 fsaverage_sym template"
    mkdir -p $(dirname $TEMPLATE)
 
    TEMPLATE_FS=$(dirname $TEMPLATE)/$(basename $TEMPLATE .surf.gii)
 
    mris_remesh \
        --nvert 40962 \
        -i $FREESURFER_HOME/subjects/fsaverage_sym/surf/lh.sphere \
        -o $TEMPLATE_FS
 
    mris_convert $TEMPLATE_FS $TEMPLATE
    echo "    Template created: $TEMPLATE"
fi


# ── Step 1: Register lh to fsaverage_sym ─────────────────────────────────────
echo ""
echo ">>> Step 1: surfreg lh -> fsaverage_sym"

if [[ -f $SURF/lh.fsaverage_sym.sphere.reg ]]; then
    echo "    lh.fsaverage_sym.sphere.reg already exists, skipping."
else
    surfreg --s $SUBJECT \
            --t fsaverage_sym \
            --lh \
            --no-annot \
            --threads $nthreads
fi

# ── Step 2: xhemireg + surfreg rh via xhemi ──────────────────────────────────
echo ""
echo ">>> Step 2: xhemireg + surfreg rh -> fsaverage_sym (via xhemi)"

if [[ -f $XHEMI/lh.fsaverage_sym.sphere.reg ]]; then
    echo "    xhemi/lh.fsaverage_sym.sphere.reg already exists, skipping."
else
    xhemireg --s $SUBJECT --threads $nthreads

    surfreg --s $SUBJECT \
            --t fsaverage_sym \
            --lh \
            --xhemi \
            --no-annot \
            --threads $nthreads
fi

# ── Step 3: Convert spheres to GIFTI ─────────────────────────────────────────
echo ""
echo ">>> Step 3: Convert spheres to GIFTI"

mris_convert $SURF/lh.sphere \
             $SURF/lh.sphere.surf.gii

mris_convert $SURF/lh.fsaverage_sym.sphere.reg \
             $SURF/lh.fsaverage_sym.sphere.reg.surf.gii

mris_convert $XHEMI/lh.sphere \
             $XHEMI/lh.sphere.surf.gii

mris_convert $XHEMI/lh.fsaverage_sym.sphere.reg \
             $XHEMI/lh.fsaverage_sym.sphere.reg.surf.gii

# ── Step 4: Resample pial and white surfaces to ico6 ───────────────────────────
echo ""
echo ">>> Step 4: Resample pial and white to ico6"

for SURF_NAME in white pial; do

    # Left hemisphere
    mris_convert \
                 $SURF/lh.${SURF_NAME} \
                 $SURF/lh.${SURF_NAME}.surf.gii


    $WB -surface-resample \
        $SURF/lh.${SURF_NAME}.surf.gii \
        $SURF/lh.fsaverage_sym.sphere.reg.surf.gii \
        $TEMPLATE \
        BARYCENTRIC \
        $SURF/lh_${SURF_NAME}_ico6_sym.surf.gii

    # Right hemisphere (from xhemi)
    mris_convert \
                 $XHEMI/lh.${SURF_NAME} \
                 $XHEMI/lh.${SURF_NAME}.surf.gii

    $WB -surface-resample \
        $XHEMI/lh.${SURF_NAME}.surf.gii \
        $XHEMI/lh.fsaverage_sym.sphere.reg.surf.gii \
        $TEMPLATE \
        BARYCENTRIC \
        $SURF/rh_${SURF_NAME}_ico6_sym.surf.gii

done

# ── Step 5: Flip rh back to native space ─────────────────────────────────────
echo ""
echo ">>> Step 5: Flip rh surfaces back to native (non-mirrored) space"

# xhemireg reflects voxels as i -> (N-1)-i, which in TkReg maps x -> -x - vox_size_x
# (flip axis is at x = -0.5*vox_size_x, not x=0). surface-flip-lr flips around x=0,
# so the round-trip leaves a residual translation of -vox_size_x when the voxel x
# direction is antiparallel to RAS x (x increases right-to-left). Correct with +vox_size_x.
CORRECTION=$(echo "$VOX_SIZE_X" | awk '{printf "%.6f", $1}')
XFMFILE=$(mktemp /tmp/xhemi_correction_XXXXXX.mat)
printf "1 0 0 %s\n0 1 0 0\n0 0 1 0\n0 0 0 1\n" "$CORRECTION" > "$XFMFILE"

for SURF_NAME in white pial; do
    $WB -surface-flip-lr \
        $SURF/rh_${SURF_NAME}_ico6_sym.surf.gii \
        $SURF/rh_${SURF_NAME}_ico6_sym.surf.gii

    $WB -surface-apply-affine \
        $SURF/rh_${SURF_NAME}_ico6_sym.surf.gii \
        "$XFMFILE" \
        $SURF/rh_${SURF_NAME}_ico6_sym.surf.gii
done
rm -f "$XFMFILE"

# ── Step 6: Set structure metadata ───────────────────────────────────────────
echo ""
echo ">>> Step 6: Set structure metadata"

for SURF_NAME in white pial; do
    $WB -set-structure \
        $SURF/lh_${SURF_NAME}_ico6_sym.surf.gii \
        CORTEX_LEFT \
        -surface-type ANATOMICAL

    $WB -set-structure \
        $SURF/rh_${SURF_NAME}_ico6_sym.surf.gii \
        CORTEX_RIGHT \
        -surface-type ANATOMICAL
done

# ── Step 7: Resample morphological metrics ────────────────────────────────────
echo ""
echo ">>> Step 7: Resample sulc, curv, thickness to ico6"

for METRIC in sulc curv thickness; do

    # Left hemisphere
    mris_convert -c \
        $SURF/lh.${METRIC} \
        $SURF/lh.white \
        $SURF/lh.${METRIC}.func.gii

    $WB -metric-resample \
        $SURF/lh.${METRIC}.func.gii \
        $SURF/lh.fsaverage_sym.sphere.reg.surf.gii \
        $TEMPLATE \
        ADAP_BARY_AREA \
        $SURF/lh.${METRIC}.ico6_sym.func.gii \
        -area-surfs \
        $SURF/lh.white.surf.gii \
        $SURF/lh_white_ico6_sym.surf.gii

    $WB -set-structure \
        $SURF/lh.${METRIC}.ico6_sym.func.gii \
        CORTEX_LEFT

    # Right hemisphere (from xhemi)
    mris_convert -c \
        $XHEMI/lh.${METRIC} \
        $XHEMI/lh.white \
        $XHEMI/lh.${METRIC}.func.gii

    $WB -metric-resample \
        $XHEMI/lh.${METRIC}.func.gii \
        $XHEMI/lh.fsaverage_sym.sphere.reg.surf.gii \
        $TEMPLATE \
        ADAP_BARY_AREA \
        $SURF/rh.${METRIC}.ico6_sym.func.gii \
        -area-surfs \
        $XHEMI/lh.white.surf.gii \
        $SURF/rh_white_ico6_sym.surf.gii

    $WB -set-structure \
        $SURF/rh.${METRIC}.ico6_sym.func.gii \
        CORTEX_RIGHT

done


# ── Step 8: Shift surfaces from TkReg RAS to scanner RAS ─────────────────────
echo ""
echo ">>> Step 8: Apply TkReg -> scanner RAS translation (c_ras = $C_RAS_X $C_RAS_Y $C_RAS_Z)"

TKRFILE=$(mktemp /tmp/tkr2scanner_XXXXXX.mat)
printf "1 0 0 %s\n0 1 0 %s\n0 0 1 %s\n0 0 0 1\n" \
    "$C_RAS_X" "$C_RAS_Y" "$C_RAS_Z" > "$TKRFILE"

for hemi in lh rh; do
    for SURF_NAME in white pial; do
        $WB -surface-apply-affine \
            $SURF/${hemi}_${SURF_NAME}_ico6_sym.surf.gii \
            "$TKRFILE" \
            $SURF/${hemi}_${SURF_NAME}_ico6_sym.surf.gii
    done
done
rm -f "$TKRFILE"


specfile=$SUBJECTS_DIR/$SUBJECT/surf/ico6_sym.spec
my_do_cmd $WB -add-to-spec-file $specfile CORTEX_LEFT $SURF/lh_white_ico6_sym.surf.gii
my_do_cmd $WB -add-to-spec-file $specfile CORTEX_LEFT $SURF/lh_pial_ico6_sym.surf.gii
my_do_cmd $WB -add-to-spec-file $specfile CORTEX_RIGHT $SURF/rh_white_ico6_sym.surf.gii
my_do_cmd $WB -add-to-spec-file $specfile CORTEX_RIGHT $SURF/rh_pial_ico6_sym.surf.gii
for METRIC in sulc curv thickness; do
  my_do_cmd $WB -add-to-spec-file $specfile CORTEX_LEFT  $SURF/lh.${METRIC}.ico6_sym.func.gii
  my_do_cmd $WB -add-to-spec-file $specfile CORTEX_RIGHT $SURF/rh.${METRIC}.ico6_sym.func.gii
done


# inflate surfaces
for hemi in lh rh; do
    my_do_cmd $WB -surface-generate-inflated \
      $SURF/${hemi}_white_ico6_sym.surf.gii \
      ${SURF}/${hemi}_white_ico6_sym_inflated.surf.gii \
      ${SURF}/${hemi}_white_ico6_sym_veryInflated.surf.gii
done



# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo " Done: $SUBJECT"
echo " Output files in $SURF:"
ls $SURF/*.ico6_sym.* 
echo "========================================"
echolor green "[INFO] wb_view `readlink -f $specfile`"
echo "========================================"