"""
cortical_browser_config.py — shared configuration for the cortical DWI tools.

Single source of truth for BOTH the interactive browser (cortical_browser.py)
and the normative-dataset builder (cortical_create_normative_data_from_tsf.py),
so the two always search for, build, and display the same metrics on the same
surface template.

Values are read from corticalDWI_params.conf — the same file the shell
pipeline uses — with the same two-tier priority as cortical_load_params.sh,
plus a third, higher-priority tier shared with Snakemake's own config:
  1. Repo defaults    — corticalDWI_params.conf at the repo root
  2. Study overrides   — $SUBJECTS_DIR/corticalDWI_params.conf, if the
     SUBJECTS_DIR environment variable is set and the file exists
  3. Study yaml        — $SUBJECTS_DIR/.corticalDWI/config.yaml (the same file
     the Snakefile merges over ITS repo defaults), if it exists and sets
     target_type/browser_metrics

That's 3 files actually read here — but there is a 4th place configuration
for this pipeline lives: the repo's own config.yaml (used only by Snakemake).
This module does NOT read it; see print_config_report() below, which says so
explicitly rather than leaving it ambiguous.

Keys consumed here:
  target_type      — surface template name -> TEMPLATE
  browser_metrics   — comma-separated metric list -> METRICS

Call print_config_report(subjects_dir) from a CLI's main(), once args are
parsed, to print exactly which of the above actually supplied TEMPLATE/METRICS
for THIS run — never leave it to be inferred from which files happen to exist.
"""
import os
import re

_REPO_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_CONF = os.path.join(_REPO_DIR, 'corticalDWI_params.conf')
# Snakemake's own repo-default config — NOT read by this module (see module
# docstring / print_config_report()). Kept here only so the report below can
# name it and say so, instead of a user having to know that on their own.
_REPO_YAML = os.path.join(_REPO_DIR, 'config.yaml')

# Fallback values, used only if a key is missing from every conf file found.
_DEFAULT_TEMPLATE = 'ico6_sym'
_DEFAULT_METRICS  = ('dwi/dti/fa,dwi/dti/md,dwi/dti/ad,dwi/dti/rd,dwi/dti/cl,dwi/dti/cp,dwi/dti/cs,'
                      'dwi/csd_fixels_singletissue/afd-par,dwi/csd_fixels_singletissue/afd-perp,'
                      'dwi/dki/mk,dwi/dki/ak,dwi/dki/rk,'
                      'mri/T1w_proc,mri/flair_proc,mri/T1w_proc_grad,mri/T1_over_FLAIR')


def _parse_conf(path):
    params = {}
    if not os.path.isfile(path):
        return params
    with open(path, encoding='utf-8') as f:
        text = f.read()
    # A trailing backslash joins a line to the next one — same as bash's own
    # line-continuation, which is how this file is also read (cortical_load_params.sh
    # sources it directly). Matches bash only when the continuation line has NO
    # leading whitespace; an indented continuation would make bash treat it as a
    # separate word/command instead of part of the assignment, so this file must
    # not indent continuation lines either.
    text = re.sub(r'\\\n', '', text)
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if not line or '=' not in line:
            continue
        key, _, val = line.partition('=')
        params[key.strip()] = val.strip()
    return params


_subjects_dir = os.environ.get('SUBJECTS_DIR')
_study_conf = os.path.join(_subjects_dir, 'corticalDWI_params.conf') if _subjects_dir else None
_study_yaml = os.path.join(_subjects_dir, '.corticalDWI', 'config.yaml') if _subjects_dir else None

_params = {}
# key -> path of the file whose value for that key is the one actually in
# effect (the last file, in priority order, that set it); absent from this
# dict (checked via .get(key)) means no file set it and the built-in
# _DEFAULT_* above was used instead.
_provenance = {}


def _merge_conf(path):
    for key, val in _parse_conf(path).items():
        _params[key] = val
        _provenance[key] = path


_merge_conf(_REPO_CONF)
if _study_conf:
    _merge_conf(_study_conf)

# Per-dataset overrides in $SUBJECTS_DIR/.corticalDWI/config.yaml (the same file
# the Snakefile merges over the repo defaults) take precedence over the .conf files.
# browser_metrics may be a comma-separated string or a YAML list.
if _study_yaml and os.path.isfile(_study_yaml):
    try:
        import yaml
        with open(_study_yaml, encoding='utf-8') as f:
            _yaml = yaml.safe_load(f) or {}
        for _k in ('target_type', 'browser_metrics'):
            if _yaml.get(_k):
                _v = _yaml[_k]
                _params[_k] = ','.join(map(str, _v)) if isinstance(_v, (list, tuple)) else str(_v)
                _provenance[_k] = _study_yaml
    except Exception as e:
        print(f'WARNING: could not read {_study_yaml}: {e}')

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
# The 3 files actually consulted (in priority order — a later one, if present,
# overrides the earlier ones key-by-key), whether each was found, and whether
# SUBJECTS_DIR was even set (a missing SUBJECTS_DIR silently skips #2 and #3
# entirely, which is easy to mistake for "no overrides configured").
CONFIG_SOURCES = [
    ('1. repo defaults',   _REPO_CONF,  os.path.isfile(_REPO_CONF)),
    ('2. study overrides', _study_conf, bool(_study_conf and os.path.isfile(_study_conf))),
    ('3. study yaml',      _study_yaml, bool(_study_yaml and os.path.isfile(_study_yaml))),
]


def _source_label(key):
    path = _provenance.get(key)
    return f'{path}' if path else '(built-in default — no config file sets this)'


def print_config_report(subjects_dir=None):
    """Print exactly which config file(s) this module resolved TEMPLATE/METRICS
    from, so which of the several places configuration can live actually applied
    is never left to be inferred. Pass the subjects_dir this run is actually
    using (a CLI's own positional arg, which can differ from the SUBJECTS_DIR
    env var this module resolved against at import time) to get a loud warning
    if the two disagree — in that case the report below reflects the wrong
    directory's config entirely."""
    print('Config sources for target_type / browser_metrics (later overrides earlier):')
    for label, path, exists in CONFIG_SOURCES:
        if path is None:
            print(f'  [ SUBJECTS_DIR not set — skipped ] {label}')
        else:
            mark = 'x' if exists else ' '
            print(f'  [{mark}] {label:18s} {path}')
    print(f'  (repo config.yaml at {_REPO_YAML} is Snakemake-only and is NOT read by the browser/builder)')
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
            print(f'  WARNING: SUBJECTS_DIR environment variable is not set, so study-level config '
                  f'files under {subjects_dir} (#2, #3 above) were never consulted — only repo '
                  f'defaults apply, even though a study directory was given on the command line.')
