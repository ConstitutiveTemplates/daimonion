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
