"""
Laplacian streamline field, ico6_sym surface resampling, T1<->DWI registration,
and the streamlines themselves (T1 space, then warped to DWI space).

target_type is pinned to ico6_sym throughout this port: cortical_resample_surface_ico6_sym.sh
hardcodes 'ico6_sym' in its output filenames regardless of config, and
cortical_compute_streamlines.sh requires target_type-suffixed surfaces as input — the two
are only consistent when target_type == ico6_sym, which is also the repo default.
Wiring up fsLR-32k/fsLR-5k (via cortical_resample_surface.sh) is out of scope here.

resample_fsaverage_sym_to_ico6 is the one group-wise rule in this file (study-level
template surfaces, not per-subject) — see its own docstring for why it's never pulled
into a subject's default target, mirroring build_normative_data in rules/zscore.smk.
"""


rule laplacian:
    input:
        f"{SUBJECTS_DIR}/{{subject}}/mri/aparc+aseg.mgz",
    output:
        f"{SUBJECTS_DIR}/{{subject}}/mri/laplace-wm_vec.nii.gz",
    shell:
        MRTRIX_ENV + "cortical_compute_laplacian.sh {wildcards.subject}"


rule resample_surface_ico6_sym:
    input:
        sphere=f"{SUBJECTS_DIR}/{{subject}}/surf/lh.sphere",
        white=f"{SUBJECTS_DIR}/{{subject}}/surf/lh.white",
        pial=f"{SUBJECTS_DIR}/{{subject}}/surf/lh.pial",
        orig=f"{SUBJECTS_DIR}/{{subject}}/mri/orig.mgz",
    output:
        # Downstream-consumed surfaces only. The script also writes per-metric
        # (sulc/curv/thickness) func.gii files and inflated variants that no
        # tracked step reads — not declared here, still produced on disk.
        lh_white=f"{SUBJECTS_DIR}/{{subject}}/surf/lh_white_ico6_sym.surf.gii",
        rh_white=f"{SUBJECTS_DIR}/{{subject}}/surf/rh_white_ico6_sym.surf.gii",
        lh_pial=f"{SUBJECTS_DIR}/{{subject}}/surf/lh_pial_ico6_sym.surf.gii",
        rh_pial=f"{SUBJECTS_DIR}/{{subject}}/surf/rh_pial_ico6_sym.surf.gii",
        spec=f"{SUBJECTS_DIR}/{{subject}}/surf/ico6_sym.spec",
    shell:
        MRTRIX_ENV + "cortical_resample_surface_ico6_sym.sh {wildcards.subject}"


rule resample_fsaverage_sym_to_ico6:
    # Group-wise, triggered by name only (`cortical_snakerun.py
    # resample_fsaverage_sym_to_ico6`) — like build_normative_data in
    # rules/zscore.smk, this is never an input of any subject's default
    # target, so it never silently reruns just because some subject's own
    # output changed. Builds the shared ico6_sym white/pial TEMPLATE surfaces
    # (mirrored fsaverage_sym, not any one subject's anatomy) that
    # cortical_browser.py's surface-type dropdown lists as "average_white"/
    # "average_pial" (see find_surface_types()) — once per study, not once
    # per subject.
    #
    # Its input is the ico6 sphere template, built as a side effect the
    # first time ANY subject runs resample_surface_ico6_sym above — not
    # declared as that rule's output (deliberately: it's shared/study-level,
    # not per-subject) so Snakemake has no rule it could chain to build it
    # automatically. The wrapped script exits with a clear error if it's
    # still missing, same as cortical_create_normative_data_from_tsf.py does
    # for its own missing inputs.
    input:
        f"{SUBJECTS_DIR}/templates/fsaverage_sym.sphere.ico6.surf.gii",
    output:
        lh_white=f"{SUBJECTS_DIR}/templates/surf/lh_white.ico6_sym.surf.gii",
        rh_white=f"{SUBJECTS_DIR}/templates/surf/rh_white.ico6_sym.surf.gii",
        lh_pial=f"{SUBJECTS_DIR}/templates/surf/lh_pial.ico6_sym.surf.gii",
        rh_pial=f"{SUBJECTS_DIR}/templates/surf/rh_pial.ico6_sym.surf.gii",
        lh_inflated=f"{SUBJECTS_DIR}/templates/surf/lh_inflated.ico6_sym.surf.gii",
        rh_inflated=f"{SUBJECTS_DIR}/templates/surf/rh_inflated.ico6_sym.surf.gii",
        lh_very_inflated=f"{SUBJECTS_DIR}/templates/surf/lh_very-inflated.ico6_sym.surf.gii",
        rh_very_inflated=f"{SUBJECTS_DIR}/templates/surf/rh_very-inflated.ico6_sym.surf.gii",
    shell:
        MRTRIX_ENV + "cortical_resample_fsaverage_sym_to_ico6.sh"


