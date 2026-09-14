"""NODDI fit (AMICO) and streamline sampling of NODDI metrics."""

NODDI_METRICS = ["ODI", "NDI", "FWF"]


def noddi_outputs(subject):
    return [f"{SUBJECTS_DIR}/{subject}/dwi/noddi/{m}.nii.gz" for m in NODDI_METRICS] + [
        f"{SUBJECTS_DIR}/{subject}/dwi/noddi/config.pickle"
    ]


rule noddi:
    input:
        dwi=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.nii.gz",
        bvec=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.bvec",
        bval=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.bval",
        scheme=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.scheme",
        mask=f"{SUBJECTS_DIR}/{{subject}}/dwi/mask.nii.gz",
    output:
        noddi_outputs("{subject}"),
    threads: config["python_threads"]  # also sizes the SGE slot request, see profiles/
    shell:
        # AMICO's numpy/scipy link OpenBLAS (pthreads build) here, same as dipy_fit_dki
        # in rules/dki.smk — see that rule's comment. MRTRIX_ENV applied blanket
        # (see Snakefile) even though cortical_NODDI.sh doesn't call MRtrix itself.
        # JITTER: reads the big raw DWI volume directly off NFS.
        JITTER + MRTRIX_ENV + "OMP_NUM_THREADS={threads} OPENBLAS_NUM_THREADS={threads} "
        "cortical_NODDI.sh {wildcards.subject}"


def tcksample_noddi_outputs(subject):
    return [
        f"{SUBJECTS_DIR}/{subject}/dwi/noddi/{hemi}_{TARGET_TYPE}_{m}.tsf"
        for hemi in HEMIS
        for m in NODDI_METRICS
    ]


rule tcksample_noddi:
    input:
        tck=lambda wc: warp_tck_to_dwi_outputs(wc.subject),
        maps=rules.noddi.output,
    output:
        tcksample_noddi_outputs("{subject}"),
    shell:
        MRTRIX_ENV + "cortical_tcksample_noddi.sh {wildcards.subject} "
        f"{{config[nDepths]}} {TARGET_TYPE}"
