"""
CSD response functions, group-average response (frozen snapshot), FOD, and
AFD fixel sampling.

IMPORTANT CAVEAT on the frozen snapshot: $SUBJECTS_DIR/.corticalDWI/csd_average_response_subjects.txt
controls WHEN Snakemake considers csd_average_response stale (i.e. when Snakemake
decides to re-run it) — but cortical_CSD_average_response.sh itself takes no
subject-list argument; when it *does* run, it globs every response_wm.txt
already present anywhere under $SUBJECTS_DIR (via `fd`), not just the subjects
named in the snapshot file. So the snapshot file reliably prevents *unwanted*
reruns (no edit to the file -> Snakemake sees no stale input -> rule not
re-run), but if you ever do trigger a rerun for any reason, the script will
average over whatever subjects currently exist on disk, not just the
snapshot list. This is a limitation of the wrapped script, not the Snakemake
layer — flagged here rather than silently patched, per the port's "wrap
as-is" scope.
"""

RESPONSE_TISSUES = ["wm", "gm", "csf"]

CSD_SNAPSHOT_FILE = f"{STUDY_DIR}/csd_average_response_subjects.txt"
if os.path.exists(CSD_SNAPSHOT_FILE):
    CSD_SNAPSHOT_SUBJECTS = [
        line.strip()
        for line in open(CSD_SNAPSHOT_FILE)
        if line.strip() and not line.strip().startswith("#")
    ]
else:
    # No snapshot yet for this dataset — csd_average_response simply has no
    # input to depend on until one is created (see that file's own header,
    # written once you're ready: cp config.yaml's neighbor template or just
    # `ls "$SUBJECTS_DIR" | grep '^sub-' > "$SUBJECTS_DIR/.corticalDWI/csd_average_response_subjects.txt"`).
    CSD_SNAPSHOT_SUBJECTS = []


def csd_individual_response_outputs(subject):
    return [f"{SUBJECTS_DIR}/{subject}/dwi/csd/response_{t}.txt" for t in RESPONSE_TISSUES]


rule csd_individual_response:
    input:
        dwi=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.nii.gz",
        scheme=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.scheme",
        mask=f"{SUBJECTS_DIR}/{{subject}}/dwi/mask.nii.gz",
    output:
        csd_individual_response_outputs("{subject}"),
    shell:
        JITTER + MRTRIX_ENV + "cortical_CSD_individual_response.sh {wildcards.subject}"


rule csd_average_response:
    input:
        ([CSD_SNAPSHOT_FILE] if os.path.exists(CSD_SNAPSHOT_FILE) else [])
        + [
            f
            for subject in CSD_SNAPSHOT_SUBJECTS
            for f in csd_individual_response_outputs(subject)
        ],
    output:
        [f"{SUBJECTS_DIR}/average_response/average_response_{t}.txt" for t in RESPONSE_TISSUES],
    shell:
        MRTRIX_ENV + "cortical_CSD_average_response.sh"


def csd_compute_fod_outputs(subject):
    fixel_files = ["afd_fixels.mif", "peak_fixels.mif", "disp_fixels.mif"]
    return (
        [f"{SUBJECTS_DIR}/{subject}/dwi/csd/fod_{t}.mif" for t in RESPONSE_TISSUES]
        + [f"{SUBJECTS_DIR}/{subject}/dwi/csd/csd_fixels/{f}" for f in fixel_files]
        + [f"{SUBJECTS_DIR}/{subject}/dwi/csd/fod_wm_singletissue.mif"]
        + [f"{SUBJECTS_DIR}/{subject}/dwi/csd/csd_fixels_singletissue/{f}" for f in fixel_files]
    )


rule csd_compute_fod:
    # Note: csd_fixels / csd_fixels_singletissue are hardcoded literals inside
    # cortical_CSD_compute_fod.sh, NOT built from config["csd_fixel_dir"] — this
    # only lines up with tcksamplefixels_afd (which DOES read csd_fixel_dir from
    # config) because the config default happens to match the hardcoded literal.
    # Preserved as-is; see plan notes.
    input:
        dwi=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.nii.gz",
        scheme=f"{SUBJECTS_DIR}/{{subject}}/dwi/dwi.scheme",
        mask=f"{SUBJECTS_DIR}/{{subject}}/dwi/mask.nii.gz",
        group_average=rules.csd_average_response.output,
    output:
        csd_compute_fod_outputs("{subject}"),
    shell:
        JITTER + MRTRIX_ENV + "cortical_CSD_compute_fod.sh {wildcards.subject}"


def tcksamplefixels_afd_outputs(subject):
    fixel_dir = f"{SUBJECTS_DIR}/{subject}/dwi/csd/{config['csd_fixel_dir']}"
    suffixes = ["afd-par-perp-indices", "afd-par", "afd-perp", "afd-perp-av"]
    return [f"{fixel_dir}/{hemi}_{TARGET_TYPE}_{s}.tsf" for hemi in HEMIS for s in suffixes]


rule tcksamplefixels_afd:
    input:
        tck=lambda wc: warp_tck_to_dwi_outputs(wc.subject),
        afd_fixels=lambda wc: f"{SUBJECTS_DIR}/{wc.subject}/dwi/csd/{config['csd_fixel_dir']}/afd_fixels.mif",
    output:
        tcksamplefixels_afd_outputs("{subject}"),
    shell:
        MRTRIX_ENV + "cortical_tcksamplefixels_afd.sh {wildcards.subject} "
        f"{{config[csd_fixel_dir]}} {{config[angle]}} {{config[nDepths]}} {TARGET_TYPE}"
