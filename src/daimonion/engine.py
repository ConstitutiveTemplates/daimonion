from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any, NamedTuple

from daimonion.context import scope_rules
from daimonion.models import Finding, Rule, Suppression
from daimonion.rules import BUILTIN_RULES, load_rules_from_yaml
from daimonion.suppress import parse_line

#: Source-code suffixes ``scan_paths`` descends into by default.
SOURCE_SUFFIXES: frozenset[str] = frozenset({".py", ".ts", ".js", ".go", ".rs", ".java"})

#: Documentation and configuration suffixes, scanned only when docs are opted in
#: (``scan: {docs: true}`` in ``.daimonion.yml`` or ``--include-docs``): a README
#: that mentions "license" is not a licensing change.
DOC_SUFFIXES: frozenset[str] = frozenset({".md", ".yml", ".yaml", ".toml"})

#: The rulebook ``when`` conditions a project can declare in ``.daimonion.yml``
#: (``always`` sections apply without being listed). Kept next to the engine
#: so rule gates can name them directly; mirrors ``WHEN_VOCABULARY``.
RULEBOOK_CONDITIONS: tuple[str, ...] = (
    "always",
    "library",
    "cli",
    "embedded",
    "personal_data",
    "face_recognition",
    "medtech",
    "scraping",
    "oj_code",
    "kaggle",
    "mcp",
    "data_science",
    "web_api",
    "commercial",
    "eu_market",
    "jp",
    "ai_assisted",
)

#: Historical name for :data:`RULEBOOK_CONDITIONS`; kept for backward compatibility.
KANON_CONDITIONS: tuple[str, ...] = RULEBOOK_CONDITIONS


def _gate_names(gate: str) -> set[str]:
    """The bare names a gate expression references (empty gate: no names)."""
    import ast

    gate = (gate or "").strip()
    if not gate:
        return set()
    try:
        tree = ast.parse(gate, mode="eval")
    except SyntaxError:
        return set()
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def when_to_answers(when: Iterable[str]) -> dict[str, Any]:
    """Answer-vocabulary flags reconstructed from declared ``when`` conditions.

    Lets gates written in the old copier-answers vocabulary (``web_api``,
    ``mcp_effective``, ``domain_traits``, ...) keep working under a
    ``.daimonion.yml`` scope: each declared condition sets the answers that
    would have implied it.
    """
    declared = set(when)
    traits = [
        trait
        for trait, condition in (
            ("personal-data", "personal_data"),
            ("face-recognition", "face_recognition"),
            ("medtech", "medtech"),
        )
        if condition in declared
    ]
    project_type = next(
        (
            answer
            for answer, condition in (
                ("library", "library"),
                ("cli", "cli"),
                ("web_api", "web_api"),
                ("data_science", "data_science"),
                ("micropython", "embedded"),
            )
            if condition in declared
        ),
        "",
    )
    answers: dict[str, Any] = {
        "project_type": project_type,
        "domain_traits": traits,
        "distribution": ["commercial"] if "commercial" in declared else [],
        "oj_kind": "kaggle" if "kaggle" in declared else ("atcoder" if "oj_code" in declared else ""),
        "include_mcp": "mcp" in declared,
        "include_scraping": "scraping" in declared,
        "include_web_api": "web_api" in declared and project_type != "web_api",
        "include_data_science": "data_science" in declared and project_type != "data_science",
    }
    if ("kaggle" in declared or "oj_code" in declared) and project_type == "":
        answers["project_type"] = "online_judge"
    return answers


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


