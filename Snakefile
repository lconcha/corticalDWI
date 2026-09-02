"""
Snakemake orchestration for the corticalDWI pipeline.

This wraps the existing, working cortical_*.sh module scripts as-is — it is
an orchestration layer, not a reimplementation. Every rule calls the same
script cortical_singlesubject_fullprocess.sh already calls; Snakemake just
replaces that script's hardcoded sequential order with a real dependency
graph, and replaces cortical_status.sh's hand-maintained manifest with
`snakemake -n` / `--dag` / `--rulegraph`.

Prerequisites (unchanged from cortical_singlesubject_fullprocess.sh):
  module load freesurfer/8.1 mrtrix/3.0.4 workbench_con/2.0.1 ANTs/2.4.4 mrds/1.2.0
  path_add /misc/lauterbur2/lconcha/code/corticalDWI/
  path_add /misc/lauterbur2/lconcha/code/inb_mrtrix_modules/bin
  path_add /misc/lauterbur2/lconcha/code/inb_mrtrix_modules/scripts
  export SUBJECTS_DIR=/path/to/freesurfer/subjects

Config cascade (mirrors corticalDWI_params.conf's own repo-default ->
study-override pattern): this repo's config.yaml supplies defaults; if
$SUBJECTS_DIR/.corticalDWI/config.yaml exists, its keys override those
defaults for this dataset only. Same idea for the CSD group-average
snapshot list and cluster job logs — see rules/csd.smk and
profiles/sge_don_clusterio/ (a template to copy into
$SUBJECTS_DIR/.corticalDWI/snakemake_profile/ and adjust per cluster).

Usage:
  snakemake -n                      # dry run — what's done, what would run
  snakemake --rulegraph | dot -Tpng > dag.png
  snakemake --cores 20              # run locally, thread-aware scheduling
  snakemake --profile $SUBJECTS_DIR/.corticalDWI/snakemake_profile
                                     # submit to a cluster (see that profile)

Want to run just one module for one subject, bash-script-style, without
hand-building a target path? Use cortical_snakerun.py instead of snakemake
directly — it interrogates this Snakefile fresh on every call (never a
hardcoded rule list) and resolves the target path + thread count for you:
  cortical_snakerun.py                    # list every rule + target + threads
  cortical_snakerun.py dti sub-79291      # run just DTI for one subject
  cortical_snakerun.py mrds sub-79291 -R  # extra snakemake args pass through

Use --cores, not a bare job count like -j4, for local runs: rules/mrds.smk,
rules/dki.smk, rules/dti.smk, and rules/noddi.smk declare threads: (from
config["mrds_threads"]/["python_threads"]) for the tools confirmed to respect
OMP_NUM_THREADS/OPENBLAS_NUM_THREADS on this host (see
reference_omp_threads_pinned_to_1 memory) — Snakemake uses --cores as the
total budget and packs concurrent jobs to fit inside it, honoring each rule's
threads:. A bare "-j4" (as used during initial testing) does NOT do this:
without --cores, Snakemake treats every job as needing 1 slot regardless of
threads:, so it can schedule e.g. mrds (wanting many threads) concurrently
with other jobs that also each grab threads, wildly oversubscribing the
machine. --cores 20 leaves a couple of this host's 32 cores free; raise/lower
based on who else is using it (check `who`/`uptime` first — this host is not
always exclusively yours).
"""

import os
import glob

# Symlink-safe repo location, so this Snakefile can be symlinked into
# $SUBJECTS_DIR (for plain `snakemake` with no -s/--directory flags) without
# breaking the configfile:/include: lines below. Deliberately NOT using
# Snakemake's own workflow.basedir/srcdir() here — checked the installed
# Snakemake's source (2026-08-26): it computes basedir via os.path.abspath()
# on the snakefile path, not os.path.realpath(), so it still resolves to the
# symlink's apparent directory, not this repo — same failure, different code
# path. CORTICAL_DWI_DIR mirrors the existing override convention already
# used by cortical_load_params.sh.
CORTICAL_DWI_DIR = os.environ.get("CORTICAL_DWI_DIR", "/misc/lauterbur2/lconcha/code/corticalDWI")

SUBJECTS_DIR = os.environ.get("SUBJECTS_DIR")
if not SUBJECTS_DIR:
    raise WorkflowError(
        "SUBJECTS_DIR is not set. Export it before running snakemake, "
        "same as you would before running cortical_singlesubject_fullprocess.sh."
    )
SUBJECTS_DIR = SUBJECTS_DIR.rstrip("/")

# Per-dataset scaffold: config overrides, the CSD snapshot, and cluster job
# logs all live here rather than in the repo, so the same versioned pipeline
# can serve multiple datasets (and multiple clusters) with different settings.
# Dot-prefixed so `ls`/sub-* globs (including this Snakefile's own subject
# auto-discovery below) never pick it up.
STUDY_DIR = f"{SUBJECTS_DIR}/.corticalDWI"
os.makedirs(f"{STUDY_DIR}/logs", exist_ok=True)

configfile: f"{CORTICAL_DWI_DIR}/config.yaml"

