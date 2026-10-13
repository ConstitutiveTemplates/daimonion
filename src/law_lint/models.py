from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Rule:
    """A legal/ethical compliance rule with its detection triggers."""

    id: str
    title: str
    triggers: str
    summary: str
    category: str = "general"
    enforcement: str = "L1"
    gate: str = ""

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
        }


@dataclass(frozen=True)
class Finding:
    """A finding indicating a rule trigger matched a line in a file."""

    rule: Rule
    file_path: str
    line_number: int
    matched_text: str
    context_line: str


#: Historical name for :class:`Finding`; kept for backward compatibility.
MatchFinding = Finding

__all__ = ["Finding", "MatchFinding", "Rule"]
