from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from daimonion import kanon
from daimonion.config import CONFIG_NAME, ConfigError, ProjectConfig, find_config, load_config
from daimonion.context import derive_context, describe_context, find_answers_file, load_answers
from daimonion.detect import UNDETECTABLE, default_agents_md, detect, render_config
from daimonion.engine import Linter
from daimonion.i18n import DEFAULT_UI, LANGS, UI, resolve_emoji, resolve_lang
from daimonion.models import Finding
from daimonion.report import build_json_report, build_rules_json_report, build_sarif_report, dumps
from daimonion.suppress import BASELINE_NAME, BaselineError, load_baseline, split_baselined, write_baseline

#: Prepared per-project rule file written by ``prepare --write``.
PREPARED_RULES_NAME = ".daimonion-rules.yml"
#: Previous name of the prepared rule file; still read when the new name is absent.
LEGACY_PREPARED_RULES_NAME = ".law-lint-rules.yml"

#: Output formats for finding-producing subcommands.
FORMAT_CHOICES = ("human", "json", "sarif")
#: ``list-rules`` describes rules, not locations, so SARIF does not apply there.
RULE_FORMAT_CHOICES = ("human", "json")


def _suppression_note(finding: Finding, ui: UI) -> str:
    """Why an inline directive on this finding's line did not silence it."""
    if finding.suppression is None:
        return ""
    status = finding.suppression.status()
    if status == "expired":
        return f" [{ui.t('findings.ignore_expired', until=finding.suppression.until)}]"
    if status == "invalid":
        return f" [{ui.t('findings.ignore_invalid')}]"
    return ""


def _footer(suppressed: list[Finding], baselined: list[Finding], ui: UI) -> list[str]:
    lines: list[str] = []
    if suppressed:
        lines.append(ui.line("muted", "footer.suppressed", count=len(suppressed)))
    if baselined:
        lines.append(ui.line("baseline", "footer.baselined", count=len(baselined)))
    return lines


def format_findings(
    findings: list[Finding],
    *,
    verbose: bool = False,
    suppressed: list[Finding] | None = None,
    baselined: list[Finding] | None = None,
    ui: UI = DEFAULT_UI,
) -> str:
    """Format findings for terminal output, in ``ui``'s language and icon style."""
    footer = _footer(suppressed or [], baselined or [], ui)
    if not findings:
        return "\n".join([ui.line("clean", "findings.none"), *footer])

    # Group by rule id
    by_rule: dict[str, list[Finding]] = {}
    for f in findings:
        by_rule.setdefault(f.rule.id, []).append(f)

    lines: list[str] = [ui.line("warn", "findings.header", findings=len(findings), areas=len(by_rule)) + "\n"]

    hit, line = ui.t("findings.hit"), ui.t("findings.line")
    for rule_id, rule_findings in by_rule.items():
        rule = rule_findings[0].rule
        badge = f"[{rule.enforcement}] " if rule.enforcement else ""
        lines.append(f"{ui.icon('rule')}{badge}{ui.rule_title(rule)} ({rule_id})")
        lines.append(f"   {ui.line('summary', 'findings.summary', summary=ui.rule_summary(rule))}")
        lines.append(f"   {ui.line('where', 'findings.where')}")
        for rf in rule_findings[:5]:
            note = _suppression_note(rf, ui)
            lines.append(f"      - {rf.file_path}:{rf.line_number} ({hit}: '{rf.matched_text}'){note}")
            if verbose:
                lines.append(f"        {line}: {rf.context_line}")
        if len(rule_findings) > 5:
            lines.append(f"      {ui.t('findings.more', count=len(rule_findings) - 5)}")
        lines.append("")

    lines.extend(footer)
    return "\n".join(lines).strip()