# A second configfile: (rather than a manual config.update()) so Snakemake's
# own provenance-aware merge applies here too: values from this study file
# override the repo defaults above, but a CLI --config override still wins
# over both. A plain config.update(yaml.safe_load(...)) was tried first and
# is wrong — it clobbers CLI --config values with whatever this file
# happens to set for the same key (found 2026-08-27: --config
# subjects=["sub-79291"] was silently ignored whenever this file existed,
# because it unconditionally set config["subjects"] = [] via .update()).
study_config_file = f"{STUDY_DIR}/config.yaml"
if os.path.exists(study_config_file):
    configfile: study_config_file

TARGET_TYPE = config["target_type"]

if config.get("subjects"):
    SUBJECTS = config["subjects"]
else:
    SUBJECTS = sorted(
        os.path.basename(d) for d in glob.glob(f"{SUBJECTS_DIR}/sub-*") if os.path.isdir(d)
    )
    SUBJECTS = [s for s in SUBJECTS if not os.path.exists(f"{SUBJECTS_DIR}/{s}/skip")]

if not SUBJECTS:
    raise WorkflowError(f"No sub-* directories found in {SUBJECTS_DIR}")

HEMIS = ["lh", "rh"]

# Prepended to the shell: command of every rule that reads the big raw DWI
# volume directly off NFS (mrds, dki, noddi, dti, csd_individual_response,
# csd_compute_fod), so a burst of jobs starting at once doesn't hit the
# shared filesystem with several full-volume reads in the same instant.
# Lives here, not in the wrapped scripts themselves — running e.g.
# cortical_MRDS.sh directly, outside Snakemake, never waits.
JITTER = "sleep $((RANDOM % 45)); "

# Prepended to EVERY rule's shell: command (2026-08-27). MRtrix tools
# (mrconvert, mrcalc, tckedit, tcksample, dwi2tensor, dwi2fod, ...) are not
# OpenMP-linked (confirmed via ldd — see reference_omp_threads_pinned_to_1
# memory) so OMP_NUM_THREADS never touched them, but they auto-detect and use
# every core they find by default regardless — completely invisible to
# Snakemake's own threads:/--cores accounting, and completely independent of
# the OMP_NUM_THREADS prefix already used for mrds/dki/noddi/register_t1_to_dwi.
# MRTRIX_NTHREADS (an MRtrix-specific env var, NOT documented in `--help` —
# https://mrtrix.readthedocs.io/en/dev/reference/environment_variables.html —
# found only after grepping --help output and binary strings came up empty)
# overrides MRtrix's auto-detection; explicit -nthreads CLI flags in a wrapped
# script still take precedence over it per MRtrix's own docs, so this is safe
# to apply blanket — including on cortical_compute_streamlines.sh's tckedit
# call, whose deterministic-ordering requirement is protected by a hardcoded
# `-nthreads 1` CLI flag directly in that script (not by this rule staying at
# Snakemake's own threads: 1), so raising its MRTRIX_NTHREADS same as every
# other rule below can never touch that guarantee.
MRTRIX_ENV = "MRTRIX_NTHREADS={threads} "

include: f"{CORTICAL_DWI_DIR}/rules/streamline_prep.smk"
include: f"{CORTICAL_DWI_DIR}/rules/dti.smk"
include: f"{CORTICAL_DWI_DIR}/rules/csd.smk"
include: f"{CORTICAL_DWI_DIR}/rules/mrds.smk"
include: f"{CORTICAL_DWI_DIR}/rules/dki.smk"
include: f"{CORTICAL_DWI_DIR}/rules/noddi.smk"
include: f"{CORTICAL_DWI_DIR}/rules/structural.smk"

# One global default thread count for the "just a few MRtrix calls" majority
# of rules, so a new rule doesn't need its own threads: line added by hand
# for MRTRIX_ENV above to actually give it more than Snakemake's own
# implicit default of 1. Runs once, right here, after every rules/*.smk
# above has registered its rules on `workflow.rules` — mrds/dki/noddi/
# register_t1_to_dwi already claimed their own dedicated threads: (see
# config.yaml's comment on why those four stay separate), so this only
# touches whatever's still sitting at the untouched default of 1. Mutating
# rule.resources["_cores"] directly like this is exactly what Snakemake's
# own --set-threads CLI flag does internally (confirmed in its source,
# snakemake/workflow.py — see reference_snakemake_mrtrix_threads_default
# memory) — this is the same mechanism, just applied programmatically
# instead of needing RULE=N spelled out on the command line for every rule.
for _rule in workflow.rules:
    if _rule.name != "all" and _rule.resources.get("_cores", 1) == 1:
        _rule.resources["_cores"] = config["mrtrix_threads"]


def final_outputs(subject):
    """Every leaf (terminal) output for one subject. Nothing downstream
    depends on these, so requesting them pulls in the whole DAG behind them."""
    return (
        tcksample_dti_outputs(subject)
        + tcksamplefixels_afd_outputs(subject)
        + tcksamplefixels_mrds_outputs(subject)
        + tcksample_dki_outputs(subject)
        + tcksample_noddi_outputs(subject)
        + tcksample_mri_outputs(subject)
    )


rule all:
    input:
        [f for subject in SUBJECTS for f in final_outputs(subject)],
