"""DTI fit and streamline sampling of DTI metrics."""

DTI_METRICS = ["fa", "md", "ad", "rd", "v1", "cl", "cp", "cs"]
DTI_SAMPLED_METRICS = ["fa", "md", "ad", "rd", "cl", "cp", "cs"]  # v1 (vector) is not sampled


def dti_outputs(subject):
    return [f"{SUBJECTS_DIR}/{subject}/dwi/dti/{m}.nii.gz" for m in DTI_METRICS]


rule dti:
    input:
        dwi=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.nii.gz",
        mask=f"{SUBJECTS_DIR}/{{subject}}/dwi/mask.nii.gz",
        scheme=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.scheme",
    output:
        dti_outputs("{subject}"),
    shell:
        # JITTER: reads the big raw DWI volume directly off NFS. dwi2tensor/
        # tensor2metric are confirmed not OpenMP-linked, so no OMP_NUM_THREADS
        # needed — but they're MRtrix tools, so MRTRIX_ENV still applies (see
        # its definition in the Snakefile).
        JITTER + MRTRIX_ENV + "cortical_DTI.sh {wildcards.subject}"


def tcksample_dti_outputs(subject):
    return [
        f"{SUBJECTS_DIR}/{subject}/dwi/dti/{hemi}_{TARGET_TYPE}_{m}.tsf"
        for hemi in HEMIS
        for m in DTI_SAMPLED_METRICS
    ]


rule tcksample_dti:
    input:
        tck=lambda wc: warp_tck_to_dwi_outputs(wc.subject),
        maps=rules.dti.output,
    output:
        tcksample_dti_outputs("{subject}"),
    shell:
        MRTRIX_ENV + "cortical_tcksample_dti.sh {wildcards.subject} "
        f"{{config[nDepths]}} {TARGET_TYPE}"