def _iter_candidate_files(paths: Iterable[str | Path], suffixes: frozenset[str] = SOURCE_SUFFIXES) -> Iterator[Path]:
    """Yield scannable files for the given files/directories.

    An explicitly named file is always yielded; directories contribute only
    files whose suffix is in ``suffixes``.
    """
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
                    if candidate.suffix.lower() in suffixes:
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

    def __init__(self, rules: Iterable[Rule] | None = None, *, include_docs: bool = False) -> None:
        self.rules: list[Rule] = list(rules) if rules is not None else list(BUILTIN_RULES)
        self.include_docs = include_docs
        self._compiled: list[tuple[Rule, re.Pattern[str]]] = []
        for rule in self.rules:
            pattern = _compile_rule(rule)
            if pattern is not None:
                self._compiled.append((rule, pattern))

    @classmethod
    def from_yaml(cls, path: str | Path) -> Linter:
        """Load rules from an external YAML file (e.g. a law-map ``checks/`` dir or REGISTRY.yml)."""
        return cls(load_rules_from_yaml(path))

    def for_context(self, context: Mapping[str, Any]) -> Linter:
        """Return a new Linter holding only the rules whose gate holds in context."""
        return Linter(scope_rules(self.rules, context), include_docs=self.include_docs)

    def for_when(self, when: Iterable[str]) -> Linter:
        """Scope the rules to the rulebook ``when`` conditions a project declares.

        A rule whose gate names a ``when`` condition applies when the project
        declares it; a gate naming anything else falls back to the
        answer-vocabulary context (``web_api``, ``mcp_effective``, ...),
        derived from the ``when`` set as if it were the answers. Rules whose
        gate mentions neither stay as they are.
        """
        from daimonion.context import derive_context

        declared = set(when) | {"always"}
        scoped: list[Rule] = []
        for rule in self.rules:
            gate_names = _gate_names(rule.gate)
            if not gate_names:
                scoped.append(rule)
                continue
            if gate_names <= set(KANON_CONDITIONS):
                context = {condition: condition in declared for condition in KANON_CONDITIONS}
                context |= {"true": True, "false": False}
                scoped.extend(scope_rules([rule], context))
                continue
            scoped.extend(scope_rules([rule], derive_context(when_to_answers(declared))))
        return Linter(scoped, include_docs=self.include_docs)

    @property
    def suffixes(self) -> frozenset[str]:
        """File suffixes a directory scan descends into."""
        return SOURCE_SUFFIXES | DOC_SUFFIXES if self.include_docs else SOURCE_SUFFIXES

    def _match_compiled(
        self,
        text: str,
        *,
        file_path: str,
        line_number: int,
        directives: Iterable[Suppression] = (),
    ) -> list[Finding]:
        """Match the pre-compiled rule patterns against a single line of text.

        ``text`` may carry a trailing ignore directive; only the code before it
        is matched, and a directive naming the rule is attached to the finding.
        """
        parsed = parse_line(text, line_number)
        active = [d for d in (*directives, parsed.directive) if d is not None]
        findings: list[Finding] = []
        for rule, pattern in self._compiled:
            match = pattern.search(parsed.code)
            if match:
                findings.append(
                    Finding(
                        rule=rule,
                        file_path=file_path,
                        line_number=line_number,
                        matched_text=match.group(0),
                        context_line=text.strip(),
                        suppression=next((d for d in active if d.covers(rule.id)), None),
                    )
                )
        return findings

    def scan_text(self, text: str, file_path: str = "<stdin>") -> list[Finding]:
        """Scan a string line by line and report matched findings."""
        findings: list[Finding] = []
        pending: Suppression | None = None
        for line_no, line in enumerate(text.splitlines(), start=1):
            carried, pending = pending, None
            if not line.strip() or _is_self_trigger_comment(line):
                continue
            parsed = parse_line(line, line_no)
            if parsed.standalone:
                pending = parsed.directive
                continue
            directives = (carried,) if carried is not None else ()
            findings.extend(self._match_compiled(line, file_path=file_path, line_number=line_no, directives=directives))
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
        for candidate in _iter_candidate_files(paths, self.suffixes):
            findings.extend(self.scan_file(candidate))
        return findings

    def scan_git_diff(self, *, staged: bool = False, repo_dir: str | Path = ".") -> list[Finding]:
        """Inspect added or modified lines in git diff."""
        diff_text = _run_git_diff(staged=staged, repo_dir=repo_dir)
        if diff_text is None:
            return []
        findings: list[Finding] = []
        previous: dict[str, AddedLine] = {}
        for added in _iter_added_lines(diff_text):
            prior = previous.get(added.file_path)
            previous[added.file_path] = added
            if Path(added.file_path).suffix.lower() in DOC_SUFFIXES and not self.include_docs:
                continue
            if not added.text.strip() or parse_line(added.text).standalone:
                continue
            # A standalone directive on the line above: an added line when the
            # diff carries it, otherwise the unchanged line in the work tree.
            if prior is not None and prior.line_number == added.line_number - 1:
                above = prior.text
            else:
                above = _line_from_worktree(Path(repo_dir) / added.file_path, added.line_number - 1)
            directive = parse_line(above, added.line_number - 1) if above is not None else None
            directives = (directive.directive,) if directive is not None and directive.standalone else ()
            findings.extend(
                self._match_compiled(
                    added.text, file_path=added.file_path, line_number=added.line_number, directives=directives
                )
            )
        return findings


def _line_from_worktree(path: Path, line_number: int) -> str | None:
    """Line ``line_number`` (1-based) of ``path``, or None when unavailable."""
    if line_number < 1:
        return None
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle, start=1):
                if index == line_number:
                    return line.rstrip("\n")
    except OSError:
        return None
    return None
