#!/bin/bash
source `which my_do_cmd`
fakeflag=" "

set -e

# ── User-defined paths ────────────────────────────────────────────────────────
TEMPLATE=$SUBJECTS_DIR/templates/fsaverage_sym.sphere.ico6.surf.gii
# ─────────────────────────────────────────────────────────────────────────────

subjid=$1
inScalar=$2; # relative path to scalar file in $SUBJECTS_DIR/$subjid
full_inScalar=$SUBJECTS_DIR/$subjid/$inScalar

if [[ -z "$subjid" || -z "$inScalar" ]]; then
    echo "Usage: $(basename $0) <subject_id> <lh|rh.scalar_name>"
    exit 1
fi

if [[ ! -f $TEMPLATE ]]; then
    echo "ERROR: ico6_sym template sphere not found: $TEMPLATE"
    echo "Run cortical_resample_surface_ico6_sym.sh for at least one subject first."
    exit 1
fi

ff=$(basename $inScalar)
hemi=${ff:0:2}
echolor green "[INFO] Resampling $inScalar to ico6_sym for subject $subjid, hemisphere $hemi"

tmpDir=$(mktemp -d -t resample_ico6_sym_XXXXXX)

SURF=$SUBJECTS_DIR/$subjid/surf
XHEMI=$SUBJECTS_DIR/$subjid/xhemi/surf

if [[ "$hemi" != "lh" && "$hemi" != "rh" ]]; then
    echo "ERROR: could not determine hemisphere (lh/rh) from scalar filename: $inScalar"
    rm -fR $tmpDir
    exit 1
fi

if [[ ! -f $SURF/lh.fsaverage_sym.sphere.reg.surf.gii || ! -f $XHEMI/lh.fsaverage_sym.sphere.reg.surf.gii ]]; then
    echo "ERROR: symmetric sphere registration not found for subject $subjid."
    echo "Run cortical_resample_surface_ico6_sym.sh $subjid first."
    rm -fR $tmpDir
    exit 1
fi


if [[ "$hemi" == "lh" ]]; then
# Left hemisphere
my_do_cmd $fakeflag mris_convert -c \
    $full_inScalar \
    $SURF/lh.white \
    ${tmpDir}/${ff}.func.gii

f_metric_resampled_to_ico6_sym=$SURF/$(basename $inScalar).ico6_sym.func.gii
my_do_cmd $fakeflag wb_command -metric-resample \
    ${tmpDir}/${ff}.func.gii \
    $SURF/lh.fsaverage_sym.sphere.reg.surf.gii \
    $TEMPLATE \
    ADAP_BARY_AREA \
    $f_metric_resampled_to_ico6_sym \
    -area-surfs \
    $SURF/lh.white.surf.gii \
    $SURF/lh_white_ico6_sym.surf.gii

my_do_cmd $fakeflag wb_command -set-structure \
    $f_metric_resampled_to_ico6_sym \
    CORTEX_LEFT

echolor cyan "[INFO] (Check with:) freeview -f  $SURF/lh.white:overlay=$full_inScalar -f $SURF/lh_white_ico6_sym.surf.gii:overlay=$f_metric_resampled_to_ico6_sym"
fi

if [[ "$hemi" == "rh" ]]; then
# Right hemisphere (from xhemi)
my_do_cmd $fakeflag mris_convert -c \
    $full_inScalar \
    $XHEMI/lh.white \
    ${tmpDir}/${ff}.func.gii

f_metric_resampled_to_ico6_sym=$SURF/$(basename $inScalar).ico6_sym.func.gii
my_do_cmd $fakeflag wb_command -metric-resample \
    ${tmpDir}/${ff}.func.gii \
    $XHEMI/lh.fsaverage_sym.sphere.reg.surf.gii \
    $TEMPLATE \
    ADAP_BARY_AREA \
    $f_metric_resampled_to_ico6_sym \
    -area-surfs \
    $XHEMI/lh.white.surf.gii \
    $SURF/rh_white_ico6_sym.surf.gii

my_do_cmd $fakeflag wb_command -set-structure \
    $f_metric_resampled_to_ico6_sym \
    CORTEX_RIGHT

echolor cyan "[INFO] (Check with:) freeview -f $SURF/rh.white:overlay=$full_inScalar -f $SURF/rh_white_ico6_sym.surf.gii:overlay=$f_metric_resampled_to_ico6_sym"
fi


echolor green "[INFO] Resampled metric saved to: $f_metric_resampled_to_ico6_sym"


rm -fR $tmpDir