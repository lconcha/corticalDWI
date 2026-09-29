"""
cortical_browser_config.py — shared configuration for the cortical DWI tools.

Single source of truth for BOTH the interactive browser (cortical_browser.py)
and the normative-dataset builder (cortical_create_normative_data_from_tsf.py),
so the two always search for, build, and display the same metrics on the same
surface template.

Values come from corticalDWI_params.conf — the ONE file pipeline parameters
live in (see that file's own header) — via cortical_config.py's shared
parser, with the same two-tier priority cortical_load_params.sh and the
Snakefile also use:
  1. Repo defaults    — corticalDWI_params.conf at the repo root
  2. Study overrides   — $SUBJECTS_DIR/corticalDWI_params.conf, if the
     SUBJECTS_DIR environment variable is set and the file exists

Keys consumed here:
  target_type      — surface template name -> TEMPLATE
  browser_metrics   — comma-separated metric list -> METRICS

Call print_config_report(subjects_dir) from a CLI's main(), once args are
parsed, to print exactly which of the two files above actually supplied
TEMPLATE/METRICS for THIS run — never leave it to be inferred.
"""
import os
import sys

_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_DIR)
from cortical_config import load_conf   # noqa: E402 (needs the sys.path insert above)

# Fallback values, used only if a key is missing from every conf file found.
_DEFAULT_TEMPLATE = 'ico6_sym'
_DEFAULT_METRICS  = ('dwi/dti/fa,dwi/dti/md,dwi/dti/ad,dwi/dti/rd,dwi/dti/cl,dwi/dti/cp,dwi/dti/cs,'
                      'dwi/csd_fixels_singletissue/afd-par,dwi/csd_fixels_singletissue/afd-perp,'
                      'dwi/dki/mk,dwi/dki/ak,dwi/dki/rk,'
                      'mri/T1w_proc,mri/flair_proc,mri/T1w_proc_grad,mri/T1_over_FLAIR')

_subjects_dir = os.environ.get('SUBJECTS_DIR')
_params, _provenance, _repo_conf, _study_conf = load_conf(_REPO_DIR, _subjects_dir)

# ── Surface template / naming convention ──────────────────────────────────────
# Which surface template's files to search for and display. All TSF and surface
# files are expected to follow the {hemi}_{...}_{TEMPLATE}... naming convention
# (e.g. lh_ico6_sym_fa.tsf, lh_white_ico6_sym.surf.gii).
TEMPLATE = _params.get('target_type', _DEFAULT_TEMPLATE)

# ── Metrics ───────────────────────────────────────────────────────────────────
# Metrics to search for, display in the browser, and include in the normative
# dataset — in the order they should appear. Each metric is written
# <folder>/<name> (e.g. dwi/dti/fa, dwi/dki/fa, dwi/mrds/mrds_fixels/BIC/FA-par,
# mri/T1w_proc) and maps to the file <folder>/{hemi}_{TEMPLATE}_<name>.tsf under
# the subject's directory. <folder> is the FULL path, every directory name from
# the subject directory down, of the directory that holds the .tsf — arbitrarily
# deep, and this is what tells apart metrics that several methods (or, for
# MRDS, different model-selection variants) produce under the same name.
# If a subject is missing a metric, the browser will display a warning and skip it.
METRICS = [m.strip() for m in _params.get('browser_metrics', _DEFAULT_METRICS).split(',') if m.strip()]
_bad = [m for m in METRICS if '/' not in m or m.startswith('/') or m.endswith('/')]
if _bad:
    raise SystemExit(f"browser_metrics must be written <folder>/<name> (e.g. dwi/dti/fa, mri/T1w_proc); offending: {_bad}")


# ── Provenance report ──────────────────────────────────────────────────────────
CONFIG_SOURCES = [
    ('1. repo defaults',   _repo_conf,  os.path.isfile(_repo_conf)),
    ('2. study overrides', _study_conf, bool(_study_conf and os.path.isfile(_study_conf))),
]


def _source_label(key):
    path = _provenance.get(key)
    return f'{path}' if path else '(built-in default — no config file sets this)'


def print_config_report(subjects_dir=None):
    """Print exactly which config file this module resolved TEMPLATE/METRICS
    from. Pass the subjects_dir this run is actually using (a CLI's own
    positional arg, which can differ from the SUBJECTS_DIR env var this
    module resolved against at import time) to get a loud warning if the two
    disagree — in that case the report below reflects the wrong directory's
    config entirely."""
    print('Config sources for target_type / browser_metrics (later overrides earlier):')
    for label, path, exists in CONFIG_SOURCES:
        if path is None:
            print(f'  [ SUBJECTS_DIR not set — skipped ] {label}')
        else:
            mark = 'x' if exists else ' '
            print(f'  [{mark}] {label:18s} {path}')
    print(f'  -> target_type     = {TEMPLATE!r}  from {_source_label("target_type")}')
    print(f'  -> browser_metrics = {len(METRICS)} metric(s)  from {_source_label("browser_metrics")}')
    print(f'     {", ".join(METRICS)}')
    if subjects_dir:
        if _subjects_dir and os.path.realpath(subjects_dir) != os.path.realpath(_subjects_dir):
            print(f'  WARNING: SUBJECTS_DIR env var ({_subjects_dir}) differs from the subjects_dir '
                  f'this run is actually using ({subjects_dir}) — the config above was resolved '
                  f'against SUBJECTS_DIR, NOT the directory being browsed. Export SUBJECTS_DIR to '
                  f'match before running, or the study-level overrides for the actual directory '
                  f'in use are silently skipped.')
        elif not _subjects_dir:
            print(f'  WARNING: SUBJECTS_DIR environment variable is not set, so the study-level '
                  f'corticalDWI_params.conf under {subjects_dir} (#2 above) was never consulted — '
                  f'only repo defaults apply, even though a study directory was given on the '
                  f'command line.')
