"""
cortical_config.py — shared, dependency-free parser for corticalDWI_params.conf.

corticalDWI_params.conf is the single source of truth for pipeline parameters
(repo defaults at the repo root, optionally overridden per-study by
$SUBJECTS_DIR/corticalDWI_params.conf). It is read three different ways, all
of which must agree:
  - directly, by bash `source`, in cortical_load_params.sh — used by every
    cortical_*.sh script, with zero dependencies beyond bash itself.
  - via parse_conf() below, by the Snakefile, which coerces the handful of
    keys it needs typed (thread counts, the subjects list) and feeds the rest
    to Snakemake's `config` dict as plain strings, same as everything else
    already interpolated into shell: command lines.
  - via parse_conf() below, by cortical_browser/cortical_browser_config.py,
    for the interactive browser and the normative-dataset builder.

There is deliberately no YAML (or other structured-format) sibling to this
file anymore — Snakemake used to have its own config.yaml specifically
because it needs typed values, but that meant two files, hand-kept in sync,
living side by side in $SUBJECTS_DIR. Whichever of the three readers above
needs a typed value now coerces it itself, from the same plain-text source,
rather than that source existing twice in two formats.
"""
import os
import re


def parse_conf(path):
    """{key: value} (every value a plain string) from one
    corticalDWI_params.conf-style file, or {} if it doesn't exist.

    A trailing backslash joins a line to the next one — same as bash's own
    line-continuation, since this file is also `source`d directly. Matches
    bash only when the continuation line has NO leading whitespace; an
    indented continuation would make bash treat it as a separate word/command
    instead of part of the assignment, so this file must not indent
    continuation lines either.
    """
    if not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8') as f:
        text = f.read()
    text = re.sub(r'\\\n', '', text)
    params = {}
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if not line or '=' not in line:
            continue
        key, _, val = line.partition('=')
        params[key.strip()] = val.strip()
    return params


def load_conf(repo_dir, subjects_dir=None):
    """Two-tier merge — repo defaults (corticalDWI_params.conf at repo_dir)
    overridden key-by-key by study overrides
    (subjects_dir/corticalDWI_params.conf, if subjects_dir is given and the
    file exists) — same priority order as cortical_load_params.sh's own bash
    sourcing. Returns (params, provenance, repo_conf_path, study_conf_path):
    provenance[key] is the path of whichever file's value for that key is
    the one in effect; study_conf_path is None if subjects_dir wasn't given.
    """
    repo_conf = os.path.join(repo_dir, 'corticalDWI_params.conf')
    study_conf = os.path.join(subjects_dir, 'corticalDWI_params.conf') if subjects_dir else None

    params = {}
    provenance = {}
    for path in (repo_conf, study_conf):
        if not path:
            continue
        for key, val in parse_conf(path).items():
            params[key] = val
            provenance[key] = path
    return params, provenance, repo_conf, study_conf
