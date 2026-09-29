"""Vertex- and depth-wise z-scores of a subject's streamline-sampled metrics
against the normative (control cohort) data.

cortical_zscore_tsf.py compares each {hemi}_{target_type}_<metric>.tsf with
the cohort HDF5 built by cortical_create_normative_data_from_tsf.py
($SUBJECTS_DIR/templates/normative/{target_type}_multivariate.h5), and writes,
next to the tsf:
    <metric>_zscore.tsf                 z per streamline point
    <metric>_zscore_absmean.func.gii    mean |z| per vertex
    <metric>_zscore_abssum.func.gii     sum  |z| per vertex

That HDF5 is NOT produced by any rule here (the cohort is chosen by hand, in
templates/subjects_to_average.txt), so these rules only enter a subject's DAG
when it exists — see zscore_eligible(). Subjects listed in
subjects_to_average.txt are never z-scored: they are the normative data.

Two rules:
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


def _read_cohort():
    if not os.path.isfile(COHORT_FILE):
        return set()
    with open(COHORT_FILE) as f:
        return {line.strip() for line in f if line.strip()}


NORMATIVE_METRICS = _read_normative_metrics()
NORMATIVE_COHORT = _read_cohort()


def zscore_eligible(subject):
    return bool(NORMATIVE_METRICS) and subject not in NORMATIVE_COHORT


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
