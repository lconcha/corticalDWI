"""
cortical_browser_config.py — shared configuration for the cortical DWI tools.

Single source of truth for BOTH the interactive browser (cortical_browser.py)
and the normative-dataset builder (cortical_create_normative_data_from_tsf.py),
so the two always search for, build, and display the same metrics on the same
surface template. Edit the two settings below to change what the tools use.
"""

# ── Surface template / naming convention ──────────────────────────────────────
# Which surface template's files to search for and display. All TSF and surface
# files are expected to follow the {hemi}_{...}_{TEMPLATE}... naming convention
# (e.g. lh_ico6_sym_fa.tsf, lh_white_ico6_sym.surf.gii). Change this one string
# to switch the whole toolchain between templates.
#   'ico6_sym'   — symmetric icosahedral (ico6) template
#   'fsLR-32k'   — HCP fs_LR 32k template
TEMPLATE = 'ico6_sym'

# ── Metrics ───────────────────────────────────────────────────────────────────
# Metrics to search for, display in the browser, and include in the normative
# dataset — in the order they should appear. Each metric <m> maps to per-hemi
# TSF files named {hemi}_{TEMPLATE}_<m>.tsf, located recursively under each
# subject's directory (so files nested in sub-folders like
# dwi/csd_fixels_singletissue/ are found too).
METRICS = ['fa', 'md', 'ad', 'rd', 'afd-par', 'afd-perp']
