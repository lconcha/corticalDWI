#!/bin/bash
# cortical_status.sh
# Reports corticalDWI pipeline completion by probing key output files.
# Step definitions are read from cortical_status_steps.conf (same directory).

G='\033[0;32m'
R='\033[0;31m'
Y='\033[1;33m'
B='\033[1m'
NC='\033[0m'

target_type=ico6_sym          # built-in fallback
target_type_cli=""            # set only when -t is explicitly passed
fixel_dir=csd_fixels_singletissue  # built-in fallback
fixel_dir_cli=""               # set only when -f is explicitly passed
tsv_mode=0
remaining_mode=0
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
config_file="${script_dir}/cortical_status_steps.conf"

# 1. Repo-level defaults
[[ -f "${script_dir}/corticalDWI_params.conf" ]] && source "${script_dir}/corticalDWI_params.conf"

# ── Helpers ───────────────────────────────────────────────────────────────────

trim() { sed 's/^[[:space:]]*//;s/[[:space:]]*$//' <<< "$1"; }

chk() { [ -f "$1" ] && echo 1 || echo 0; }

load_config() {
    labels=(); longnames=(); patterns=()
    while IFS='|' read -r label longname pattern || [[ -n "$label" ]]; do
        [[ "$label" =~ ^[[:space:]]*# || -z "${label// }" ]] && continue
        labels+=("$(trim "$label")")
        longnames+=("$(trim "$longname")")
        patterns+=("$(trim "$pattern")")
    done < "$1"
    if [ ${#labels[@]} -eq 0 ]; then
        echo "ERROR: No steps found in config: $1" >&2; exit 1
    fi
}

usage() {
    cat <<EOF

Usage: $(basename "$0") [options] [subject1 subject2 ...]

Reports which corticalDWI pipeline steps are complete for each subject
by checking for key output files. Nothing is run or re-run.

Arguments:
  [subject...]     Subject IDs to check (default: all sub-* in SUBJECTS_DIR)

Options:
  -t <type>   Surface target type (default: ${target_type})
  -f <dir>    Fixel directory name, relative to dwi/, for the sCSD step
              (default: ${fixel_dir})
  -c <file>   Step config file (default: cortical_status_steps.conf)
  -r          List remaining (incomplete) steps per subject with long names
  -T          TSV output — machine-readable, no colors (1=done, 0=missing)
  -h          Show this help

EOF
    if [ -f "$config_file" ]; then
        echo "Steps from $(basename "$config_file"):"
        load_config "$config_file"
        for i in "${!labels[@]}"; do
            printf "  %-6s %-42s %s\n" \
                "${labels[$i]}" "${longnames[$i]}" "${patterns[$i]}"
        done
        echo ""
    fi
    cat <<'EOF'
Examples:
  cortical_status.sh /data/subjects
  cortical_status.sh -t fsLR-32k /data/subjects sub-001 sub-002
  cortical_status.sh -f csd_fixels /data/subjects                # check a different fixel dir
  cortical_status.sh -T /data/subjects | awk -F'\t' '$5==0'   # missing REG
  cortical_status.sh -r /data/subjects                        # what still needs to run
EOF
}

# ── Args ──────────────────────────────────────────────────────────────────────

while getopts "t:f:c:rTh" opt; do
    case $opt in
        t) target_type_cli=$OPTARG ;;
        f) fixel_dir_cli=$OPTARG ;;
        c) config_file=$OPTARG ;;
        r) remaining_mode=1 ;;
        T) tsv_mode=1 ;;
        h) usage; exit 0 ;;
        *) usage; exit 1 ;;
    esac
done
shift $((OPTIND-1))

[ ! -f "$config_file" ] && { echo "ERROR: Config not found: $config_file" >&2; exit 1; }
load_config "$config_file"

[ -z "$SUBJECTS_DIR" ] && { echo "ERROR: <SUBJECTS_DIR> required." >&2; usage; exit 1; }
[ ! -d "$SUBJECTS_DIR" ] && { echo "ERROR: Not a directory: $SUBJECTS_DIR" >&2; exit 1; }

# 2. Study-level overrides (may reset target_type)
[[ -f "${SUBJECTS_DIR}/corticalDWI_params.conf" ]] && source "${SUBJECTS_DIR}/corticalDWI_params.conf"

# 3. CLI -t / -f win over everything
[[ -n "$target_type_cli" ]] && target_type=$target_type_cli
[[ -n "$fixel_dir_cli" ]] && fixel_dir=$fixel_dir_cli

