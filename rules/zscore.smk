"""Vertex- and depth-wise z-scores of a subject's streamline-sampled metrics
and single-scalar-per-vertex surface metrics against the normative (control
cohort) data.

cortical_zscore_tsf.py compares each {hemi}_{target_type}_<metric>.tsf, and
each {hemi}.<metric>.ico6_sym.func.gii (curv/sulc/thickness), with the cohort
HDF5 built by cortical_create_normative_data_from_tsf.py
($SUBJECTS_DIR/templates/normative/{target_type}_multivariate.h5), and writes,
next to each:
    <metric>_zscore.tsf                 z per streamline point (depth-wise)
    <metric>_zscore_absmean.func.gii    mean |z| per vertex     (depth-wise)
    <metric>_zscore_abssum.func.gii     sum  |z| per vertex     (depth-wise)
    <metric>_zscore.func.gii            z per vertex            (scalar — no
                                         depth axis, so no absmean/abssum)

That HDF5 is not produced automatically by any subject-dependent rule (the
cohort is chosen by hand, in templates/subjects_to_average.txt) — normative_stats,
zscore_tsf, and zscore_scalar_gii only enter a subject's DAG once it already
exists, see zscore_eligible(). Cohort subjects ARE z-scored too, same as
everyone else — a cohort subject's own value is part of the mean/std it's
compared against, so its z-scores are biased toward 0 (not a true held-out
deviation), but seeing them land near 0 is itself a useful sanity check on
the normative stats, see cortical_zscore_tsf.py's own docstring.

There IS a rule to build it, build_normative_data below, but it is deliberately
never an input of normative_stats/zscore_tsf/zscore_scalar_gii, nor of any
subject's default target — it must be triggered by name
(`cortical_snakerun.py build_normative_data` or `snakemake
build_normative_data`). Wiring it in automatically would mean the normative
baseline (and therefore everyone's z-scores) silently rebuilds and shifts
whenever some unrelated subject's .tsf output happens to change, instead of
only when a human deliberately decides the cohort or its data should change.

Four rules:
  build_normative_data once per dataset, by hand: builds the cohort HDF5
                itself from templates/subjects_to_average.txt. Re-run whenever
                browser_metrics, target_type, or that subject list changes —
                its declared input is just the cohort list file, not every
                cohort subject's .tsf/.func.gii files, so Snakemake has no way
                to notice a changed/added one on its own and won't rebuild
                for you.
  normative_stats  once per dataset: control mean/SD/n per vertex+depth, cached
                beside the HDF5. A rule of its own so parallel subject jobs
                never race to build it, and so it is rebuilt automatically
                whenever the HDF5 is newer.
  zscore_tsf    once per tsf file. The tsf can live in mri/, dwi/dti/,
                dwi/mrds/mrds_fixels/BIC/..., so the sub-directory is a
                wildcard matching any depth. Metrics are labelled
                <folder>/<name>, folder being the FULL path from the subject
                directory down (dwi/dti/fa, dwi/mrds/mrds_fixels/BIC/FA-par),
                so a metric several methods (or MRDS model-selection variants)
                produce under the same name is z-scored per method, each
                against its own cohort statistics.
  zscore_scalar_gii  once per single-scalar-per-vertex file (curv/sulc/
                thickness) — same idea as zscore_tsf, for the metrics
                resample_surface_ico6_sym writes under surf/ instead of a
                depth-wise .tsf.

Covariate adjustment (zscore_adjust_for / zscore_covariates_file in
corticalDWI_params.conf — see that file's own comment and
cortical_zscore_tsf.py's --adjust-for docstring) is OFF by default
(ZSCORE_ADJUST_FOR == ""), in which case every rule below behaves exactly as
described above. Set zscore_adjust_for to a continuous covariate column
(e.g. age_scan) to additionally produce, next to each z-score file above, a
<metric>_zscore_adj-<col>.* sibling.

That sibling is no longer a cheap per-vertex OLS computed on the fly — it's
gated on a real group-level significance test. A new rule, normative_glm_stats,
fits a BrainStat SLM (metric ~ covariate, both hemispheres combined into one
bilateral mesh, smoothed, FDR+RFT corrected — see cortical_glm_covariate.py)
once per metric/depth and writes slope/intercept/r/p-uncorrected/p-fdr/
p-rft/resid-sd as .func.gii under templates/normative/glm/. zscore_tsf and
zscore_scalar_gii then pass --adjust-for/--covariates/--rft-threshold to
cortical_zscore_tsf.py, which reads those GIFTIs and uses the BrainStat
slope/intercept/resid-sd as the predicted value+SD ONLY where that vertex/
depth's RFT CLUSTER-corrected p-value (p-rft) is below --rft-threshold
(zscore_adjust_rft_threshold, default 0.05); everywhere else it's not
adjusted at all (same as the plain z-score there). normative_glm_stats must
therefore complete, for every metric zscore_tsf/zscore_scalar_gii touch,
before --adjust-for can be used — cortical_zscore_tsf.py hard-errors if a
metric's GLM stats are missing rather than silently skipping the adjustment.

normative_stats still separately builds/caches the OLD fast per-vertex OLS
(NORMATIVE_ADJUST_STATS) when zscore_adjust_for is set — that one is no longer
read by the production z-scoring path above, but cortical_var_explorer.py
still uses it for its own interactive, no-BrainStat-run-required exploration
of any covariate; see that script's own docstring.
"""

