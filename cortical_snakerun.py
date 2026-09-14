#!/usr/bin/env python3
"""
\033[1mcortical_snakerun.py\033[0m

Run or reset the corticalDWI pipeline through Snakemake.

Every rule's shape (pattern, threads, inputs, outputs) is discovered live on each invocation,
via `snakemake -n --forceall`, so it can never drift out of sync with rules/*.smk 


\033[1mUsage:\033[0m
  cortical_snakerun.py        # list every rule + its target pattern
  cortical_snakerun.py <rule> <subject> [extra snakemake args...]
  cortical_snakerun.py <rule> --all-subjects
  cortical_snakerun.py <rule> # only for rules with no {subject} in their pattern
  
\033[1mOptions:\033[0m
  --all-subjects    Run all subjects within $SUBJECTS_DIR
  --dry-run/-n      Show what would run, run nothing
  --rules <list>    Run just this comma-separated list of rules
  --skip <list>     Skip these comma-separated rules
  --all-rules       Run all rules in the pipeline
  --cluster         Submit to cluster instead of running locally

\033[1mNotes on running a rule:\033[0m
  - \033[1mBy default this runs locally\033[0m, sized to just the one job's threads.
  - \033[1mTo run on the cluster instead, add --cluster\033[0m . It submits via whatever
    profile is currently deployed at $SUBJECTS_DIR/.corticalDWI/snakemake_profile/
    (copy a different profile config.yaml there to target a different cluster).
  - To run locally with more than one job's worth of cores (e.g. for
    --all-subjects), pass your own --cores N.
  - To use a hand-picked profile instead of the deployed one, pass --profile <dir>.
  - --dry-run/-n and --quiet/-q (above) work with any run-a-rule invocation,
    including --rules/--skip/--all-rules, --all-subjects, and --cluster.

\033[1mIntrospection:\033[0m
  --status [sub-X sub-Y ...]
          cortical_status.sh-style table: one row per subject, one numbered
          column per rule (a footnote below the table maps numbers back to
          rule names), check/cross/! (partial). Defaults to every non-skipped
          sub-* subject if none are given. Rules with no {subject} in their
          outputs (e.g. csd_average_response) get their own "Group-wise
          rules" section below the table instead.
  --subject-status sub-X
          one line per subject-scoped rule, check/cross + n/m outputs
          present for sub-X
  --subject-outputs sub-X [--under mri]
          every file some rule declares as output for sub-X
  --subject-raw-inputs sub-X [--under dwi]
          files some rule reads but no rule ever produces (i.e. raw data)

\033[1mCleanup:\033[0m
  --delete sub-X [--dry-run]
          reset sub-X: delete every rule output for it (mri/ by exact
          declared output, dwi/ by everything-except-raw-inputs, surf/ also
          sweeps undeclared .gii/.spec byproducts) — see
          cortical_delete_everything.sh for the older, hand-maintained-glob
          equivalent, kept deliberately Snakemake-free. --dry-run/-n prints
          what would be removed without deleting anything.
  --delete-rule <rule> <subject|--all-subjects> [--dry-run]
          delete just one rule's declared outputs, exact files only — never
          a directory sweep, so it's safe even when the output dir is shared
          with another rule (e.g. mrds_fixels/{modsel}/ holds both mrds's
          and tcksamplefixels_mrds's outputs). --dry-run/-n previews without
          deleting.

\033[1mExamples:\033[0m
  cortical_snakerun.py dti sub-79291
  cortical_snakerun.py mrds sub-79291 -R              # force rerun even if already done
  cortical_snakerun.py dti --all-subjects             # run for every non-skipped sub-* subject
  cortical_snakerun.py csd_average_response           # global rule, no subject needed
  cortical_snakerun.py mrds sub-79291 --cluster        # submit to Don Clusterio (or whatever
                                                        # profile is currently deployed there)
  cortical_snakerun.py dti --all-subjects --dry-run    # preview what would run for every subject

————————————————————————————
\033[1mTO RUN ON A CLUSTER:\033[0m
  --cluster uses whatever profile is currently sitting in $SUBJECTS_DIR/.corticalDWI/snakemake_profile/
          To target a different cluster, copy a different profile config.yaml in that location.
————————————————————————————

LU15 (0N(H4 (and Claude)
INB-UNAM
Sep 2026
lconcha@unam.mx

"""
import glob
import os
import re
import shutil
import subprocess
import sys

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD_YELLOW = "\033[1;33m"
GRAY = "\033[90m"
NC = "\033[0m"
GREEN_CHECK = f"{GREEN}✓{NC}"
RED_CROSS = f"{RED}✗{NC}"
YELLOW_BANG = f"{YELLOW}!{NC}"

