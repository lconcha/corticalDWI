"""T1/FLAIR structural processing and streamline sampling of structural metrics.

cortical_tcksample_mri.sh samples from the T1-space streamlines
(mri/{hemi}_{target_type}_laplace-wm-streamlines.tck, cortical_compute_streamlines.sh's
output) rather than the dwi-space warped ones every other tcksample_* script uses —
preserved as-is, not a porting mistake.
"""

STRUCTURAL_METRICS = ["T1w_proc", "flair_proc", "T1w_proc_grad", "T1_over_FLAIR"]


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


def tcksample_mri_outputs(subject):
    return [
        f"{SUBJECTS_DIR}/{subject}/mri/{hemi}_{TARGET_TYPE}_{m}.tsf"
        for hemi in HEMIS
        for m in STRUCTURAL_METRICS
    ]


rule tcksample_mri:
    input:
        tck=lambda wc: compute_streamlines_outputs(wc.subject)[:2],
        t1w_proc=rules.proc_t1.output.t1w_proc,
        t1w_proc_grad=rules.proc_t1.output.t1w_proc_grad,
        flair_proc=rules.proc_flair.output.flair_proc,
        t1_over_flair=rules.proc_flair.output.t1_over_flair,
    output:
        tcksample_mri_outputs("{subject}"),
    shell:
        MRTRIX_ENV + "cortical_tcksample_mri.sh {wildcards.subject} "
        f"{{config[nDepths]}} {TARGET_TYPE}"
