"""T1/FLAIR structural processing and streamline sampling of structural metrics.

cortical_tcksample_mri.sh samples from the T1-space streamlines
(mri/{hemi}_{target_type}_laplace-wm-streamlines.tck, cortical_compute_streamlines.sh's
output) rather than the dwi-space warped ones every other tcksample_* script uses —
preserved as-is, not a porting mistake.

flair.nii.gz is optional, unlike everything else in this file: proc_flair and
tcksample_mri_flair only ever enter a subject's DAG when has_flair(subject) is
true (wired in via tcksample_mri_outputs() below, consumed by final_outputs()
in the Snakefile). proc_t1/tcksample_mri_t1 have no such gate — like
laplacian/resample_surface_ico6_sym/compute_streamlines in
rules/streamline_prep.smk, they have no dwi/ dependency either, so they (and,
conditionally, proc_flair/tcksample_mri_flair) are exactly what still runs for
a subject with no dwi/ data at all.
"""

STRUCTURAL_METRICS_T1 = ["T1w_proc", "T1w_proc_grad"]
STRUCTURAL_METRICS_FLAIR = ["flair_proc", "T1_over_FLAIR"]


def has_flair(subject):
    return os.path.exists(f"{SUBJECTS_DIR}/{subject}/mri/flair.nii.gz")


rule proc_t1:
    input:
        orig=f"{SUBJECTS_DIR}/{{subject}}/mri/orig.mgz",
        brain=f"{SUBJECTS_DIR}/{{subject}}/mri/brain.mgz",
        wm_seg=f"{SUBJECTS_DIR}/{{subject}}/mri/wm.seg.mgz",
    output:
        t1w_proc=f"{SUBJECTS_DIR}/{{subject}}/mri/T1w_proc.nii.gz",
        t1w_proc_grad=f"{SUBJECTS_DIR}/{{subject}}/mri/T1w_proc_grad.nii.gz",
    shell:
        MRTRIX_ENV + "cortical_proc_t1.sh {wildcards.subject}"


rule proc_flair:
    input:
        flair=f"{SUBJECTS_DIR}/{{subject}}/mri/flair.nii.gz",
        t1=f"{SUBJECTS_DIR}/{{subject}}/mri/T1.mgz",
        aseg=f"{SUBJECTS_DIR}/{{subject}}/mri/aseg.mgz",
        brainmask=f"{SUBJECTS_DIR}/{{subject}}/mri/brainmask.mgz",
        t1w_proc=rules.proc_t1.output.t1w_proc,
    output:
        flair_proc=f"{SUBJECTS_DIR}/{{subject}}/mri/flair_proc.nii.gz",
        t1_over_flair=f"{SUBJECTS_DIR}/{{subject}}/mri/T1_over_FLAIR.nii.gz",
    shell:
        MRTRIX_ENV + "cortical_proc_FLAIR.sh {wildcards.subject}"


def tcksample_mri_t1_outputs(subject):
    return [
        f"{SUBJECTS_DIR}/{subject}/mri/{hemi}_{TARGET_TYPE}_{m}.tsf"
        for hemi in HEMIS
        for m in STRUCTURAL_METRICS_T1
    ]


rule tcksample_mri_t1:
    input:
        tck=lambda wc: compute_streamlines_outputs(wc.subject)[:2],
        t1w_proc=rules.proc_t1.output.t1w_proc,
        t1w_proc_grad=rules.proc_t1.output.t1w_proc_grad,
    output:
        tcksample_mri_t1_outputs("{subject}"),
    shell:
        MRTRIX_ENV + "cortical_tcksample_mri.sh {wildcards.subject} "
        f"{{config[nDepths]}} {TARGET_TYPE} \"{' '.join(STRUCTURAL_METRICS_T1)}\""


def tcksample_mri_flair_outputs(subject):
    return [
        f"{SUBJECTS_DIR}/{subject}/mri/{hemi}_{TARGET_TYPE}_{m}.tsf"
        for hemi in HEMIS
        for m in STRUCTURAL_METRICS_FLAIR
    ]


rule tcksample_mri_flair:
    input:
        tck=lambda wc: compute_streamlines_outputs(wc.subject)[:2],
        flair_proc=rules.proc_flair.output.flair_proc,
        t1_over_flair=rules.proc_flair.output.t1_over_flair,
    output:
        tcksample_mri_flair_outputs("{subject}"),
    shell:
        MRTRIX_ENV + "cortical_tcksample_mri.sh {wildcards.subject} "
        f"{{config[nDepths]}} {TARGET_TYPE} \"{' '.join(STRUCTURAL_METRICS_FLAIR)}\""


def tcksample_mri_outputs(subject):
    """Every tcksample_mri output for this subject: the T1 metrics always,
    plus the FLAIR metrics too if this subject actually has a flair.nii.gz."""
    outputs = tcksample_mri_t1_outputs(subject)
    if has_flair(subject):
        outputs += tcksample_mri_flair_outputs(subject)
    return outputs
