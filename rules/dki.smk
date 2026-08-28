"""DKI fit (dipy) and streamline sampling of DKI metrics."""

# mk/ak/rk are explicit dipy_fit_dki output flags in cortical_DKI.sh; fa/ga/md/ad/rd
# are dipy_fit_dki's implicit default outputs into the same --out_dir, consumed by
# cortical_tcksample_dki.sh's "fa ga md ad rd mk ak rk" metric list.
DKI_METRICS = ["fa", "ga", "md", "ad", "rd", "mk", "ak", "rk"]


def dki_outputs(subject):
    return [f"{SUBJECTS_DIR}/{subject}/dwi/dki/{m}.nii.gz" for m in DKI_METRICS]


rule dki:
    input:
        dwi=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.nii.gz",
        bvec=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.bvec",
        bval=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.bval",
        mask=f"{SUBJECTS_DIR}/{{subject}}/dwi/mask.nii.gz",
    output:
        dki_outputs("{subject}"),
    threads: config["python_threads"]  # also sizes the SGE slot request, see profiles/
    shell:
        # dipy_fit_dki's numpy/scipy link OpenBLAS (pthreads build) here, which
        # reads OPENBLAS_NUM_THREADS; OMP_NUM_THREADS set too as OpenBLAS's fallback.
        # cortical_DKI.sh doesn't itself call any MRtrix tool, but MRTRIX_ENV is
        # applied blanket across every rule regardless — harmless if unused.
        # JITTER: this rule reads the big raw DWI volume directly off NFS.
        JITTER + MRTRIX_ENV + "OMP_NUM_THREADS={threads} OPENBLAS_NUM_THREADS={threads} "
        "cortical_DKI.sh {wildcards.subject}"


def tcksample_dki_outputs(subject):
    return [
        f"{SUBJECTS_DIR}/{subject}/dwi/dki/{hemi}_{TARGET_TYPE}_{m}.tsf"
        for hemi in HEMIS
        for m in DKI_METRICS
    ]


rule tcksample_dki:
    input:
        tck=lambda wc: warp_tck_to_dwi_outputs(wc.subject),
        maps=rules.dki.output,
    output:
        tcksample_dki_outputs("{subject}"),
    shell:
        MRTRIX_ENV + "cortical_tcksample_dki.sh {wildcards.subject} "
        f"{{config[nDepths]}} {TARGET_TYPE}"
