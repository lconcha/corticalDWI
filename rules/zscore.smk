"""Vertex- and depth-wise z-scores of a subject's streamline-sampled metrics
against the normative (control cohort) data.

cortical_zscore_tsf.py compares each {hemi}_{target_type}_<metric>.tsf with
the cohort HDF5 built by cortical_create_normative_data_from_tsf.py
($SUBJECTS_DIR/templates/normative/{target_type}_multivariate.h5), and writes,
next to the tsf:
    <metric>_zscore.tsf                 z per streamline point
    <metric>_zscore_absmean.func.gii    mean |z| per vertex
    <metric>_zscore_abssum.func.gii     sum  |z| per vertex

That HDF5 is not produced automatically by any subject-dependent rule (the
cohort is chosen by hand, in templates/subjects_to_average.txt) — zscore_stats
and zscore_tsf only enter a subject's DAG once it already exists, see
zscore_eligible(). Cohort subjects ARE z-scored too, same as everyone else —
a cohort subject's own value is part of the mean/std it's compared against,
so its z-scores are biased toward 0 (not a true held-out deviation), but
seeing them land near 0 is itself a useful sanity check on the normative
stats, see cortical_zscore_tsf.py's own docstring.

There IS a rule to build it, build_normative_data below, but it is deliberately
never an input of zscore_stats/zscore_tsf, nor of any subject's default
target — it must be triggered by name (`cortical_snakerun.py
build_normative_data` or `snakemake build_normative_data`). Wiring it in
automatically would mean the normative baseline (and therefore everyone's
z-scores) silently rebuilds and shifts whenever some unrelated subject's .tsf
output happens to change, instead of only when a human deliberately decides
the cohort or its data should change.

Three rules:
  build_normative_data once per dataset, by hand: builds the cohort HDF5
                itself from templates/subjects_to_average.txt. Re-run whenever
                browser_metrics, target_type, or that subject list changes —
                its declared input is just the cohort list file, not every
                cohort subject's .tsf files, so Snakemake has no way to notice
                a changed/added .tsf on its own and won't rebuild for you.
  zscore_stats  once per dataset: control mean/SD/n per vertex+depth, cached
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
"""

NORMATIVE_H5 = f"{SUBJECTS_DIR}/templates/normative/{TARGET_TYPE}_multivariate.h5"
ZSCORE_STATS = NORMATIVE_H5[: -len(".h5")] + "_zscore_stats.npz"
COHORT_FILE = f"{SUBJECTS_DIR}/templates/subjects_to_average.txt"


def _read_normative_metrics():
    if not os.path.isfile(NORMATIVE_H5):
        return []
    import h5py
    with h5py.File(NORMATIVE_H5, "r") as h5f:
        return [m.decode() if isinstance(m, bytes) else m for m in h5f["metrics"][:]]


NORMATIVE_METRICS = _read_normative_metrics()


def zscore_eligible():
    return bool(NORMATIVE_METRICS)


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


def zscore_outputs(subject, tsf_files):
    outputs = []
    for path in zscore_inputs(subject, tsf_files):
        base = path[: -len(".tsf")]
        outputs += [f"{base}_zscore.tsf", f"{base}_zscore_absmean.func.gii", f"{base}_zscore_abssum.func.gii"]
    return outputs


rule build_normative_data:
    # Convenience wrapper, not a dependency link — see module docstring above
    # for why zscore_stats/zscore_tsf must never depend on this. COHORT_FILE
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


rule zscore_stats:
    input:
        h5=NORMATIVE_H5,
    output:
        ZSCORE_STATS,
    threads: config["python_threads"]  # parallel workers reading the gzip'd HDF5
    shell:
        "cortical_zscore_tsf.py --stats-only {SUBJECTS_DIR} --workers {threads}"


rule zscore_tsf:
    wildcard_constraints:
        subject="[^/]+",
        hemi="lh|rh",
        metric="[^/]+",
    input:
        tsf=f"{SUBJECTS_DIR}/{{subject}}/{{subdir}}/{{hemi}}_{TARGET_TYPE}_{{metric}}.tsf",
        stats=ZSCORE_STATS,
    output:
        tsf=f"{SUBJECTS_DIR}/{{subject}}/{{subdir}}/{{hemi}}_{TARGET_TYPE}_{{metric}}_zscore.tsf",
        absmean=f"{SUBJECTS_DIR}/{{subject}}/{{subdir}}/{{hemi}}_{TARGET_TYPE}_{{metric}}_zscore_absmean.func.gii",
        abssum=f"{SUBJECTS_DIR}/{{subject}}/{{subdir}}/{{hemi}}_{TARGET_TYPE}_{{metric}}_zscore_abssum.func.gii",
    # numpy on one tsf; threads: 2 (not 1) only so the Snakefile's blanket
    # mrtrix_threads default, which claims every threads: 1 rule, doesn't reserve 7 cores for it.
    threads: 2
    shell:
        "cortical_zscore_tsf.py {wildcards.subject} {SUBJECTS_DIR} --tsf {input.tsf}"