def prepare(args: argparse.Namespace, ui: UI = DEFAULT_UI) -> int:
    """Derive the applicable compliance set from .copier-answers.yml."""
    answers_path = Path(args.answers) if args.answers else find_answers_file(args.repo)
    if answers_path is None:
        print(ui.line("warn", "prepare.no_answers", repo=args.repo), file=sys.stderr)
        return 2

    context = derive_context(load_answers(answers_path))
    base = Linter.from_yaml(args.rules) if args.rules else Linter()
    scoped = base.for_context(context)
    skipped = [r for r in base.rules if r not in scoped.rules]

    print(ui.line("plan", "prepare.header", path=answers_path))
    for line in describe_context(context):
        print(f"   {line}")
    print()
    print(ui.line("ok", "prepare.applicable", count=len(scoped.rules), total=len(base.rules)))
    for r in scoped.rules:
        print(f"   [{r.enforcement}] {r.id}: {ui.rule_title(r)}")
        print(f"        {ui.icon('summary')}{ui.rule_summary(r)}")
    if skipped:
        print()
        print(ui.line("skip", "prepare.skipped", count=len(skipped), ids=", ".join(r.id for r in skipped)))

    if args.write:
        payload = {"rules": [r.to_dict() for r in scoped.rules]}
        out = answers_path.parent / PREPARED_RULES_NAME
        out.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print("\n" + ui.line("wrote", "prepare.wrote", path=out))
        print("   " + ui.t("prepare.commit", name=PREPARED_RULES_NAME))
    else:
        print("\n" + ui.line("info", "prepare.hint", name=PREPARED_RULES_NAME))
    return 0


def init(args: argparse.Namespace, ui: UI = DEFAULT_UI) -> int:
    """Suggest a .daimonion.yml from the repository's manifests and agent files."""
    repo = Path(args.repo)
    signals = detect(repo)
    text = render_config(signals, agents_md=default_agents_md(repo))
    target = repo / CONFIG_NAME

    print(ui.line("scan", "init.header", path=repo.resolve()))
    if signals:
        for signal in signals:
            print(f"   {signal.condition}: {signal.source} ({signal.detail})")
    else:
        print("   " + ui.t("init.none"))
    print("   " + ui.t("init.ask", conditions=", ".join(UNDETECTABLE)))
    print()

    if not args.write:
        print(text, end="")
        print("\n" + ui.line("info", "init.hint", name=CONFIG_NAME))
        return 0
    if target.exists() and not args.force:
        print(ui.line("warn", "init.exists", path=target), file=sys.stderr)
        return 2
    target.write_text(text, encoding="utf-8")
    print(ui.line("wrote", "init.wrote", path=target))
    print("   " + ui.t("init.next"))
    return 0


def agents_md(args: argparse.Namespace, ui: UI = DEFAULT_UI) -> int:
    """Render the rules block for .daimonion.yml; print, write, or check it."""
    config_path = Path(args.config) if args.config else find_config(args.repo)
    if config_path is None:
        print(ui.line("warn", "agents.no_config", name=CONFIG_NAME, repo=args.repo), file=sys.stderr)
        return 2
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"{ui.icon('warn')}{exc}", file=sys.stderr)
        return 2

    block = kanon.render_block(config.when)
    target = config.agents_md_path
    current = target.read_text(encoding="utf-8") if target.is_file() else ""
    try:
        updated = kanon.splice_block(current, block)
    except ValueError as exc:
        print(f"{ui.icon('warn')}{target}: {exc}", file=sys.stderr)
        return 2

    if args.check:
        if kanon.extract_block(current) == block:
            print(ui.line("ok", "agents.current", path=target, sha=kanon.kanon_sha()[:12]))
            return 0
        state = "agents.missing" if kanon.extract_block(current) is None else "agents.stale"
        print(ui.line("fail", state, path=target), file=sys.stderr)
        return 1
    if args.write:
        if updated != current:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(updated, encoding="utf-8")
            print(ui.line("wrote", "agents.updated", path=target))
        else:
            print(ui.line("ok", "agents.up_to_date", path=target))
        return 0
    print(block, end="")
    return 0


def resolve_linter(args: argparse.Namespace, ui: UI = DEFAULT_UI) -> Linter:
    """Select the active rule set: --rules > prepared file > copier-answers scope > all builtins.

    The prepared file is :data:`PREPARED_RULES_NAME`; a project that prepared
    under the previous release name still has :data:`LEGACY_PREPARED_RULES_NAME`,
    which is read only when the new name is absent.
    """
    repo = Path(getattr(args, "repo", "."))
    if args.rules:
        return Linter.from_yaml(args.rules)
    prepared = repo / PREPARED_RULES_NAME
    legacy = repo / LEGACY_PREPARED_RULES_NAME
    answers = find_answers_file(repo)
    if prepared.is_file():
        return Linter.from_yaml(prepared)
    if legacy.is_file():
        return Linter.from_yaml(legacy)
    if answers is not None and not getattr(args, "all", False):
        scoped = Linter.for_project(answers)
        print(ui.line("info", "scope.note", count=len(scoped.rules), answers=answers), file=sys.stderr)
        return scoped
    return Linter()


