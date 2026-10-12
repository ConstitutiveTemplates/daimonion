from __future__ import annotations

import argparse
import sys
from pathlib import Path

from law_lint.engine import Linter
from law_lint.models import MatchFinding


def format_findings(findings: list[MatchFinding], *, verbose: bool = False) -> str:
    """Format findings for terminal output."""
    if not findings:
        return "✨ No legal or compliance triggers matched."

    # Group by rule id
    by_rule: dict[str, list[MatchFinding]] = {}
    for f in findings:
        by_rule.setdefault(f.rule.id, []).append(f)

    lines: list[str] = [
        f"⚠️  law-lint: Detected {len(findings)} trigger match(es) across {len(by_rule)} compliance area(s):\n"
    ]

    for rule_id, rule_findings in by_rule.items():
        rule = rule_findings[0].rule
        badge = f"[{rule.enforcement}]" if rule.enforcement else ""
        lines.append(f"📌 {badge} {rule.title} ({rule_id})")
        lines.append(f"   💡 要約: {rule.summary}")
        lines.append("   🔎 検出箇所:")
        for rf in rule_findings[:5]:
            lines.append(f"      - {rf.file_path}:{rf.line_number} (hit: '{rf.matched_text}')")
            if verbose:
                lines.append(f"        line: {rf.context_line}")
        if len(rule_findings) > 5:
            lines.append(f"      ... and {len(rule_findings) - 5} more occurrence(s)")
        lines.append("")

    return "\n".join(lines).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="law-lint",
        description="Fast linter matching source files and git diffs against legal and ethical triggers.",
    )
    parser.add_argument("--rules", type=Path, default=None, help="Custom rules YAML file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show full matched lines")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 if any L2 rule triggers")

    sub = parser.add_subparsers(dest="subcommand", required=True)

    # diff
    p_diff = sub.add_parser("diff", help="Scan git diff for modified lines")
    p_diff.add_argument("--staged", action="store_true", help="Scan staged changes instead of unstaged")
    p_diff.add_argument("--repo", default=".", help="Target repository directory (default: current)")

    # check
    p_check = sub.add_parser("check", help="Scan specific files or directories")
    p_check.add_argument("paths", nargs="+", help="Files or directories to scan")

    # list-rules
    sub.add_parser("list-rules", help="List all active detection rules")

    args = parser.parse_args(argv)

    linter = Linter.from_yaml(args.rules) if args.rules else Linter()

    if args.subcommand == "list-rules":
        print(f"Active compliance rules ({len(linter.rules)}):")
        for r in linter.rules:
            print(f"- [{r.enforcement}] {r.id}: {r.title}")
            print(f"  Summary: {r.summary}")
        return 0

    if args.subcommand == "diff":
        findings = linter.scan_git_diff(staged=args.staged, repo_dir=args.repo)
    elif args.subcommand == "check":
        findings = linter.scan_paths(args.paths)
    else:
        findings = []

    print(format_findings(findings, verbose=args.verbose))

    if args.strict and any(f.rule.enforcement == "L2" for f in findings):
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
