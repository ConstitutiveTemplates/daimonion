from __future__ import annotations

import argparse
import sys
from pathlib import Path

from daimonion import kanon
from daimonion.config import CONFIG_NAME, ConfigError, ProjectConfig, find_config, load_config
from daimonion.context import answers_to_when, find_answers_file, load_answers
from daimonion.detect import UNDETECTABLE, Signal, default_agents_md, detect, render_config
from daimonion.engine import Linter
from daimonion.i18n import DEFAULT_UI, LANGS, UI, resolve_emoji, resolve_lang
from daimonion.kanon import WHEN_VOCABULARY
from daimonion.models import Finding
from daimonion.report import build_json_report, build_rules_json_report, build_sarif_report, dumps
from daimonion.suppress import BASELINE_NAME, BaselineError, load_baseline, split_baselined, write_baseline

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


def init(args: argparse.Namespace, ui: UI = DEFAULT_UI) -> int:
    """Write a .daimonion.yml from manifests, agent files, and .copier-answers.yml.

    The answers file is read **once**, here: its answers convert to ``when``
    conditions that merge with the manifest-detected signals. ``scan`` and
    ``agents-md`` later read only the written ``.daimonion.yml``.
    """
    repo = Path(args.repo)
    signals = detect(repo)
    answers_path = Path(args.answers) if args.answers else find_answers_file(repo)
    converted = answers_to_when(load_answers(answers_path)) if answers_path is not None else []
    known = set(WHEN_VOCABULARY)
    converted = [c for c in converted if c in known]
    merged = list(signals)
    seen = {s.condition for s in merged}
    source = answers_path.name if answers_path is not None else ".copier-answers.yml"
    for condition in converted:
        if condition not in seen:
            seen.add(condition)
            merged.append(Signal(condition, source, "converted from copier answers"))
    text = render_config(merged, agents_md=default_agents_md(repo))
    target = repo / CONFIG_NAME

    print(ui.line("scan", "init.header", path=repo.resolve()))
    if answers_path is not None:
        print(ui.line("plan", "init.answers", path=answers_path))
        if converted:
            print(f"   {', '.join(converted)}")
        else:
            print("   " + ui.t("init.answers_none"))
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


def resolve_rules(args: argparse.Namespace, config: ProjectConfig | None, ui: UI = DEFAULT_UI) -> Linter:
    """Select the active rule set: --rules wins, else the ``.daimonion.yml`` conditions gate the builtins.

    ``scan`` and ``agents-md`` read only ``.daimonion.yml``: a project with
    no config scans everything, exactly like ``--all``.
    """
    if args.rules:
        return Linter.from_yaml(args.rules)
    base = Linter()
    if config is None or getattr(args, "all", False):
        return base
    scoped = base.for_when(config.when)
    print(ui.line("info", "scope.note", count=len(scoped.rules), config=config.path), file=sys.stderr)
    return scoped


def _load_project_config(repo: Path) -> ProjectConfig | None:
    """``.daimonion.yml`` under ``repo`` when present (raises ConfigError when malformed)."""
    path = find_config(repo)
    return load_config(path) if path is not None else None


def scan(args: argparse.Namespace, ui: UI = DEFAULT_UI) -> int:
    """Run ``scan``: match, apply ignores and the baseline, then report and decide the exit code."""
    repo = Path(args.repo)
    try:
        config = _load_project_config(repo)
    except ConfigError as exc:
        print(f"{ui.icon('warn')}{exc}", file=sys.stderr)
        return 2
    linter = resolve_rules(args, config, ui)
    linter.include_docs = args.include_docs or (config is not None and config.scan_docs)

    if args.paths:
        findings = linter.scan_paths(args.paths)
        base = Path.cwd()
    else:
        findings = linter.scan_git_diff(staged=args.staged, repo_dir=repo)
        base = repo  # diff paths are repo-relative

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
    """Options shared by the two ``scan`` modes (paths vs git diff)."""
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

    # init: convert manifests + .copier-answers.yml into .daimonion.yml
    p_init = sub.add_parser(
        "init", parents=[display], help=f"Write a {CONFIG_NAME} from manifests and .copier-answers.yml"
    )
    p_init.add_argument("--repo", default=".", help="Project root to inspect")
    p_init.add_argument("--answers", default=None, help="Explicit path to a copier answers file")
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

    # scan: findings over explicit paths, or over the git diff when no paths are given
    p_scan = sub.add_parser("scan", parents=[display], help="Scan paths, or the git diff when no paths are given")
    p_scan.add_argument("paths", nargs="*", help="Files or directories to scan (default: scan the git diff)")
    p_scan.add_argument("--staged", action="store_true", help="Scan staged changes instead of unstaged (diff mode)")
    p_scan.add_argument("--repo", default=".", help=f"Project root containing {CONFIG_NAME}")
    p_scan.add_argument("--all", action="store_true", help=f"Scan with every rule, ignoring the {CONFIG_NAME} scope")
    p_scan.add_argument(
        "--format",
        dest="output_format",
        choices=FORMAT_CHOICES,
        default="human",
        help="Output format for findings (default: human)",
    )
    p_scan.add_argument("--list-rules", action="store_true", help="List the active detection rules instead of scanning")
    p_scan.add_argument(
        "--list-format",
        dest="list_format",
        choices=RULE_FORMAT_CHOICES,
        default="human",
        help="Output format for --list-rules (default: human)",
    )
    _add_scan_options(p_scan)

    return parser


def list_rules(args: argparse.Namespace, ui: UI = DEFAULT_UI) -> int:
    """List the rules ``scan`` would use: ``--rules`` wins, else the ``.daimonion.yml`` scope."""
    repo = Path(args.repo)
    try:
        config = _load_project_config(repo)
    except ConfigError as exc:
        print(f"{ui.icon('warn')}{exc}", file=sys.stderr)
        return 2
    rules = resolve_rules(args, config, ui).rules
    if getattr(args, "list_format", "human") == "json":
        print(dumps(build_rules_json_report(rules)))
        return 0
    print(ui.t("rules.header", count=len(rules)))
    for r in rules:
        print(f"- [{r.enforcement}] {r.id}: {ui.rule_title(r)}")
        print(f"  {ui.t('rules.summary', summary=ui.rule_summary(r))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ui = UI.create(resolve_lang(getattr(args, "lang", None)), emoji=resolve_emoji(getattr(args, "no_emoji", False)))

    if args.subcommand == "init":
        return init(args, ui)
    if args.subcommand == "agents-md":
        return agents_md(args, ui)

    if getattr(args, "list_rules", False):
        return list_rules(args, ui)
    return scan(args, ui)


if __name__ == "__main__":
    sys.exit(main())
