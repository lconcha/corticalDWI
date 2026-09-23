"""
cortical_browser_config.py — shared configuration for the cortical DWI tools.

Single source of truth for BOTH the interactive browser (cortical_browser.py)
and the normative-dataset builder (cortical_create_normative_data_from_tsf.py),
so the two always search for, build, and display the same metrics on the same
surface template.

Values are read from corticalDWI_params.conf — the same file the shell
pipeline uses — with the same two-tier priority as cortical_load_params.sh:
  1. Repo defaults  — corticalDWI_params.conf at the repo root
  2. Study overrides — $SUBJECTS_DIR/corticalDWI_params.conf, if the
     SUBJECTS_DIR environment variable is set and the file exists

Keys consumed here:
  target_type      — surface template name -> TEMPLATE
  browser_metrics   — comma-separated metric list -> METRICS
"""
import os

_REPO_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_CONF = os.path.join(_REPO_DIR, 'corticalDWI_params.conf')

# Fallback values, used only if a key is missing from every conf file found.
_DEFAULT_TEMPLATE = 'ico6_sym'
_DEFAULT_METRICS  = ('fa,md,ad,rd,cl,cp,cs,afd-par,afd-perp,mk,ak,rk,'
                      'T1w_proc,flair_proc,T1w_proc_grad,T1_over_FLAIR')


def _parse_conf(path):
    params = {}
    if not os.path.isfile(path):
        return params
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if not line or '=' not in line:
                continue
            key, _, val = line.partition('=')
            params[key.strip()] = val.strip()
    return params


_params = _parse_conf(_REPO_CONF)

_subjects_dir = os.environ.get('SUBJECTS_DIR')
if _subjects_dir:
    _params.update(_parse_conf(os.path.join(_subjects_dir, 'corticalDWI_params.conf')))

# Per-dataset overrides in $SUBJECTS_DIR/.corticalDWI/config.yaml (the same file
# the Snakefile merges over the repo defaults) take precedence over the .conf files.
# browser_metrics may be a comma-separated string or a YAML list.
if _subjects_dir:
    _yaml_path = os.path.join(_subjects_dir, '.corticalDWI', 'config.yaml')
    if os.path.isfile(_yaml_path):
        try:
            import yaml
            with open(_yaml_path, encoding='utf-8') as f:
                _yaml = yaml.safe_load(f) or {}
            for _k in ('target_type', 'browser_metrics'):
                if _yaml.get(_k):
                    _v = _yaml[_k]
                    _params[_k] = ','.join(map(str, _v)) if isinstance(_v, (list, tuple)) else str(_v)
        except Exception as e:
            print(f'WARNING: could not read {_yaml_path}: {e}')

# ── Surface template / naming convention ──────────────────────────────────────
# Which surface template's files to search for and display. All TSF and surface
# files are expected to follow the {hemi}_{...}_{TEMPLATE}... naming convention
# (e.g. lh_ico6_sym_fa.tsf, lh_white_ico6_sym.surf.gii).
TEMPLATE = _params.get('target_type', _DEFAULT_TEMPLATE)

# ── Metrics ───────────────────────────────────────────────────────────────────
# Metrics to search for, display in the browser, and include in the normative
# dataset — in the order they should appear. Each metric <m> maps to per-hemi
# TSF files named {hemi}_{TEMPLATE}_<m>.tsf, located recursively under each
# subject's directory (so files nested in sub-folders like
# dwi/csd_fixels_singletissue/ are found too).
# If a subject is missing a metric, the browser will display a warning and skip it.
METRICS = [m.strip() for m in _params.get('browser_metrics', _DEFAULT_METRICS).split(',') if m.strip()]
