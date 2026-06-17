# Changelog

All notable changes to corticalDWI are documented in this file.

History prior to this file is available via `git log` and the tags
`blaschka` and `vizWorking_beforeOrthoSlices`.

## [0.1.0] - 2026-06-17

### Added
- Centralized pipeline parameter loading: `cortical_load_params.sh` sources
  repo-level defaults (`corticalDWI_params.conf`) and then study-level
  overrides (`$SUBJECTS_DIR/corticalDWI_params.conf`), with CLI arguments
  always taking final priority.
- Easy way to check status of pipeline with `cortical_status.sh`.
- Introducing the fantastic Cortical Browser GUI in Matlab.

### Changed
- Most positional arguments across the pipeline scripts
  (`cortical_compute_streamlines.sh`, `cortical_warp_tck_to_dwi.sh`,
  `cortical_tcksample_dti.sh`, `cortical_tcksamplefixels_afd.sh`,
  `cortical_separate_streamlines_by_aparc.sh`) are now optional, falling back
  to `corticalDWI_params.conf` defaults instead of requiring a fixed argument
  count.
- Most scripts now skip re-running and exit early when their output file
  already exists, instead of overwriting it.



## [0.0.9] - 2026-06-12

First working release with `ico6_sym` and `fsLR-32k` working side by side.