if [ $# -gt 0 ]; then
    subjects=("$@")
else
    mapfile -t subjects < <(ls -d "${SUBJECTS_DIR}"/sub-* 2>/dev/null | xargs -n1 basename)
fi
[ ${#subjects[@]} -eq 0 ] && { echo "No sub-* directories found in ${SUBJECTS_DIR}" >&2; exit 1; }

# ── Layout ────────────────────────────────────────────────────────────────────

n_steps=${#labels[@]}
subj_w=16

# Column width: widest label + 1 padding
col_w=4
for lbl in "${labels[@]}"; do [ ${#lbl} -gt $col_w ] && col_w=${#lbl}; done
(( col_w++ ))

cell_w=$(( col_w + 2 ))   # 2 leading spaces per cell
total_w=$(( subj_w + n_steps * cell_w + 8 ))

# ── Header ────────────────────────────────────────────────────────────────────
if [ "$remaining_mode" -eq 0 ]; then
    if [ "$tsv_mode" -eq 1 ]; then
        printf "subject"
        for lbl in "${labels[@]}"; do printf "\t%s" "$lbl"; done
        printf "\n"
    else
        printf "${B}%-${subj_w}s${NC}" "SUBJECT"
        for lbl in "${labels[@]}"; do printf "  ${B}%-${col_w}s${NC}" "$lbl"; done
        printf "\n"
        printf '%0.s-' $(seq 1 $total_w); printf "\n"
    fi
fi

# ── Per-subject rows ──────────────────────────────────────────────────────────

n_done=0; n_total=0

for sID in "${subjects[@]}"; do
    if [ -f ${SUBJECTS_DIR}/${sID}/skip ]; then
        continue
    fi
    sd="${SUBJECTS_DIR}/${sID}"

    if [ ! -d "$sd" ]; then
        if [ "$tsv_mode" -eq 1 ]; then
            printf "%s" "$sID"
            for _ in "${labels[@]}"; do printf "\t?"; done
            printf "\n"
        else
            printf "${Y}%-${subj_w}s  (directory not found)${NC}\n" "$sID"
        fi
        continue
    fi

    steps=()
    for pattern in "${patterns[@]}"; do
        resolved="${sd}/${pattern/\{target_type\}/${target_type}}"
        resolved="${resolved/\{fixel_dir\}/${fixel_dir}}"
        steps+=("$(chk "$resolved")")
    done

    subj_done=0
    for s in "${steps[@]}"; do (( subj_done += s )); done
    (( n_done  += subj_done ))
    (( n_total += n_steps   ))

    if [ "$remaining_mode" -eq 1 ]; then
        local_remaining=()
        for i in "${!steps[@]}"; do
            [ "${steps[$i]}" -eq 0 ] && local_remaining+=("$i")
        done
        if [ ${#local_remaining[@]} -eq 0 ]; then
            printf "${G}%s${NC}  (complete)\n" "$sID"
        else
            printf "${B}%s${NC}  (%d remaining):\n" "$sID" "${#local_remaining[@]}"
            for i in "${local_remaining[@]}"; do
                printf "  ${R}%-6s${NC}  %s\n" "${labels[$i]}" "${longnames[$i]}"
            done
        fi
    elif [ "$tsv_mode" -eq 1 ]; then
        printf "%s" "$sID"
        for s in "${steps[@]}"; do printf "\t%s" "$s"; done
        printf "\n"
    else
        printf "%-${subj_w}s" "$sID"
        pad=$(( col_w - 1 ))   # ✓/✗ is 1 visible char; fill the rest
        for s in "${steps[@]}"; do
            if [ "$s" -eq 1 ]; then
                printf "  ${G}✓${NC}%*s" $pad ""
            else
                printf "  ${R}✗${NC}%*s" $pad ""
            fi
        done
        printf "  (%d/%d)\n" "$subj_done" "$n_steps"
    fi
done

# ── Summary ───────────────────────────────────────────────────────────────────

if [ "$tsv_mode" -eq 0 ] && [ "$remaining_mode" -eq 0 ] && [ "$n_total" -gt 0 ]; then
    printf '%0.s-' $(seq 1 $total_w); printf "\n"
    pct=$(( n_done * 100 / n_total ))
    printf "Total: ${G}%d${NC} / %d steps done across %d subject(s) (%d%%) for target type ${G}%s${NC}\n" \
        "$n_done" "$n_total" "${#subjects[@]}" "$pct" "$target_type"
fi