"""MRDS multi-tensor fit and fixel-based streamline sampling."""

MRDS_VARIANTS = ["FA", "MD", "COMP_SIZE"]
# cortical_MRDS.sh now fits both model-selection criteria and gives each its
# own fixel subdirectory (commit 26a3657, cherry-picked from main
# 2026-09-02: "each modsel gets its own fixel directory") — same pattern as
# CSD's csd_fixels/csd_fixels_singletissue split in rules/csd.smk.
MRDS_MODSELS = ["FTest", "BIC"]


def mrds_outputs(subject):
    # "mrds_fixels" is a hardcoded literal inside cortical_MRDS.sh, NOT built from
    # config["mrds_fixel_dir"] (same pattern as CSD's csd_fixels_singletissue — see
    # rules/csd.smk). tcksamplefixels_mrds DOES read config["mrds_fixel_dir"]; the two
    # only line up because the config default matches this literal. Preserved as-is.
    outputs = []
    for modsel in MRDS_MODSELS:
        fixel_dir = f"{SUBJECTS_DIR}/{subject}/dwi/mrds/mrds_fixels/{modsel}"
        outputs += [f"{fixel_dir}/index.mif", f"{fixel_dir}/directions.mif"]
        outputs += [f"{fixel_dir}/MRDS_Diff_{modsel}_{v}.mif" for v in MRDS_VARIANTS]
        # One scalar .nii.gz per modsel as a completion marker, matching the
        # pre-existing (not fully exhaustive — only FA, not MD/COMP_SIZE)
        # convention this had for the single FTest modsel before this split.
        outputs.append(f"{SUBJECTS_DIR}/{subject}/dwi/mrds/{subject}_MRDS_Diff_{modsel}_FA.nii.gz")
    return outputs


rule mrds:
    input:
        dwi=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.nii.gz",
        bvec=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.bvec",
        bval=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.bval",
        scheme=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.scheme",
        mask=f"{SUBJECTS_DIR}/{{subject}}/dwi/mask.nii.gz",
    output:
        mrds_outputs("{subject}"),
    threads: config["mrds_threads"]  # also sizes the SGE slot request, see profiles/
    shell:
        # mdtmrds (and the MRDS package's own `dti` response-fit tool, also called
        # inside cortical_MRDS.sh) link libgomp directly and read OMP_NUM_THREADS;
        # without this, both silently run single-threaded if the ambient env has
        # it pinned to 1 (confirmed on this host — see reference_omp_threads_pinned_to_1
        # memory). cortical_MRDS.sh also calls MRtrix's mrstats, hence MRTRIX_ENV
        # too. JITTER: this rule reads the big raw DWI volume directly off NFS.
        JITTER + MRTRIX_ENV + "OMP_NUM_THREADS={threads} cortical_MRDS.sh {wildcards.subject}"


def tcksamplefixels_mrds_outputs(subject):
    # cortical_tcksamplefixels_mrds.sh loops over both modsels itself, reading
    # fixels from .../{mrds_fixel_dir}/{modsel}/ and writing the .tsf files
    # into that same per-modsel subdirectory — see its own comment on why
    # FTest/BIC fixel layouts aren't interchangeable.
    suffixes = ["par-perp-indices", "par", "perp", "perp-av"]
    return [
        f"{SUBJECTS_DIR}/{subject}/dwi/mrds/{config['mrds_fixel_dir']}/{modsel}/{hemi}_{TARGET_TYPE}_{v}-{s}.tsf"
        for modsel in MRDS_MODSELS
        for hemi in HEMIS
        for v in MRDS_VARIANTS
        for s in suffixes
    ]


rule tcksamplefixels_mrds:
    input:
        tck=lambda wc: warp_tck_to_dwi_outputs(wc.subject),
        mrds_fixels=rules.mrds.output,
    output:
        tcksamplefixels_mrds_outputs("{subject}"),
    shell:
        MRTRIX_ENV + "cortical_tcksamplefixels_mrds.sh {wildcards.subject} "
        f"{{config[mrds_fixel_dir]}} {{config[angle]}} {{config[nDepths]}} {TARGET_TYPE}"