import re

NORMATIVE_H5 = f"{SUBJECTS_DIR}/templates/normative/{TARGET_TYPE}_multivariate.h5"
NORMATIVE_STATS = NORMATIVE_H5[: -len(".h5")] + "_normative_stats.npz"
COHORT_FILE = f"{SUBJECTS_DIR}/templates/subjects_to_average.txt"

# Optional covariate adjustment (see corticalDWI_params.conf's own comment
# and cortical_zscore_tsf.py's --adjust-for docstring). ZSCORE_ADJUST_FOR
# empty (the default) disables this block entirely: ZSCORE_ADJUST_FLAGS is
# "", so every shell: command below is byte-for-byte what it was before this
# feature existed, and _adj_outputs() below returns [] everywhere it's used.
ZSCORE_ADJUST_FOR = config.get("zscore_adjust_for", "").strip()
ZSCORE_COVARIATES_FILE = config.get("zscore_covariates_file", "").strip()
ZSCORE_ADJUST_FWHM = config.get("zscore_adjust_fwhm", "10.0").strip()
ZSCORE_ADJUST_RFT_THRESHOLD = config.get("zscore_adjust_rft_threshold", "0.05").strip()
# Same sanitizing as cortical_zscore_tsf.py's _sanitize_label — must match,
# since that script is what actually names the files this predicts.
ZSCORE_ADJUST_TAG = re.sub(r"[^A-Za-z0-9_.-]+", "_", ZSCORE_ADJUST_FOR) if ZSCORE_ADJUST_FOR else ""
NORMATIVE_ADJUST_STATS = (NORMATIVE_H5[: -len(".h5")] + f"_normative_stats_adj-{ZSCORE_ADJUST_TAG}.npz"
                           if ZSCORE_ADJUST_FOR else None)
ZSCORE_ADJUST_FLAGS = ""
if ZSCORE_ADJUST_FOR:
    ZSCORE_ADJUST_FLAGS = f" --adjust-for {ZSCORE_ADJUST_FOR} --rft-threshold {ZSCORE_ADJUST_RFT_THRESHOLD}"
    if ZSCORE_COVARIATES_FILE:
        ZSCORE_ADJUST_FLAGS += f" --covariates {ZSCORE_COVARIATES_FILE}"

# GLM significance stats (cortical_glm_covariate.py): one set of 7 stat
# .func.gii per hemisphere per metric, same metric list as NORMATIVE_METRICS
# below (defined once that's read) — see normative_glm_stats.
GLM_DIR = f"{SUBJECTS_DIR}/templates/normative/glm"
GLM_STATS = ("slope", "intercept", "r", "p-uncorrected", "p-fdr", "p-rft", "resid-sd")
CORTEX_LABEL_FILES = [f"{SUBJECTS_DIR}/templates/surf/{h}.cortex.{TARGET_TYPE}.label.gii" for h in ("lh", "rh")]
WHITE_SURF_FILES = [f"{SUBJECTS_DIR}/templates/surf/{h}_white.{TARGET_TYPE}.surf.gii" for h in ("lh", "rh")]


def _read_normative_metrics():
    if not os.path.isfile(NORMATIVE_H5):
        return []
    import h5py
    with h5py.File(NORMATIVE_H5, "r") as h5f:
        return [m.decode() if isinstance(m, bytes) else m for m in h5f["metrics"][:]]


NORMATIVE_METRICS = _read_normative_metrics()


def zscore_eligible():
    return bool(NORMATIVE_METRICS)


def _glm_outputs():
    """Every {hemi}.{metric}_{covariate}_{stat}.{template}.func.gii
    cortical_glm_covariate.py writes, for every metric currently in the
    normative HDF5 — enumerated here (same trick as NORMATIVE_METRICS) so
    Snakemake can track them as ordinary static outputs without a metric
    wildcard. [] whenever covariate adjustment is off."""
    if not ZSCORE_ADJUST_FOR:
        return []
    outs = []
    for metric in NORMATIVE_METRICS:
        base = metric.replace("/", "_")
        for hemi in ("lh", "rh"):
            for stat in GLM_STATS:
                outs.append(f"{GLM_DIR}/{hemi}.{base}_{ZSCORE_ADJUST_FOR}_{stat}.{TARGET_TYPE}.func.gii")
    return outs


