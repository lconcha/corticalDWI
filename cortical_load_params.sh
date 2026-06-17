#!/bin/bash
# cortical_load_params.sh
# Source this file (do not execute) to load corticalDWI pipeline parameters.
#
# Loading priority (later sources override earlier ones):
#   1. Repo defaults  — corticalDWI_params.conf next to this file
#                       (found via BASH_SOURCE[0] or $CORTICAL_DWI_DIR)
#   2. Study overrides — $SUBJECTS_DIR/corticalDWI_params.conf
#
# CLI arguments passed to the calling script always take final priority
# (handled in each script individually, after sourcing this file).
#
# Required env variables:
#   CORTICAL_DWI_DIR  — path to the corticalDWI scripts directory
#                       Set this alongside SUBJECTS_DIR in your environment or
#                       pipeline entry-point script (cortical_singlesubject_fullprocess.sh).

# ── Locate repo conf ──────────────────────────────────────────────────────────
# BASH_SOURCE[0] is this file's path when sourced with a full/relative path.
# Fall back to CORTICAL_DWI_DIR when sourced by basename via PATH.
_clp_dir=""
if [[ "${BASH_SOURCE[0]}" == */* ]]; then
    _clp_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
elif [[ -n "$CORTICAL_DWI_DIR" ]]; then
    _clp_dir=$CORTICAL_DWI_DIR
fi

if [[ -n "$_clp_dir" && -f "${_clp_dir}/corticalDWI_params.conf" ]]; then
    # shellcheck source=corticalDWI_params.conf
    source "${_clp_dir}/corticalDWI_params.conf"
fi
unset _clp_dir

# ── Study-level overrides ─────────────────────────────────────────────────────
if [[ -n "$SUBJECTS_DIR" && -f "${SUBJECTS_DIR}/corticalDWI_params.conf" ]]; then
    echolor green "[INFO] Loading study-specific parameters: ${SUBJECTS_DIR}/corticalDWI_params.conf"
    source "${SUBJECTS_DIR}/corticalDWI_params.conf"
fi