def _load_project_config(repo: Path) -> ProjectConfig | None:
    """``.daimonion.yml`` under ``repo`` when present (raises ConfigError when malformed)."""
    path = find_config(repo)
    return load_config(path) if path is not None else None


def scan(args: argparse.Namespace, linter: Linter, ui: UI = DEFAULT_UI) -> int:
    """Run ``check``/``diff``: match, apply ignores and the baseline, then report and decide the exit code."""
    repo = Path(args.repo)
    try:
        config = _load_project_config(repo)
    except ConfigError as exc:
        print(f"{ui.icon('warn')}{exc}", file=sys.stderr)
        return 2
    linter.include_docs = args.include_docs or (config is not None and config.scan_docs)

    if args.subcommand == "diff":
        findings = linter.scan_git_diff(staged=args.staged, repo_dir=repo)
        base = repo  # diff paths are repo-relative
    else:
        findings = linter.scan_paths(args.paths)
        base = Path.cwd()

    active = [f for f in findings if not f.suppressed]
    suppressed = [f for f in findings if f.suppressed]

    baseline_path = Path(args.baseline) if args.baseline else repo / BASELINE_NAME
    if args.write_baseline:
        count = write_baseline(baseline_path, active, base=base, repo=repo)
        print(ui.line("wrote", "baseline.wrote", count=count, path=baseline_path))
        return 0
    baselined: list[Finding] = []
    if baseline_path.is_file():
        try:
            active, baselined = split_baselined(active, load_baseline(baseline_path), base=base, repo=repo)
        except BaselineError as exc:
            print(f"{ui.icon('warn')}{exc}", file=sys.stderr)
            return 2
    elif args.baseline:
        print(ui.line("warn", "baseline.missing", path=baseline_path), file=sys.stderr)
        return 2

    mode = config.mode if config is not None else ""
    adoption = args.adoption or mode == "adoption"
    strict = (args.strict or mode == "strict") and not adoption
    blocking = [f for f in active if f.rule.enforcement == "L2"]
    strict_fail = strict and bool(blocking)

    if args.output_format == "json":
        report = build_json_report(active, strict_fail=strict_fail, suppressed=suppressed, baselined=baselined)
        report["summary"]["mode"] = "adoption" if adoption else "strict" if strict else "report"
        print(dumps(report))
    elif args.output_format == "sarif":
        print(dumps(build_sarif_report(active, suppressed=suppressed, baselined=baselined)))
    else:
        print(format_findings(active, verbose=args.verbose, suppressed=suppressed, baselined=baselined, ui=ui))

    if adoption and blocking:
        print(ui.line("info", "adoption.note", count=len(blocking)), file=sys.stderr)
    return 1 if strict_fail else 0


def _add_scan_options(sub: argparse.ArgumentParser) -> None:
    """Options shared by ``check`` and ``diff``."""
    sub.add_argument(
        "--include-docs",
        action="store_true",
        help="Also scan .md/.yml/.yaml/.toml (default: source code only; or set scan.docs in .daimonion.yml)",
    )
    sub.add_argument(
        "--baseline",
        default=None,
        help=f"Baseline file of accepted findings (default: {BASELINE_NAME} under --repo, when present)",
    )
    sub.add_argument(
        "--write-baseline", action="store_true", help="Record the current findings as the baseline and exit 0"
    )