NORMATIVE_GLM_OUTPUTS = _glm_outputs()


def zscore_inputs(subject, tsf_files):
    """The tsf files to z-score: those whose <folder>/<name> label (folder = the
    FULL path from the subject directory down to the tsf, e.g. dwi/dti/fa vs
    dwi/dki/fa vs dwi/mrds/mrds_fixels/BIC/FA-par) is in the normative data."""
    subj_dir = f"{SUBJECTS_DIR}/{subject}"
    chosen = []
    for path in tsf_files:
        name = os.path.basename(path)
        prefix = f"{name[:2]}_{TARGET_TYPE}_"
        folder = os.path.relpath(os.path.dirname(path), subj_dir)
        label = f"{folder}/{name[len(prefix): -len('.tsf')]}"
        if label in NORMATIVE_METRICS:
            chosen.append(path)
    return chosen


def _adj_tsf_outputs(base):
    if not ZSCORE_ADJUST_FOR:
        return []
    abase = f"{base}_zscore_adj-{ZSCORE_ADJUST_TAG}"
    return [f"{abase}.tsf", f"{abase}_absmean.func.gii", f"{abase}_abssum.func.gii"]


def zscore_outputs(subject, tsf_files):
    outputs = []
    for path in zscore_inputs(subject, tsf_files):
        base = path[: -len(".tsf")]
        outputs += [f"{base}_zscore.tsf", f"{base}_zscore_absmean.func.gii", f"{base}_zscore_abssum.func.gii"]
        outputs += _adj_tsf_outputs(base)
    return outputs


# Single-scalar-per-vertex metrics (curv/sulc/thickness) have no z-score
# consumer of their own file list the way tsf metrics do (those come from
# various dwi/mri processing rules, collected into final_outputs' own
# `outputs` list) — there are only ever these three, always written by
# resample_surface_ico6_sym under surf/, hardcoded to the "ico6_sym" naming
# regardless of target_type (see that rule's own comment in
# rules/streamline_prep.smk), so the path is built directly here to match —
# NOT via rules.resample_surface_ico6_sym.output, which still carries an
# unresolved {subject} wildcard outside that rule's own job context.
_SCALAR_SURF_METRICS = ("sulc", "curv", "thickness")


def zscore_scalar_inputs(subject):
    subj_dir = f"{SUBJECTS_DIR}/{subject}"
    paths = []
    for hemi in ("lh", "rh"):
        for name in _SCALAR_SURF_METRICS:
            if f"surf/{name}" in NORMATIVE_METRICS:
                paths.append(f"{subj_dir}/surf/{hemi}.{name}.ico6_sym.func.gii")
    return paths


def zscore_scalar_outputs(subject):
    outputs = []
    for path in zscore_scalar_inputs(subject):
        base = path[: -len(".func.gii")]
        outputs.append(f"{base}_zscore.func.gii")
        if ZSCORE_ADJUST_FOR:
            outputs.append(f"{base}_zscore_adj-{ZSCORE_ADJUST_TAG}.func.gii")
    return outputs


rule build_normative_data:
    # Convenience wrapper, not a dependency link — see module docstring above
    # for why normative_stats/zscore_tsf must never depend on this. COHORT_FILE
    # as the only declared input is deliberate too: it makes Snakemake rerun
    # this when the cohort list is edited, without pretending to track every
    # cohort subject's .tsf files (that tracking would just invite the same
    # silent-auto-rebuild problem the module docstring warns against).
    input:
        COHORT_FILE,
    output:
        NORMATIVE_H5,
    threads: config["python_threads"]
    shell:
        "cortical_create_normative_data_from_tsf.py {SUBJECTS_DIR}"


rule normative_stats:
    input:
        h5=NORMATIVE_H5,
    output:
        [NORMATIVE_STATS] + ([NORMATIVE_ADJUST_STATS] if ZSCORE_ADJUST_FOR else []),
    threads: config["python_threads"]  # parallel workers reading the gzip'd HDF5
    shell:
        "cortical_zscore_tsf.py --stats-only {SUBJECTS_DIR} --workers {threads}" + ZSCORE_ADJUST_FLAGS