rule register_t1_to_dwi:
    input:
        t1=f"{SUBJECTS_DIR}/{{subject}}/mri/brain.mgz",
        b0=f"{SUBJECTS_DIR}/{{subject}}/dwi/b0.nii.gz",
    output:
        warp=f"{SUBJECTS_DIR}/{{subject}}/dwi/t1native_to_b0_1Warp.nii.gz",
        affine=f"{SUBJECTS_DIR}/{{subject}}/dwi/t1native_to_b0_0GenericAffine.mat",
        inverse_warp=f"{SUBJECTS_DIR}/{{subject}}/dwi/t1native_to_b0_1InverseWarp.nii.gz",
        # cortical_register_t1_to_dwi.sh's own help text claims "t1native_to_b0.nii.gz"
        # (no suffix), but that file is never actually created by the real chain —
        # confirmed 2026-08-25 via a real run: inb_synthreg.sh's true final output
        # (from its trailing antsApplyTransforms call) is t1native_to_b0_Warped.nii.gz.
        # Nothing downstream reads this output either way (checked warp_tck_to_dwi,
        # the only consumer of this rule's outputs — it uses warp/affine/inverse_warp
        # only), so this is purely a completion marker; fixed to match reality.
        registered=f"{SUBJECTS_DIR}/{{subject}}/dwi/t1native_to_b0_Warped.nii.gz",
    # Sizes the SGE slot request so nproc inside the job (which the external
    # inb_synthreg.sh probes to self-configure) never returns something that
    # breaks its arithmetic — see corticalDWI_params.conf's register_threads comment.
    threads: config["register_threads"]
    shell:
        MRTRIX_ENV + "cortical_register_t1_to_dwi.sh {wildcards.subject}"


def compute_streamlines_outputs(subject):
    return [
        f"{SUBJECTS_DIR}/{subject}/mri/{hemi}_{TARGET_TYPE}_laplace-wm-streamlines.tck"
        for hemi in HEMIS
    ] + [
        f"{SUBJECTS_DIR}/{subject}/mri/{hemi}_{TARGET_TYPE}_laplace-wm-streamlines_endsOnly.tck"
        for hemi in HEMIS
    ]


rule compute_streamlines:
    input:
        lh_white=rules.resample_surface_ico6_sym.output.lh_white,
        rh_white=rules.resample_surface_ico6_sym.output.rh_white,
        lh_pial=rules.resample_surface_ico6_sym.output.lh_pial,
        rh_pial=rules.resample_surface_ico6_sym.output.rh_pial,
        laplace_vec=rules.laplacian.output,
    output:
        compute_streamlines_outputs("{subject}"),
    shell:
        MRTRIX_ENV + "cortical_compute_streamlines.sh {wildcards.subject} "
        f"{TARGET_TYPE} {{config[nsteps]}} {{config[step_size]}}"


def warp_tck_to_dwi_outputs(subject):
    return [
        f"{SUBJECTS_DIR}/{subject}/dwi/{hemi}_{TARGET_TYPE}_laplace-wm-streamlines_dwispace.tck"
        for hemi in HEMIS
    ]


rule warp_tck_to_dwi:
    input:
        affine=rules.register_t1_to_dwi.output.affine,
        warp=rules.register_t1_to_dwi.output.warp,
        inverse_warp=rules.register_t1_to_dwi.output.inverse_warp,
        b0=f"{SUBJECTS_DIR}/{{subject}}/dwi/b0.nii.gz",
        tck=lambda wc: compute_streamlines_outputs(wc.subject)[:2],
    output:
        warp_tck_to_dwi_outputs("{subject}"),
    shell:
        MRTRIX_ENV + "cortical_warp_tck_to_dwi.sh {wildcards.subject} "
        f"{TARGET_TYPE} {{config[tck_step_size]}} {{config[max_length]}}"