def _display_options(*, top_level: bool) -> argparse.ArgumentParser:
    """``--lang``/``--no-emoji``, accepted before or after the subcommand.

    The subcommand copies default to SUPPRESS so they never overwrite a value
    given before the subcommand.
    """
    parent = argparse.ArgumentParser(add_help=False)
    default = None if top_level else argparse.SUPPRESS
    parent.add_argument(
        "--lang",
        choices=LANGS,
        default=default,
        help="Language of human-readable output (default: $DAIMONION_LANG, else the locale, else en)",
    )
    parent.add_argument(
        "--no-emoji",
        action="store_true",
        default=False if top_level else argparse.SUPPRESS,
        help="Drop the leading emoji icons from human-readable output (or set DAIMONION_NO_EMOJI=1)",
    )
    return parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="daimonion",
        description="Fast linter matching source files and git diffs against legal and ethical triggers.",
        parents=[_display_options(top_level=True)],
    )
    parser.add_argument("--rules", type=Path, default=None, help="Custom rules YAML file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show full matched lines")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 if any L2 (structural) rule triggers")
    parser.add_argument(
        "--adoption",
        action="store_true",
        help="Warn-only adoption mode: report findings but always exit 0, even with --strict "
        "(or set `mode: adoption` in .daimonion.yml)",
    )

    display = _display_options(top_level=False)
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # prepare
    p_prep = sub.add_parser(
        "prepare",
        parents=[display],
        help="Read .copier-answers.yml, infer the project type, and show the applicable compliance rules",
    )
    p_prep.add_argument("--repo", default=".", help="Project root containing .copier-answers.yml")
    p_prep.add_argument("--answers", default=None, help="Explicit path to a copier answers file")
    p_prep.add_argument("--write", action="store_true", help=f"Write {PREPARED_RULES_NAME} next to the answers file")

    # init
    p_init = sub.add_parser("init", parents=[display], help=f"Suggest a {CONFIG_NAME} from the repository's manifests")
    p_init.add_argument("--repo", default=".", help="Project root to inspect")
    p_init.add_argument("--write", action="store_true", help=f"Save the suggestion as {CONFIG_NAME}")
    p_init.add_argument("--force", action="store_true", help=f"Overwrite an existing {CONFIG_NAME}")

    # agents-md
    p_agents = sub.add_parser(
        "agents-md", parents=[display], help=f"Render the rules block (sourced kanon rules) selected by {CONFIG_NAME}"
    )
    p_agents.add_argument("--repo", default=".", help=f"Project root containing {CONFIG_NAME}")
    p_agents.add_argument("--config", default=None, help=f"Explicit path to a {CONFIG_NAME}")
    mode = p_agents.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Insert or refresh the block in the guide file")
    mode.add_argument("--check", action="store_true", help="Exit 1 when the guide file's block is missing or stale")

    # diff
    p_diff = sub.add_parser("diff", parents=[display], help="Scan git diff for modified lines")
    p_diff.add_argument("--staged", action="store_true", help="Scan staged changes instead of unstaged")
    p_diff.add_argument("--repo", default=".", help="Target repository directory (default: current)")
    p_diff.add_argument(
        "--all", action="store_true", help="Scan with every rule, ignoring the copier-derived project scope"
    )
    p_diff.add_argument(
        "--format",
        dest="output_format",
        choices=FORMAT_CHOICES,
        default="human",
        help="Output format for findings (default: human)",
    )
    _add_scan_options(p_diff)

    # check
    p_check = sub.add_parser("check", parents=[display], help="Scan specific files or directories")
    p_check.add_argument("paths", nargs="+", help="Files or directories to scan")
    p_check.add_argument("--repo", default=".", help="Project root for copier-derived scoping")
    p_check.add_argument(
        "--all", action="store_true", help="Scan with every rule, ignoring the copier-derived project scope"
    )
    p_check.add_argument(
        "--format",
        dest="output_format",
        choices=FORMAT_CHOICES,
        default="human",
        help="Output format for findings (default: human)",
    )
    _add_scan_options(p_check)

    # list-rules
    p_list = sub.add_parser("list-rules", parents=[display], help="List all active detection rules")
    p_list.add_argument("--repo", default=".", help="Project root for copier-derived scoping")
    p_list.add_argument("--all", action="store_true", help="List every rule, ignoring the copier-derived project scope")
    p_list.add_argument(
        "--format",
        dest="output_format",
        choices=RULE_FORMAT_CHOICES,
        default="human",
        help="Output format for the rule list (default: human)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ui = UI.create(resolve_lang(getattr(args, "lang", None)), emoji=resolve_emoji(getattr(args, "no_emoji", False)))

    if args.subcommand == "prepare":
        return prepare(args, ui)
    if args.subcommand == "init":
        return init(args, ui)
    if args.subcommand == "agents-md":
        return agents_md(args, ui)

    linter = resolve_linter(args, ui)

    if args.subcommand == "list-rules":
        if args.output_format == "json":
            print(dumps(build_rules_json_report(linter.rules)))
            return 0
        print(ui.t("rules.header", count=len(linter.rules)))
        for r in linter.rules:
            print(f"- [{r.enforcement}] {r.id}: {ui.rule_title(r)}")
            print(f"  {ui.t('rules.summary', summary=ui.rule_summary(r))}")
        return 0

    return scan(args, linter, ui)


if __name__ == "__main__":
    sys.exit(main())
