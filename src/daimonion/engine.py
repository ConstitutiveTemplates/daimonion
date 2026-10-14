from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any, NamedTuple

from daimonion.context import derive_context, load_answers, scope_rules
from daimonion.models import Finding, Rule
from daimonion.rules import BUILTIN_RULES, load_rules_from_yaml

#: File suffixes ``scan_paths`` descends into.
SOURCE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".py",
        ".ts",
        ".js",
        ".go",
        ".rs",
        ".java",
        ".md",
        ".yml",
        ".yaml",
        ".toml",
    }
)


class AddedLine(NamedTuple):
    """A single added line parsed from unified diff output."""

    file_path: str
    line_number: int
    text: str


def _compile_rule(rule: Rule) -> re.Pattern[str] | None:
    """Compile a rule's trigger pattern, returning None when it is invalid."""
    try:
        return re.compile(rule.triggers)
    except re.error:
        return None


def _is_self_trigger_comment(line: str) -> bool:
    """Whether a line only documents triggers (never a real violation)."""
    stripped = line.strip()
    return stripped.startswith("#") and "Triggers:" in stripped


def _iter_candidate_files(paths: Iterable[str | Path]) -> Iterator[Path]:
    """Yield scannable files for the given files/directories."""
    for raw in paths:
        target = Path(raw)
        if target.is_file():
            yield target
        elif target.is_dir():
            for root, _, files in os.walk(target):
                if any(part.startswith(".") for part in Path(root).parts):
                    continue
                for name in files:
                    candidate = Path(root) / name
                    if candidate.suffix.lower() in SOURCE_SUFFIXES:
                        yield candidate


def _run_git_diff(*, staged: bool, repo_dir: str | Path) -> str | None:
    """Run git diff and return its stdout, or None when git is unavailable."""
    cmd = ["git", "diff", "--unified=0"]
    if staged:
        cmd.append("--cached")
    try:
        completed = subprocess.run(cmd, cwd=str(repo_dir), capture_output=True, text=True, check=True)
    except (subprocess.SubprocessError, OSError):
        return None
    return completed.stdout


def _iter_added_lines(diff_text: str) -> Iterator[AddedLine]:
    """Parse added lines (with file and new-side line number) from a unified diff."""
    current_file = ""
    current_line_no = 0
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line.removeprefix("+++ b/")
        elif line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            if match:
                current_line_no = int(match.group(1)) - 1
        elif line.startswith("+") and not line.startswith("+++"):
            current_line_no += 1
            yield AddedLine(file_path=current_file, line_number=current_line_no, text=line[1:])


class Linter:
    """Scanning engine that matches files or git diffs against compliance rules."""

    def __init__(self, rules: Iterable[Rule] | None = None) -> None:
        self.rules: list[Rule] = list(rules) if rules is not None else list(BUILTIN_RULES)
        self._compiled: list[tuple[Rule, re.Pattern[str]]] = []
        for rule in self.rules:
            pattern = _compile_rule(rule)
            if pattern is not None:
                self._compiled.append((rule, pattern))

    @classmethod
    def from_yaml(cls, path: str | Path) -> Linter:
        """Load rules from an external YAML file (e.g. from kanon, law-map, or REGISTRY.yml)."""
        return cls(load_rules_from_yaml(path))

    def for_context(self, context: Mapping[str, Any]) -> Linter:
        """Return a new Linter holding only the rules whose gate holds in context."""
        return Linter(scope_rules(self.rules, context))

    @classmethod
    def for_project(cls, answers_path: str | Path, base_rules: Linter | None = None) -> Linter:
        """Build a scoped Linter from a project's .copier-answers.yml."""
        context = derive_context(load_answers(answers_path))
        linter = base_rules if base_rules is not None else cls()
        return linter.for_context(context)

    def _match_compiled(self, text: str, *, file_path: str, line_number: int) -> list[Finding]:
        """Match the pre-compiled rule patterns against a single line of text."""
        findings: list[Finding] = []
        for rule, pattern in self._compiled:
            match = pattern.search(text)
            if match:
                findings.append(
                    Finding(
                        rule=rule,
                        file_path=file_path,
                        line_number=line_number,
                        matched_text=match.group(0),
                        context_line=text.strip(),
                    )
                )
        return findings

    def scan_text(self, text: str, file_path: str = "<stdin>") -> list[Finding]:
        """Scan a string line by line and report matched findings."""
        findings: list[Finding] = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.strip() or _is_self_trigger_comment(line):
                continue
            findings.extend(self._match_compiled(line, file_path=file_path, line_number=line_no))
        return findings

    def scan_file(self, path: str | Path) -> list[Finding]:
        """Scan a single file."""
        target = Path(path)
        if not target.is_file():
            return []
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        return self.scan_text(content, file_path=str(target))

    def scan_paths(self, paths: Iterable[str | Path]) -> list[Finding]:
        """Recursively scan given paths."""
        findings: list[Finding] = []
        for candidate in _iter_candidate_files(paths):
            findings.extend(self.scan_file(candidate))
        return findings

    def scan_git_diff(self, *, staged: bool = False, repo_dir: str | Path = ".") -> list[Finding]:
        """Inspect added or modified lines in git diff."""
        diff_text = _run_git_diff(staged=staged, repo_dir=repo_dir)
        if diff_text is None:
            return []
        findings: list[Finding] = []
        for added in _iter_added_lines(diff_text):
            findings.extend(self._match_compiled(added.text, file_path=added.file_path, line_number=added.line_number))
        return findings
