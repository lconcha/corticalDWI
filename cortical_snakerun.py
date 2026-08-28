#!/usr/bin/env python3
"""
cortical_snakerun.py — run a single corticalDWI Snakemake rule for a single
subject, without needing to know or remember its exact target output path.

Unlike a hand-maintained lookup table, this interrogates the Snakefile fresh
on every invocation (via `snakemake -n --forceall`), so the rule/target list
can never drift out of sync with rules/*.smk — it reflects whatever the rules
currently declare, automatically.

Prerequisites (same as any other corticalDWI script/the Snakefile itself):
  module load freesurfer/8.1 mrtrix/3.0.4 workbench_con/2.0.1 ANTs/2.4.4 mrds/1.2.0
  conda activate corticalDWI
  export SUBJECTS_DIR=/path/to/freesurfer/subjects

Usage:
  cortical_snakerun.py                                # list every rule + its target pattern
  cortical_snakerun.py --for-subject sub-X             #   (discover using a specific subject)
  cortical_snakerun.py <rule> <subject> [extra snakemake args...]
  cortical_snakerun.py <rule> --all-subjects [extra snakemake args...]
  cortical_snakerun.py <rule>                          # only for rules with no {subject} in their pattern
  cortical_snakerun.py <rule> <subject> --cluster      # submit via $SUBJECTS_DIR/.corticalDWI/snakemake_profile
  cortical_snakerun.py --subject-outputs sub-X [--under mri]    # every declared output for sub-X
  cortical_snakerun.py --subject-raw-inputs sub-X [--under dwi] # files read but never produced by any rule
  cortical_snakerun.py --delete sub-X [--dry-run]      # reset sub-X: delete every rule output for it
                                                        # (see cortical_delete_everything.sh for the
                                                        # older, hand-maintained-glob equivalent — kept
                                                        # deliberately Snakemake-free)

Examples:
  cortical_snakerun.py dti sub-79291
  cortical_snakerun.py mrds sub-79291 -R              # force rerun even if already done
  cortical_snakerun.py dti --all-subjects             # run for every non-skipped sub-* subject
  cortical_snakerun.py csd_average_response           # global rule, no subject needed
  cortical_snakerun.py mrds sub-79291 --cluster        # submit to Don Clusterio (or whatever
                                                        # profile is currently deployed there)

--cluster uses whatever profile is currently sitting in $SUBJECTS_DIR/.corticalDWI/snakemake_profile/ 
To target a different cluster, copy a different profile config.yaml there;
this script never hardcodes which cluster that is.
"""
import glob
import os
import re
import shutil
import subprocess
import sys