# Boilerplate --quiet still can't touch: snakemake's own --quiet flag (see
# the "rules"/"progress" levels used below) only controls per-job rule
# blocks — these lines print regardless, at every level short of "all" (which
# also nukes the job-stats summary we actually want to keep, so it's not a
# usable substitute). Filtered out line-by-line only under --quiet, never
# otherwise, so nothing here can hide a real error.
QUIET_NOISE_EXACT = {"Building DAG of jobs..."}
QUIET_NOISE_PATTERNS = [
    re.compile(r"^Config file .* is extended by additional config specified via the command line\.$"),
    re.compile(r"RequestsDependencyWarning"),  # unrelated missing-optional-dep warning from `requests`
    re.compile(r"pkg_resources is deprecated"),  # unrelated deprecation warning from `stopit`
    re.compile(r"^\s*warnings\.warn\("),  # the source-line stopit/requests print under their warning
    re.compile(r"^\s*import pkg_resources$"),
]


def is_quiet_noise(line):
    stripped = line.rstrip("\n")
    if stripped in QUIET_NOISE_EXACT:
        return True
    return any(p.search(stripped) for p in QUIET_NOISE_PATTERNS)


def marked(path):
    """path prefixed with a green check if it exists on disk, red cross if not."""
    return f"{GREEN_CHECK if os.path.exists(path) else RED_CROSS} {path}"


def find_cortical_dwi_dir():
    env = os.environ.get("CORTICAL_DWI_DIR")
    if env:
        return env.rstrip("/")
    return os.path.dirname(os.path.realpath(__file__))


def find_all_subjects(subjects_dir):
    return sorted(
        os.path.basename(d)
        for d in glob.glob(os.path.join(subjects_dir, "sub-*"))
        if os.path.isdir(d) and not os.path.exists(os.path.join(d, "skip"))
    )


def find_a_subject(subjects_dir):
    subjects = find_all_subjects(subjects_dir)
    return subjects[0] if subjects else None


