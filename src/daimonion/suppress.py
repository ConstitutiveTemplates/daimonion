"""Adoption controls: inline ignore directives and the findings baseline.

An inline directive silences named rules on its own line, or on the next line
when it stands alone on a comment line::

    ua = "my-crawler-agent/1.0"  # daimonion: ignore[llm-appsec] reason=HTTP User-Agent until=2027-01-31

    # daimonion: ignore[licensing/no-copyleft-contamination] reason=vendored notice
    LICENSE_URL = "https://..."

``reason=`` is required (a directive without one is not honoured) and
``until=`` is optional; past that date the finding is reported again.

The baseline (``.daimonion-baseline.json``) records findings that already
exist when a project adopts daimonion, keyed by rule, repo-relative file, and
the matched line's text, so unrelated edits that shift line numbers keep
matching. Baselined findings are reported but never fail ``--strict``.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Any, NamedTuple

from daimonion.models import Finding, Suppression

BASELINE_NAME = ".daimonion-baseline.json"
BASELINE_VERSION = 1

_DIRECTIVE_RE = re.compile(r"daimonion:\s*ignore\[(?P<ids>[^\]]*)\](?P<rest>.*)$")
_UNTIL_RE = re.compile(r"\buntil=(?P<date>\S+)")
_REASON_RE = re.compile(r"\breason=(?P<reason>.*)$")
#: Comment openers a standalone directive line may start with.
_COMMENT_PREFIXES = ("#", "//", "--", "/*", "*", "<!--", ";")
#: Comment closers trimmed from the end of a reason.
_COMMENT_SUFFIXES = ("-->", "*/")


class ParsedLine(NamedTuple):
    """A source line split into scannable code and its ignore directive."""

    code: str
    directive: Suppression | None
    standalone: bool


def parse_line(line: str, line_number: int = 0) -> ParsedLine:
    """Split off a ``daimonion: ignore[...]`` directive from a line.

    ``code`` is the text before the directive, so a reason never triggers a
    rule itself. ``standalone`` is true when the line holds only a comment
    carrying the directive; such a directive applies to the next line.
    """
    match = _DIRECTIVE_RE.search(line)
    if match is None:
        return ParsedLine(line, None, False)
    ids = tuple(part.strip() for part in match.group("ids").split(",") if part.strip())
    rest = match.group("rest").strip()
    for suffix in _COMMENT_SUFFIXES:
        rest = rest.removesuffix(suffix).rstrip()
    until: date | None = None
    until_match = _UNTIL_RE.search(rest)
    if until_match is not None:
        try:
            until = date.fromisoformat(until_match.group("date"))
        except ValueError:
            # An unreadable date must not silence forever: treat it as already past.
            until = date.min
        rest = (rest[: until_match.start()] + rest[until_match.end() :]).strip()
    reason_match = _REASON_RE.search(rest)
    reason = reason_match.group("reason").strip().strip("\"'") if reason_match else ""
    code = line[: match.start()]
    stripped = code.strip()
    standalone = not stripped or stripped in _COMMENT_PREFIXES
    directive = Suppression(rule_ids=ids, reason=reason, until=until, line_number=line_number) if ids else None
    return ParsedLine(code, directive, standalone and directive is not None)


class BaselineError(ValueError):
    """The baseline file is unreadable or malformed."""


def _relative(file_path: str, base: Path, repo: Path) -> str:
    """``file_path`` (relative to ``base`` unless absolute) as a repo-relative POSIX path."""
    path = Path(file_path)
    resolved = (path if path.is_absolute() else base / path).resolve()
    try:
        return resolved.relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _key(finding: Finding, base: Path, repo: Path) -> tuple[str, str, str]:
    return (finding.rule.id, _relative(finding.file_path, base, repo), finding.context_line)


def load_baseline(path: str | Path) -> Counter[tuple[str, str, str]]:
    """Read a baseline file into a multiset of ``(rule_id, file, line text)`` keys."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"{path}: cannot read baseline: {exc}"
        raise BaselineError(msg) from exc
    if (
        not isinstance(data, dict)
        or data.get("version") != BASELINE_VERSION
        or not isinstance(data.get("findings"), list)
    ):
        msg = f"{path}: expected {{'version': {BASELINE_VERSION}, 'findings': [...]}}"
        raise BaselineError(msg)
    keys: Counter[tuple[str, str, str]] = Counter()
    for entry in data["findings"]:
        if not isinstance(entry, dict):
            continue
        key = (str(entry.get("rule_id", "")), str(entry.get("file", "")), str(entry.get("line", "")))
        keys[key] += int(entry.get("count", 1))
    return keys


def write_baseline(path: str | Path, findings: Iterable[Finding], *, base: Path, repo: Path) -> int:
    """Write ``findings`` as the new baseline; returns the number of findings recorded."""
    counts = Counter(_key(finding, base, repo) for finding in findings)
    entries: list[dict[str, Any]] = [
        {"rule_id": rule_id, "file": file, "line": line, "count": count}
        for (rule_id, file, line), count in sorted(counts.items())
    ]
    payload = {"version": BASELINE_VERSION, "findings": entries}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return sum(counts.values())


def split_baselined(
    findings: Sequence[Finding], baseline: Counter[tuple[str, str, str]], *, base: Path, repo: Path
) -> tuple[list[Finding], list[Finding]]:
    """Partition into ``(new, baselined)``; each baseline entry absorbs up to ``count`` findings."""
    remaining = Counter(baseline)
    new: list[Finding] = []
    baselined: list[Finding] = []
    for finding in findings:
        key = _key(finding, base, repo)
        if remaining[key] > 0:
            remaining[key] -= 1
            baselined.append(finding)
        else:
            new.append(finding)
    return new, baselined


__all__ = [
    "BASELINE_NAME",
    "BASELINE_VERSION",
    "BaselineError",
    "ParsedLine",
    "load_baseline",
    "parse_line",
    "split_baselined",
    "write_baseline",
]