GREEN_CHECK = "\033[32m✓\033[0m"
RED_CROSS = "\033[31m✗\033[0m"


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
    cmd = [
        "snakemake", "-n", "--forceall",
        # --cores matters here, not just for a real run: without it, Snakemake
        # scales every job's threads down to 1 for its own dry-run accounting
        # (same gotcha as real local runs — see reference_snakemake_cores_vs_jobs_flag
        # memory), so a rule's true declared threads: would silently read back as 1.
        "--cores", "64",
        "-s", os.path.join(cortical_dwi_dir, "Snakefile"),
        "--directory", cortical_dwi_dir,
        "--config", f'subjects=["{subject}"]',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    text = result.stdout + result.stderr

    def generalize(path):
        return path.replace(subject, "{subject}") if subject in path else path

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


def print_targets(cortical_dwi_dir, subjects_dir, for_subject):
    subject = for_subject or find_a_subject(subjects_dir)
    if not subject:
        sys.exit(f"No sub-* directories found in {subjects_dir} to discover rules against.")
    print(f"(discovering rule targets using subject '{subject}' as an example)\n")
    rules, text = discover(cortical_dwi_dir, subject)
    if not rules:
        sys.exit(
            "Could not discover any rules — the dry-run against subject "
            f"'{subject}' didn't resolve cleanly. Try --for-subject with a "
            f"subject that has all its raw prerequisites in place. Raw output:\n\n{text}"
        )
    name_w = max(len(r) for r in rules) + 2
    for name in sorted(rules):
        info = rules[name]
        threads = info.get("threads", 1)
        print(f"  {name:<{name_w}} threads={threads:<3} {info['pattern']}")
    print(
        "\nUsage: cortical_snakerun.py <rule> <subject> [extra snakemake args]\n"
        "       cortical_snakerun.py <rule>              (only for rules with no {subject} above)\n"
        "       cortical_snakerun.py <rule> --all-subjects   (run for every non-skipped sub-*)\n"
        "\n"
        "- By default this runs locally, sized to just the one job's threads.\n"
        "- To run on the cluster instead, add --cluster:\n"
        "  cortical_snakerun.py <rule> <subject> --cluster\n"
        "  --cluster submits via whatever profile is currently deployed at\n"
        "          $SUBJECTS_DIR/.corticalDWI/snakemake_profile/\n"
        "- To point at a different cluster, copy a different profile config.yaml there.\n"
        "- To run locally with more than one job's worth of cores yourself (e.g.\n"
        "  for --all-subjects), pass your own --cores N.\n"
        "- To use a hand-picked profile instead of the deployed one, pass --profile <dir>\n"
        "\n"
        "Introspection / cleanup (read the rules, don't run anything):\n"
        "  cortical_snakerun.py --subject-outputs sub-X [--under mri]\n"
        "          every file some rule declares as output for sub-X\n"
        "  cortical_snakerun.py --subject-raw-inputs sub-X [--under dwi]\n"
        "          files some rule reads but no rule ever produces (i.e. raw data)\n"
        "  cortical_snakerun.py --delete sub-X [--dry-run]\n"
        "          reset sub-X: delete every rule output for it (mri/ by exact\n"
        "          declared output, dwi/ by everything-except-raw-inputs, surf/\n"
        "          also sweeps undeclared .gii/.spec byproducts). --dry-run/-n\n"
        "          prints what would be removed without deleting anything.\n"
    )


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

    if not argv or argv[0] in ("-h", "--help"):
        print_targets(cortical_dwi_dir, subjects_dir, for_subject)
        return

    rule = argv[0]
    rest = argv[1:]

    subject = None
    extra_args = rest
    if rest and not rest[0].startswith("-"):
        subject = rest[0]
        extra_args = rest[1:]

    if subject and all_subjects_flag:
        sys.exit("Give either a specific subject or --all-subjects, not both.")

    discovery_subject = subject or for_subject or find_a_subject(subjects_dir)
    if not discovery_subject:
        sys.exit(f"No sub-* directories found in {subjects_dir} to discover rule '{rule}' against.")

    rules, text = discover(cortical_dwi_dir, discovery_subject)
    if rule not in rules:
        available = ", ".join(sorted(rules)) if rules else "(none discovered)"
        sys.exit(f"Unknown rule '{rule}'. Available rules: {available}")

    pattern = rules[rule]["pattern"]
    threads = rules[rule].get("threads", 1)
    needs_subject = "{subject}" in pattern

    if needs_subject and not subject and not all_subjects_flag:
        sys.exit(
            f"Rule '{rule}' needs a subject: cortical_snakerun.py {rule} <subject> "
            f"(or --all-subjects to run it for every subject)"
        )
    if not needs_subject and (subject or all_subjects_flag):
        print(f"(note: rule '{rule}' doesn't take a subject — ignoring {'--all-subjects' if all_subjects_flag else repr(subject)})")

    if needs_subject and all_subjects_flag:
        all_subjects = find_all_subjects(subjects_dir)
        if not all_subjects:
            sys.exit(f"No sub-* directories found in {subjects_dir}.")
        targets = [pattern.format(subject=s) for s in all_subjects]
        print(f"(--all-subjects: {len(all_subjects)} subjects — {', '.join(all_subjects)})")
    elif needs_subject:
        targets = [pattern.format(subject=subject)]
    else:
        targets = [pattern]

    cmd = [
        "snakemake",
        "-s", os.path.join(cortical_dwi_dir, "Snakefile"),
        "--directory", cortical_dwi_dir,
    ]

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

    print("+ " + " ".join(cmd))
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()
