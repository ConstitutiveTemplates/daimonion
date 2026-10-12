from __future__ import annotations

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
    def from_dict(cls, data: dict[str, Any]) -> Rule:
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            triggers=str(data.get("triggers", "")),
            summary=str(data.get("summary", "")),
            category=str(data.get("category", "general")),
            enforcement=str(data.get("enforcement", "L1")),
            gate=str(data.get("gate", "")),
        )


@dataclass(frozen=True)
class MatchFinding:
    """A finding indicating a rule trigger matched a line in a file."""

    rule: Rule
    file_path: str
    line_number: int
    matched_text: str
    context_line: str