if ZSCORE_ADJUST_FOR:
    # Only defined when covariate adjustment is on — NORMATIVE_GLM_OUTPUTS is []
    # otherwise, and a rule can't declare zero output files.
    rule normative_glm_stats:
        # Group-level significance test cortical_zscore_tsf.py's --adjust-for
        # gates on (see module docstring and cortical_glm_covariate.py) — one
        # whole-dataset invocation, like normative_stats, not wildcarded per metric.
        input:
            # ZSCORE_COVARIATES_FILE is NOT declared here even when set: it may
            # contain an unexpanded $SUBJECTS_DIR (a real value seen in this
            # repo's own study configs), which only expands inside the shell:
            # string's actual bash invocation below, not when Snakemake checks
            # an input: path directly against the filesystem — same limitation
            # normative_stats/zscore_tsf/zscore_scalar_gii already accept for it.
            h5=NORMATIVE_H5,
            cortex=CORTEX_LABEL_FILES,
            white=WHITE_SURF_FILES,
        output:
            NORMATIVE_GLM_OUTPUTS,
        threads: config["python_threads"]
        shell:
            "cortical_glm_covariate.py {SUBJECTS_DIR} --covariate " + ZSCORE_ADJUST_FOR
            + (f" --covariates {ZSCORE_COVARIATES_FILE}" if ZSCORE_COVARIATES_FILE else "")
            + f" --fwhm {ZSCORE_ADJUST_FWHM} --out-dir {GLM_DIR}"
            + " --workers {threads}"


rule zscore_tsf:
    wildcard_constraints:
        subject="[^/]+",
        hemi="lh|rh",
        metric="[^/]+",
    input:
        tsf=f"{SUBJECTS_DIR}/{{subject}}/{{subdir}}/{{hemi}}_{TARGET_TYPE}_{{metric}}.tsf",
        stats=[NORMATIVE_STATS] + (NORMATIVE_GLM_OUTPUTS if ZSCORE_ADJUST_FOR else []),
    output:
        tsf=f"{SUBJECTS_DIR}/{{subject}}/{{subdir}}/{{hemi}}_{TARGET_TYPE}_{{metric}}_zscore.tsf",
        absmean=f"{SUBJECTS_DIR}/{{subject}}/{{subdir}}/{{hemi}}_{TARGET_TYPE}_{{metric}}_zscore_absmean.func.gii",
        abssum=f"{SUBJECTS_DIR}/{{subject}}/{{subdir}}/{{hemi}}_{TARGET_TYPE}_{{metric}}_zscore_abssum.func.gii",
        **(dict(
            tsf_adj=f"{SUBJECTS_DIR}/{{subject}}/{{subdir}}/{{hemi}}_{TARGET_TYPE}_{{metric}}_zscore_adj-{ZSCORE_ADJUST_TAG}.tsf",
            absmean_adj=f"{SUBJECTS_DIR}/{{subject}}/{{subdir}}/{{hemi}}_{TARGET_TYPE}_{{metric}}_zscore_adj-{ZSCORE_ADJUST_TAG}_absmean.func.gii",
            abssum_adj=f"{SUBJECTS_DIR}/{{subject}}/{{subdir}}/{{hemi}}_{TARGET_TYPE}_{{metric}}_zscore_adj-{ZSCORE_ADJUST_TAG}_abssum.func.gii",
        ) if ZSCORE_ADJUST_FOR else {}),
    # numpy on one tsf; threads: 2 (not 1) only so the Snakefile's blanket
    # mrtrix_threads default, which claims every threads: 1 rule, doesn't reserve 7 cores for it.
    threads: 2
    shell:
        "cortical_zscore_tsf.py {wildcards.subject} {SUBJECTS_DIR} --tsf {input.tsf}" + ZSCORE_ADJUST_FLAGS


rule zscore_scalar_gii:
    # Single-scalar-per-vertex sibling of zscore_tsf above — same shell tool,
    # just --gii instead of --tsf (cortical_zscore_tsf.py tells the two kinds
    # apart by file convention, not by an outputs list filtered here). Always
    # under surf/, hardcoded "ico6_sym" (not TARGET_TYPE) to match
    # resample_surface_ico6_sym's own pinned naming — see zscore_scalar_inputs.
    wildcard_constraints:
        subject="[^/]+",
        hemi="lh|rh",
        metric="[^/]+",
    input:
        gii=f"{SUBJECTS_DIR}/{{subject}}/surf/{{hemi}}.{{metric}}.ico6_sym.func.gii",
        stats=[NORMATIVE_STATS] + (NORMATIVE_GLM_OUTPUTS if ZSCORE_ADJUST_FOR else []),
    output:
        gii=f"{SUBJECTS_DIR}/{{subject}}/surf/{{hemi}}.{{metric}}.ico6_sym_zscore.func.gii",
        **(dict(
            gii_adj=f"{SUBJECTS_DIR}/{{subject}}/surf/{{hemi}}.{{metric}}.ico6_sym_zscore_adj-{ZSCORE_ADJUST_TAG}.func.gii",
        ) if ZSCORE_ADJUST_FOR else {}),
    threads: 2
    shell:
        "cortical_zscore_tsf.py {wildcards.subject} {SUBJECTS_DIR} --gii {input.gii}" + ZSCORE_ADJUST_FLAGS
