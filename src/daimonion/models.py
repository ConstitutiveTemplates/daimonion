from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

#: A ``keyword`` rule matches topic vocabulary (``license``, ``agent``, ``md5``):
#: a reminder that a compliance area was touched, never proof of a violation.
#: A ``structural`` rule matches the violating construct itself (AST, semgrep,
#: dependency analysis); only those may block CI at L2.
RULE_KINDS: tuple[str, ...] = ("keyword", "structural")

#: Highest enforcement a ``keyword`` rule can carry; a declared L2 is capped here.
KEYWORD_MAX_ENFORCEMENT = "L1"


def effective_enforcement(enforcement: str, kind: str) -> str:
    """The enforcement a rule actually carries: keyword rules never exceed L1."""
    if kind != "structural" and enforcement.strip().upper() == "L2":
        return KEYWORD_MAX_ENFORCEMENT
    return enforcement


@dataclass(frozen=True)
class Rule:
    """A legal/ethical compliance rule with its detection triggers.

    ``enforcement`` is capped by :func:`effective_enforcement` at construction,
    so a keyword rule declared L2 (in YAML, a law-map spec, or code) is L1.
    """

    id: str
    title: str
    triggers: str
    summary: str
    category: str = "general"
    enforcement: str = "L1"
    gate: str = ""
    kind: str = "keyword"

    def __post_init__(self) -> None:
        object.__setattr__(self, "enforcement", effective_enforcement(self.enforcement, self.kind))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Rule:
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            triggers=str(data.get("triggers", "")),
            summary=str(data.get("summary", "")),
            category=str(data.get("category", "general")),
            enforcement=str(data.get("enforcement", "L1")),
            gate=str(data.get("gate", "")),
            kind=str(data.get("kind", "keyword")),
        )

    @classmethod
    def from_check_spec(cls, data: Mapping[str, Any]) -> Rule:
        """Build a rule from a law-map ``checks/<domain>/<slug>.yml`` spec.

        A spec carries ``id`` (``domain/slug``), ``obligation``, ``level``,
        and an optional ``triggers`` list of regex strings; the rule joins
        the list into one alternation so the engine's single-pattern match
        applies. Specs without ``triggers`` map to ``(?!)`` — a pattern
        that matches nothing — so the file-presence gate they describe
        still shows in ``list-rules`` but can never fire on scanned text.
        """
        triggers = data.get("triggers", [])
        if isinstance(triggers, str):
            pattern = triggers
        elif isinstance(triggers, list):
            # Join bare with ``|`` (no wrapping group): wrapping a pattern
            # like ``(?i)\\b...`` in ``(?:...)`` moves the global flag off
            # the start of the expression, which ``re`` rejects.
            joined = "|".join(item for item in triggers if isinstance(item, str) and item)
            pattern = joined if joined else "(?!)"
        else:
            pattern = "(?!)"
        summary = data.get("acceptance", data.get("summary", ""))
        if not isinstance(summary, str):
            summary = str(summary)
        obligation = data.get("obligation", "")
        if summary:
            summary_text = summary
        elif isinstance(obligation, str) and obligation:
            summary_text = f"Check spec for {obligation}."
        else:
            summary_text = ""
        category = str(data.get("id", "")).split("/")[0] or "general"
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("obligation", str(data.get("id", "")))),
            triggers=pattern,
            summary=summary_text,
            category=category,
            enforcement=str(data.get("level", "L1")),
            gate="",
            kind=str(data.get("kind", "keyword")),
        )

    def to_dict(self) -> dict[str, str]:
        """Serialize back to the plain-dict shape :meth:`from_dict` consumes."""
        return {
            "id": self.id,
            "title": self.title,
            "triggers": self.triggers,
            "summary": self.summary,
            "category": self.category,
            "enforcement": self.enforcement,
            "gate": self.gate,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class Suppression:
    """An inline ``daimonion: ignore[rule-id] reason=... until=YYYY-MM-DD`` directive."""

    rule_ids: tuple[str, ...]
    reason: str
    until: date | None = None
    line_number: int = 0

    def covers(self, rule_id: str) -> bool:
        return rule_id in self.rule_ids or "*" in self.rule_ids

    def status(self, today: date | None = None) -> str:
        """``active``, ``expired`` (past ``until``), or ``invalid`` (no reason given)."""
        if not self.reason:
            return "invalid"
        if self.until is not None and self.until < (today or date.today()):
            return "expired"
        return "active"


@dataclass(frozen=True)
class Finding:
    """A finding indicating a rule trigger matched a line in a file.

    ``suppression`` is the inline directive naming this finding's rule, if any;
    it silences the finding only while :meth:`Suppression.status` is ``active``.
    """

    rule: Rule
    file_path: str
    line_number: int
    matched_text: str
    context_line: str
    suppression: Suppression | None = None

    @property
    def suppressed(self) -> bool:
        return self.suppression is not None and self.suppression.status() == "active"


#: Historical name for :class:`Finding`; kept for backward compatibility.
MatchFinding = Finding

__all__ = [
    "KEYWORD_MAX_ENFORCEMENT",
    "RULE_KINDS",
    "Finding",
    "MatchFinding",
    "Rule",
    "Suppression",
    "effective_enforcement",
]