def discover(cortical_dwi_dir, subject):
    """Run `snakemake -n --forceall` scoped to one subject; parse rule name ->
    {pattern, threads} from the dry-run's own "rule X: ... output: ... threads: ..."
    blocks. Returns (rules_dict, raw_output_text)."""
    # --directory is $SUBJECTS_DIR/.corticalDWI, not the repo: snakemake
    # always creates its own .snakemake/ state (locks, metadata, logs)
    # relative to --directory, and putting that under the repo (the old
    # behavior) meant every run left snakemake-internal state inside the
    # corticalDWI git checkout. Safe to relocate: the Snakefile/rules/*.smk
    # only ever use absolute SUBJECTS_DIR/CORTICAL_DWI_DIR-prefixed paths
    # (never anything relative to --directory), and every wrapped
    # cortical_*.sh script — plus its own bare `source cortical_load_params.sh`
    # — is found via $PATH (see path_corticalDWI() in ~/.bashrc), not CWD, so
    # nothing here depends on --directory being the repo. Pre-create the
    # target dir ourselves rather than relying on the Snakefile's own
    # os.makedirs(STUDY_DIR) for it (rules/*.smk line ~84) — that only runs
    # once Snakemake has already parsed the Snakefile, which happens *after*
    # it chdirs into --directory, so on a brand-new dataset --directory
    # itself wouldn't exist yet without this.
    subjects_dir = os.environ["SUBJECTS_DIR"].rstrip("/")
    study_dir = os.path.join(subjects_dir, ".corticalDWI")
    os.makedirs(study_dir, exist_ok=True)
    cmd = [
        "snakemake", "-n", "--forceall",
        # --cores matters here, not just for a real run: without it, Snakemake
        # scales every job's threads down to 1 for its own dry-run accounting
        # (same gotcha as real local runs — see reference_snakemake_cores_vs_jobs_flag
        # memory), so a rule's true declared threads: would silently read back as 1.
        "--cores", "64",
        # This call only ever introspects rule shape (never executes anything
        # for real), but it's still a genuine DAG build, so Snakemake applies
        # its full safety checks regardless — including refusing to proceed
        # at all if it sees a file some job has started writing but not yet
        # confirmed complete (IncompleteFilesException). That's the right
        # call before actually *running* something (don't want to silently
        # treat a partial/corrupted file as done), but every caller of
        # discover() here is read-only — --status, --subject-outputs, plain
        # rule listing, etc. — so it shouldn't be blocked just because some
        # OTHER job (possibly for a different subject entirely) happens to
        # be mid-flight on the cluster right now (confirmed 2026-09-02: a
        # live --all-subjects --cluster recompute made even --status fail
        # outright). --ignore-incomplete is safe here specifically because
        # nothing gets executed off the back of this call.
        "--ignore-incomplete",
        "-s", os.path.join(cortical_dwi_dir, "Snakefile"),
        "--directory", study_dir,
        "--config", f'subjects=["{subject}"]',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    text = result.stdout + result.stderr

    # Surface Snakefile-level data-hygiene warnings (e.g. a bad line in
    # csd_average_response_subjects.txt — see rules/csd.smk) here, once,
    # regardless of whether discovery itself succeeds or fails — every
    # caller of discover() gets this for free rather than needing to
    # remember to check `text` themselves, and it doesn't just get silently
    # dropped on the success path the way a plain "check text on failure
    # only" approach would.
    for line in text.splitlines():
        if line.startswith("WARNING:"):
            print(f"{BOLD_YELLOW}{line}{NC}", file=sys.stderr)
        elif line.startswith("NOTE:"):
            print(line, file=sys.stderr)

    def generalize(path):
        # Matched on token *shape* (any sub-<label> token), not on the
        # literal `subject` string passed to this call — some rules' printed
        # job blocks belong to a *different* subject than the one discovery
        # was scoped to (csd_individual_response is the confirmed case: with
        # --forceall, its only printed instance is whichever subject is in
        # the frozen CSD snapshot — see rules/csd.smk — not the discovery
        # subject). A literal-string replace would leave that path hardcoded
        # to the wrong subject instead of generalizing it, which silently
        # broke targeting for any subject not in the snapshot (found
        # 2026-08-28: `cortical_snakerun.py csd_individual_response sub-X`
        # for an unsnapshotted sub-X actually targeted the snapshot subject).
        #
        # Matches the token wherever it appears, not just as a whole /-bounded
        # path component: mrds_outputs()'s .nii.gz marker embeds the subject
        # ID as a filename *prefix* (sub-79113_MRDS_Diff_BIC_FA.nii.gz), which
        # the old /sub-[^/]+/ pattern (slash-bounded on both sides) never
        # matched, silently leaving one discovery subject's literal ID baked
        # into that pattern — invisible for --subject-outputs/--subject-status
        # (which always discover using the very subject they display), but
        # wrong for every other subject when --status reuses one discovery
        # subject's rules dict across a whole table (confirmed 2026-09-02:
        # sub-79291/sub-79864 showed spurious partial mrds/tcksamplefixels_mrds
        # status whenever a *different* subject came first in the table).
        # [A-Za-z0-9]+ stops at the next "_"/"."/non-alnum, matching BIDS-style
        # labels (alphanumeric only, no embedded "_"/"." within one entity).
        return re.sub(r"sub-[A-Za-z0-9]+", "{subject}", path)

    rules = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^rule (\S+):$", line)
        if m:
            current = m.group(1)
            continue
        if current is None:
            continue
        m = re.match(r"^ {4}input: (.+)$", line)
        if m:
            rules.setdefault(current, {})["inputs"] = [
                generalize(p) for p in m.group(1).split(", ")
            ]
            continue
        m = re.match(r"^ {4}output: (.+)$", line)
        if m:
            outputs = [generalize(p) for p in m.group(1).split(", ")]
            rules.setdefault(current, {})["outputs"] = outputs
            rules[current]["pattern"] = outputs[0]
            continue
        m = re.match(r"^ {4}threads: (\d+)$", line)
        if m:
            rules.setdefault(current, {})["threads"] = int(m.group(1))
            continue
        if line.strip() == "":
            current = None

    rules.pop("all", None)
    return rules, text


def subject_scoped(patterns):
    return {p for p in patterns if "{subject}" in p}


def subject_outputs(rules, subject, under=None):
    """Every file some rule declares as output for this subject (across all
    rules) — the precise, self-updating replacement for a hand-maintained
    glob list. `under` restricts to paths under {subject}/{under}/."""
    paths = {
        p.format(subject=subject)
        for info in rules.values()
        for p in subject_scoped(info.get("outputs", []))
    }
    if under:
        paths = {p for p in paths if f"/{subject}/{under}/" in p}
    return sorted(paths)


def subject_rule_status(rules, subject):
    """One (rule_name, n_existing, n_total) tuple per subject-scoped rule —
    the per-rule analogue of subject_outputs' per-file listing. A rule with
    no {subject} in its outputs (a global rule, e.g. csd_average_response)
    is skipped: it isn't this subject's to report on."""
    results = []
    for name, info in rules.items():
        outs = [p.format(subject=subject) for p in subject_scoped(info.get("outputs", []))]
        if not outs:
            continue
        n_existing = sum(1 for p in outs if os.path.exists(p))
        results.append((name, n_existing, len(outs)))
    return sorted(results)


def group_rule_status(rules):
    """One (rule_name, n_existing, n_total) tuple per *group-wise* rule —
    one with declared outputs but no {subject} in any of them, e.g.
    csd_average_response (a group-level CSD response averaged across
    subjects, see rules/csd.smk). Not tied to any one subject, so it doesn't
    belong in --status's per-subject grid — reported in its own section
    instead. Currently just csd_average_response, but written generically
    so any future group-wise rule shows up here automatically."""
    results = []
    for name, info in rules.items():
        outs = info.get("outputs", [])
        if not outs or subject_scoped(outs):
            continue
        n_existing = sum(1 for p in outs if os.path.exists(p))
        results.append((name, n_existing, len(outs)))
    return sorted(results)


def compute_rule_deps(rules):
    """name -> set of rule names whose declared output this rule's input
    directly consumes, matched by exact string equality on the already-
    {subject}-generalized paths in `rules` (no real subject needed)."""
    output_owner = {}
    for name, info in rules.items():
        for out in info.get("outputs", []):
            output_owner[out] = name

    deps = {name: set() for name in rules}
    for name, info in rules.items():
        for inp in info.get("inputs", []):
            producer = output_owner.get(inp)
            if producer and producer != name:
                deps[name].add(producer)
    return deps


def compute_rule_dependents(rules):
    """name -> set of rule names whose input directly consumes this rule's
    output — the reverse of compute_rule_deps, i.e. "who breaks if this rule
    doesn't run"."""
    deps = compute_rule_deps(rules)
    dependents = {name: set() for name in rules}
    for name, needed in deps.items():
        for dep in needed:
            dependents[dep].add(name)
    return dependents


def transitive_rule_dependents(dependents, name):
    """Every rule (recursively) that needs `name`'s output, directly or via
    some other rule in between."""
    seen = set()
    stack = list(dependents.get(name, ()))
    while stack:
        dep = stack.pop()
        if dep in seen:
            continue
        seen.add(dep)
        stack.extend(dependents.get(dep, ()))
    return seen


def rule_dependency_order(rules):
    """Topologically sort rule names so each rule comes after every other
    rule whose output it consumes as input — matched by exact string equality
    on the already-{subject}-generalized paths in `rules`, so this doesn't
    need a real subject to reason about the DAG shape. Independent branches
    (no dependency either way) keep their original discovery order, so the
    result is deterministic without an arbitrary alphabetical tiebreak."""
    deps = compute_rule_deps(rules)

    order = []
    done = set()
    in_progress = set()

    def visit(name):
        if name in done or name in in_progress:
            return
        in_progress.add(name)
        for dep in deps.get(name, ()):
            visit(dep)
        in_progress.discard(name)
        done.add(name)
        order.append(name)

    for name in rules:
        visit(name)
    return order


def print_status_table(rules, subjects_dir, subjects):
    """cortical_status.sh-style table: one row per subject, one column per
    subject-scoped rule. Reuses a single `rules` dict (one snakemake dry-run,
    already paid for by the caller) against every subject's real files —
    subject_rule_status itself is pure os.path.exists, so this scales to any
    number of subjects without extra snakemake subprocess calls.

    Columns are labeled 1, 2, 3... rather than by rule name — rule names are
    long enough that spelling them out as column headers overflows the row
    (a subject can have 15-20 rules) — with a numbered footnote below the
    table mapping each number back to its rule name. Column order follows
    the pipeline's own DAG (upstream rules first), not alphabetical, so
    reading left-to-right roughly matches the order steps actually run in."""
    subject_scoped_names = {name for name, info in rules.items() if subject_scoped(info.get("outputs", []))}
    names = [n for n in rule_dependency_order(rules) if n in subject_scoped_names]
    if not names:
        sys.exit("No subject-scoped rules discovered.")

    headers = [str(i + 1) for i in range(len(names))]
    subj_w = max([len(s) for s in subjects] + [len("SUBJECT")]) + 2
    col_w = max([len(h) for h in headers] + [1]) + 2

    print("SUBJECT".ljust(subj_w) + "".join(h.ljust(col_w) for h in headers))
    print("-" * (subj_w + col_w * len(names)))

    n_full = 0
    for subject in subjects:
        if os.path.exists(os.path.join(subjects_dir, subject, "skip")):
            continue
        if not os.path.isdir(os.path.join(subjects_dir, subject)):
            print(f"{YELLOW}{subject.ljust(subj_w)}(directory not found){NC}")
            continue
        status = {name: (e, t) for name, e, t in subject_rule_status(rules, subject)}
        row = subject.ljust(subj_w)
        for name in names:
            n_existing, n_total = status.get(name, (0, 0))
            if n_existing == n_total:
                symbol, color = "✓", GREEN
                n_full += 1
            elif n_existing == 0:
                symbol, color = "✗", RED
            else:
                symbol, color = "!", YELLOW
            row += f"{color}{symbol}{NC}" + " " * (col_w - 1)
        print(row)

    print("-" * (subj_w + col_w * len(names)))
    for h, name in zip(headers, names):
        print(f"  {h}. {name}")

    group_status = group_rule_status(rules)
    if group_status:
        print("-" * (subj_w + col_w * len(names)))
        print("Group-wise rules (not tied to any one subject):")
        name_w = max(len(name) for name, _, _ in group_status) + 2
        for name, n_existing, n_total in group_status:
            if n_existing == n_total:
                symbol, color = "✓", GREEN
            elif n_existing == 0:
                symbol, color = "✗", RED
            else:
                symbol, color = "!", YELLOW
            print(f"  {color}{symbol}{NC} {name:<{name_w}} {n_existing}/{n_total}")

    print("-" * (subj_w + col_w * len(names)))
    n_total_cells = len(subjects) * len(names)
    print(f"Total: {GREEN}{n_full}{NC} / {n_total_cells} rules fully complete "
          f"across {len(subjects)} subject(s)  ({GREEN}✓{NC}=done  {RED}✗{NC}=missing  {YELLOW}!{NC}=partial)")


def subject_raw_inputs(rules, subject, under=None):
    """Files some rule reads for this subject but no rule ever produces —
    i.e. externally-provided raw data, not pipeline output. `under` restricts
    to paths under {subject}/{under}/."""
    all_outputs = {p for info in rules.values() for p in subject_scoped(info.get("outputs", []))}
    all_inputs = {p for info in rules.values() for p in subject_scoped(info.get("inputs", []))}
    paths = {p.format(subject=subject) for p in (all_inputs - all_outputs)}
    if under:
        paths = {p for p in paths if f"/{subject}/{under}/" in p}
    return sorted(paths)


def delete_subject(cortical_dwi_dir, subjects_dir, subject, dry_run):
    """Reset one subject: delete every file rules/*.smk declares as this
    subject's output, read live from the Snakefile so the list can never
    drift out of sync with the rules (the failure mode a hand-maintained
    glob list hit twice in one session: silently missing new output files).

    mri/ is FreeSurfer's own subject directory, shared with plenty of content
    this pipeline never touches — so it's only ever safe to delete exactly
    the declared outputs there, never a directory-wide sweep.

    dwi/ is created and owned entirely by this pipeline, so it's safe (and
    more thorough) to instead delete everything except the true raw inputs —
    files some rule reads but no rule ever produces — which also catches any
    undeclared/intermediate file a wrapped script drops there.

    surf/ additionally gets a targeted glob for known undeclared byproducts
    (cortical_resample_surface_ico6_sym.sh's per-metric func.gii and inflated
    surf.gii variants — see rules/streamline_prep.smk's comment on that rule)
    that pure rule-output deletion would miss. Every corticalDWI-written file
    in surf/ is GIfTI (.gii) or the ico6_sym.spec manifest — native FreeSurfer
    surf/ content never uses either extension — so this glob is a safe,
    complete boundary on its own.
    """
    rules, text = discover(cortical_dwi_dir, subject)
    if not rules:
        sys.exit(f"Dry-run against '{subject}' didn't resolve cleanly:\n\n{text}")

    def do_rm(path, is_dir=False):
        verb = "would rm -rf " if is_dir else "would rm "
        if not dry_run:
            verb = "rm -rf " if is_dir else "rm "
        print(verb + path)
        if dry_run:
            return
        if is_dir:
            shutil.rmtree(path)
        else:
            os.remove(path)

    targets = set(subject_outputs(rules, subject))
    surf_dir = os.path.join(subjects_dir, subject, "surf")
    targets |= set(glob.glob(os.path.join(surf_dir, "*.gii")))
    targets |= set(glob.glob(os.path.join(surf_dir, "*.spec")))
    for f in sorted(targets):
        if os.path.exists(f):
            do_rm(f)

    dwi_dir = os.path.join(subjects_dir, subject, "dwi")
    keep = {os.path.basename(p) for p in subject_raw_inputs(rules, subject, under="dwi")}
    if os.path.isdir(dwi_dir):
        for name in sorted(os.listdir(dwi_dir)):
            if name in keep:
                continue
            path = os.path.join(dwi_dir, name)
            do_rm(path, is_dir=os.path.isdir(path) and not os.path.islink(path))


def delete_rule_outputs(rules, rule_name, subject, dry_run):
    """Delete exactly one rule's declared outputs for one subject (or, for a
    rule with no {subject} in its outputs, its one global output set —
    `subject` is None in that case).

    Deliberately exact-declared-outputs only, unlike delete_subject()'s
    blanket dwi/ sweep: several rules share an output *directory* with
    another rule (mrds_fixels/{modsel}/ holds both mrds's .mif files and
    tcksamplefixels_mrds's .tsf files; csd_fixels/ similarly holds
    csd_compute_fod's and tcksamplefixels_afd's outputs) — a directory-wide
    delete here would take out a sibling rule's outputs too, which
    "delete just this rule's outputs" should never do."""
    info = rules[rule_name]
    if subject is not None:
        outs = [p.format(subject=subject) for p in subject_scoped(info.get("outputs", []))]
    else:
        outs = info.get("outputs", [])

    label = subject or "(global)"
    if not outs:
        print(f"(rule '{rule_name}' has no outputs to delete for {label})")
        return

    for f in sorted(outs):
        if os.path.exists(f):
            verb = "would rm " if dry_run else "rm "
            print(verb + f)
            if not dry_run:
                os.remove(f)


def print_targets(cortical_dwi_dir, subjects_dir, for_subject):
    subject = for_subject or find_a_subject(subjects_dir)
    if not subject:
        sys.exit(f"No sub-* directories found in {subjects_dir} to discover rules against.")
    rules, text = discover(cortical_dwi_dir, subject)
    if not rules:
        sys.exit(
            "Could not discover any rules — the dry-run against subject "
            f"'{subject}' didn't resolve cleanly. Try --for-subject with a "
            f"subject that has all its raw prerequisites in place. Raw output:\n\n{text}"
        )
    # Everything else (usage, examples, introspection/cleanup flags) lives in
    # this module's own docstring at the top of the file — printed here
    # rather than duplicated into a second hand-maintained string, which is
    # exactly what let the two drift out of sync (and, at one point, broke
    # outright) in the first place.
    print(__doc__)

    # The live-discovered rule list prints last, dimmed gray — it's
    # reference material (what rule names/threads/patterns currently exist),
    # not the primary thing someone reading -h is looking for.
    name_w = max(len(r) for r in rules) + 2
    print(f"{GRAY}(Rules in the pipeline (discovered using subject '{subject}'){NC}\n")
    for name in sorted(rules):
        info = rules[name]
        threads = info.get("threads", 1)
        print(f"{GRAY}  {name:<{name_w}} threads={threads:<3} {info['pattern']}{NC}")


def main():
    subjects_dir = os.environ.get("SUBJECTS_DIR")
    if not subjects_dir:
        sys.exit("SUBJECTS_DIR is not set. Export it first, same as for any other corticalDWI script.")
    subjects_dir = subjects_dir.rstrip("/")
    cortical_dwi_dir = find_cortical_dwi_dir()

    argv = sys.argv[1:]

    if "--delete" in argv:
        i = argv.index("--delete")
        subject = argv[i + 1]
        del argv[i : i + 2]
        dry_run = False
        for flag in ("--dry-run", "-n"):
            if flag in argv:
                dry_run = True
                argv.remove(flag)
        delete_subject(cortical_dwi_dir, subjects_dir, subject, dry_run)
        return

    if "--delete-rule" in argv:
        i = argv.index("--delete-rule")
        rule_name = argv[i + 1]
        del argv[i : i + 2]

        dry_run = False
        for flag in ("--dry-run", "-n"):
            if flag in argv:
                dry_run = True
                argv.remove(flag)

        all_subjects_flag = "--all-subjects" in argv
        if all_subjects_flag:
            argv.remove("--all-subjects")

        subject = argv[0] if argv else None
        if subject and all_subjects_flag:
            sys.exit("Give either a specific subject or --all-subjects, not both.")

        discovery_subject = subject or find_a_subject(subjects_dir)
        if not discovery_subject:
            sys.exit(f"No sub-* directories found in {subjects_dir} to discover rule '{rule_name}' against.")
        rules, text = discover(cortical_dwi_dir, discovery_subject)
        if not rules:
            sys.exit(f"Dry-run against '{discovery_subject}' didn't resolve cleanly:\n\n{text}")
        if rule_name not in rules:
            sys.exit(f"Unknown rule '{rule_name}'. Available rules: {', '.join(sorted(rules))}")

        needs_subject = bool(subject_scoped(rules[rule_name].get("outputs", [])))
        if not needs_subject:
            if subject or all_subjects_flag:
                print(f"(note: rule '{rule_name}' doesn't take a subject — "
                      f"ignoring {'--all-subjects' if all_subjects_flag else repr(subject)})")
            delete_rule_outputs(rules, rule_name, None, dry_run)
            return

        if not subject and not all_subjects_flag:
            sys.exit(
                f"Rule '{rule_name}' needs a subject: cortical_snakerun.py --delete-rule {rule_name} <subject> "
                f"(or --all-subjects to clear it for every subject)"
            )

        if all_subjects_flag:
            targets = find_all_subjects(subjects_dir)
            if not targets:
                sys.exit(f"No sub-* directories found in {subjects_dir}.")
        else:
            targets = [subject]

        for s in targets:
            delete_rule_outputs(rules, rule_name, s, dry_run)
        return

    if "--status" in argv:
        argv.remove("--status")
        given_subjects = [a for a in argv if not a.startswith("-")]
        subjects = given_subjects or find_all_subjects(subjects_dir)
        if not subjects:
            sys.exit(f"No sub-* directories found in {subjects_dir}.")
        rules, text = discover(cortical_dwi_dir, subjects[0])
        if not rules:
            sys.exit(f"Dry-run against '{subjects[0]}' didn't resolve cleanly:\n\n{text}")
        print_status_table(rules, subjects_dir, subjects)
        return

    if "--subject-status" in argv:
        i = argv.index("--subject-status")
        subject = argv[i + 1]
        del argv[i : i + 2]
        rules, text = discover(cortical_dwi_dir, subject)
        if not rules:
            sys.exit(f"Dry-run against '{subject}' didn't resolve cleanly:\n\n{text}")
        results = subject_rule_status(rules, subject)
        if not results:
            sys.exit(f"No subject-scoped rules discovered for '{subject}'.")
        name_w = max(len(name) for name, _, _ in results) + 2
        for name, n_existing, n_total in results:
            mark = GREEN_CHECK if n_existing == n_total else RED_CROSS
            print(f"{mark} {name:<{name_w}} {n_existing}/{n_total}")
        return

    for mode in ("--subject-outputs", "--subject-raw-inputs"):
        if mode in argv:
            i = argv.index(mode)
            subject = argv[i + 1]
            del argv[i : i + 2]
            under = None
            if "--under" in argv:
                j = argv.index("--under")
                under = argv[j + 1]
                del argv[j : j + 2]
            rules, text = discover(cortical_dwi_dir, subject)
            if not rules:
                sys.exit(f"Dry-run against '{subject}' didn't resolve cleanly:\n\n{text}")
            fn = subject_outputs if mode == "--subject-outputs" else subject_raw_inputs
            for p in fn(rules, subject, under=under):
                print(marked(p))
            return

    for_subject = None
    if "--for-subject" in argv:
        i = argv.index("--for-subject")
        for_subject = argv[i + 1]
        del argv[i : i + 2]

    all_subjects_flag = "--all-subjects" in argv
    if all_subjects_flag:
        argv.remove("--all-subjects")

    cluster_flag = "--cluster" in argv
    if cluster_flag:
        argv.remove("--cluster")

    quiet_flag = False
    for flag in ("--quiet", "-q"):
        if flag in argv:
            quiet_flag = True
            argv.remove(flag)

    dry_run_flag = False
    for flag in ("--dry-run", "-n"):
        if flag in argv:
            dry_run_flag = True
            argv.remove(flag)

    all_rules_flag = "--all-rules" in argv
    if all_rules_flag:
        argv.remove("--all-rules")

    rules_arg = None
    if "--rules" in argv:
        i = argv.index("--rules")
        rules_arg = argv[i + 1]
        del argv[i : i + 2]

    skip_arg = None
    if "--skip" in argv:
        i = argv.index("--skip")
        skip_arg = argv[i + 1]
        del argv[i : i + 2]

    if sum(x is not None for x in (all_rules_flag or None, rules_arg, skip_arg)) > 1:
        sys.exit("Give at most one of --all-rules, --rules, or --skip.")

    if "-h" in argv or "--help" in argv:
        print_targets(cortical_dwi_dir, subjects_dir, for_subject)
        return

    mode = "all" if all_rules_flag else "list" if rules_arg is not None else "skip" if skip_arg is not None else "single"

    if mode == "single":
        if not argv:
            print_targets(cortical_dwi_dir, subjects_dir, for_subject)
            return
        rule = argv[0]
        rest = argv[1:]
    else:
        rest = argv

    subject = None
    extra_args = rest
    if rest and not rest[0].startswith("-"):
        subject = rest[0]
        extra_args = rest[1:]

    if subject and all_subjects_flag:
        sys.exit("Give either a specific subject or --all-subjects, not both.")

    discovery_subject = subject or for_subject or find_a_subject(subjects_dir)
    if not discovery_subject:
        sys.exit(f"No sub-* directories found in {subjects_dir} to discover rules against.")

    rules, text = discover(cortical_dwi_dir, discovery_subject)
    if not rules:
        sys.exit(f"Dry-run against '{discovery_subject}' didn't resolve cleanly:\n\n{text}")

    if mode == "single":
        if rule not in rules:
            sys.exit(f"Unknown rule '{rule}'. Available rules: {', '.join(sorted(rules))}")
        selected = [rule]
    elif mode == "list":
        names = [n.strip() for n in rules_arg.split(",") if n.strip()]
        unknown = [n for n in names if n not in rules]
        if unknown:
            sys.exit(f"Unknown rule(s): {', '.join(unknown)}. Available: {', '.join(sorted(rules))}")
        selected = names
    elif mode == "skip":
        skip_names = [n.strip() for n in skip_arg.split(",") if n.strip()]
        unknown = [n for n in skip_names if n not in rules]
        if unknown:
            sys.exit(f"Unknown rule(s) to skip: {', '.join(unknown)}. Available: {', '.join(sorted(rules))}")
        # Skipping a rule only drops its own target from the request — if
        # another still-selected rule needs its output as an input (e.g.
        # tcksamplefixels_mrds needs mrds), Snakemake would pull it back in
        # as a dependency regardless. So walk the DAG forward from each
        # skipped rule via compute_rule_dependents and skip everything
        # downstream of it too, rather than silently failing to skip it.
        dependents = compute_rule_dependents(rules)
        full_skip = set(skip_names)
        for name in skip_names:
            full_skip |= transitive_rule_dependents(dependents, name)
        auto_skipped = sorted(full_skip - set(skip_names))
        selected = [n for n in sorted(rules) if n not in full_skip]
        if not selected:
            sys.exit("Skipping every discovered rule (directly or via its downstream dependents) leaves nothing to run.")
    else:
        selected = None  # --all-rules: no explicit target list, let snakemake run its own default (rule all)

    if mode == "all":
        targets = []
        threads = max((info.get("threads", 1) for info in rules.values()), default=1)
        if not quiet_flag:
            if subject:
                print(f"(--all-rules: running the full pipeline for subject '{subject}')")
            else:
                print("(--all-rules: running the full pipeline for every non-skipped subject — same as plain snakemake)")
    else:
        all_subjects_list = None
        if all_subjects_flag:
            all_subjects_list = find_all_subjects(subjects_dir)
            if not all_subjects_list:
                sys.exit(f"No sub-* directories found in {subjects_dir}.")

        targets = []
        missing_subject = []
        no_subject_needed = []
        for name in selected:
            pattern = rules[name]["pattern"]
            needs_subject = "{subject}" in pattern
            if needs_subject and all_subjects_flag:
                targets += [pattern.format(subject=s) for s in all_subjects_list]
            elif needs_subject and subject:
                targets.append(pattern.format(subject=subject))
            elif needs_subject:
                missing_subject.append(name)
            else:
                targets.append(pattern)
                if subject or all_subjects_flag:
                    no_subject_needed.append(name)

        if missing_subject:
            sys.exit(
                "These selected rules need a subject: " + ", ".join(missing_subject) +
                " — pass a subject or --all-subjects."
            )
        if no_subject_needed and not quiet_flag:
            print(f"(note: rule(s) {', '.join(no_subject_needed)} don't take a subject — "
                  f"ignoring {'--all-subjects' if all_subjects_flag else repr(subject)} for them)")
        if not quiet_flag:
            if mode == "list":
                print(f"(--rules: {len(selected)} rule(s) — {', '.join(selected)})")
            elif mode == "skip":
                print(f"(--skip {', '.join(skip_names)}: running {len(selected)} of {len(rules)} discovered rules — {', '.join(selected)})")
                if auto_skipped:
                    print(f"(note: also skipping {', '.join(auto_skipped)} — downstream of a skipped rule, "
                          "would otherwise be pulled back in as a dependency)")
            if all_subjects_flag:
                print(f"(--all-subjects: {len(all_subjects_list)} subjects — {', '.join(all_subjects_list)})")

        threads = max((rules[n].get("threads", 1) for n in selected), default=1)

    cmd = [
        "snakemake",
        "-s", os.path.join(cortical_dwi_dir, "Snakefile"),
        # $SUBJECTS_DIR/.corticalDWI, not the repo — see discover()'s comment
        # for why. Already exists by now: discover() (called above to look up
        # this rule) creates it as a side effect.
        "--directory", os.path.join(subjects_dir, ".corticalDWI"),
    ]
    if mode == "all" and subject:
        cmd += ["--config", f'subjects=["{subject}"]']
    if dry_run_flag:
        cmd.append("-n")
    if quiet_flag:
        # snakemake's own --quiet takes an optional {progress,rules,all}
        # list (nargs='*') — greedily placing it right before the bare
        # target-path list at the end of cmd would make argparse swallow the
        # first target as an "invalid choice" for --quiet instead of a
        # target, so this must sit here, immediately followed by another
        # --flag (--profile/--cluster or --cores below), never directly by
        # extra_args/targets. "rules" hides the per-job rule/input/output/
        # reason blocks but keeps the job-count summary table and any real
        # errors — exactly "how many jobs would run", not every file detail.
        cmd += ["--quiet", "rules"]

    profile_given = any(a in ("--profile",) for a in extra_args)
    if cluster_flag:
        if profile_given:
            sys.exit("Give either --cluster or your own --profile, not both.")
        profile_dir = os.path.join(subjects_dir, ".corticalDWI", "snakemake_profile")
        if not os.path.isdir(profile_dir):
            sys.exit(
                f"--cluster was given but no profile is deployed at {profile_dir} — "
                "copy one there first (see profiles/ in the repo for a template)."
            )
        cmd += ["--profile", profile_dir]
        profile_given = True

    if not profile_given and not any(a in ("--cores", "-j", "--jobs") for a in extra_args):
        # Conservative default even with --all-subjects: just enough cores for
        # one job's worth of threads, so subjects run one at a time unless you
        # explicitly pass a bigger --cores yourself. Deliberately not guessing
        # a "reasonable" multi-subject budget on your behalf — see the NFS-jitter
        # /job-concurrency discussion in the SGE work for why that's not a call
        # to make silently. Not applicable at all under --cluster/--profile:
        # there, per-job resources come from the profile's own cluster-sync
        # (-pe smp {threads}), not from a local --cores budget.
        cmd += ["--cores", str(threads)]
    cmd += extra_args + targets

    if quiet_flag:
        # Can't os.execvp() here: process replacement hands the terminal
        # straight to snakemake with no way to filter its output afterward.
        # --quiet rules/progress can't suppress "Building DAG of jobs...",
        # the "Config file ... extended by ..." notices, or unrelated
        # dependency warnings (confirmed empirically — no combination short
        # of "all" removes them, and "all" also removes the job-stats table
        # this flag exists to keep) — see QUIET_NOISE_* above. So this
        # streams the real subprocess's combined output line-by-line and
        # drops only those known-boilerplate lines; anything else (job
        # stats, real errors, the wrapped scripts' own stdout) passes
        # through untouched, and the real exit code still propagates.
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        try:
            for line in proc.stdout:
                if not is_quiet_noise(line):
                    print(line, end="")
        except KeyboardInterrupt:
            pass
        finally:
            proc.wait()
        sys.exit(proc.returncode)

    print("+ " + " ".join(cmd))
    # os.execvp() replaces this process image directly (execve syscall) — it
    # never goes through Python's normal exit/flush machinery, so any stdout
    # buffered so far (every print() above, all the "(--rules/--skip/...)"
    # notes) would otherwise be silently lost whenever stdout isn't a TTY
    # (piped, redirected, or captured — e.g. inside an SGE job's -o log).
    sys.stdout.flush()
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()
