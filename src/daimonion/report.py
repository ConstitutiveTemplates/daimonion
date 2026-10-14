"""Machine-readable serialization of daimonion results (JSON and SARIF 2.1.0).

Both formats are plain Python structures serialized with :mod:`json`; daimonion
keeps ``pyyaml`` as its only third-party runtime dependency.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version
from typing import Any

from daimonion.models import Finding, Rule

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"

#: Enforcement tier -> SARIF result level (L2 blocking, L1 advisory, L0 informational).
ENFORCEMENT_LEVELS: dict[str, str] = {"L2": "error", "L1": "warning", "L0": "note"}

#: Level used for a missing or unrecognised enforcement tier.
DEFAULT_LEVEL = "warning"


def tool_version() -> str:
    """Installed distribution version, or a placeholder when running from a source tree."""
    try:
        return _distribution_version("daimonion")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def dumps(payload: Any) -> str:
    """Serialize a report payload as UTF-8-friendly, human-diffable JSON."""
    return json.dumps(payload, ensure_ascii=False, indent=2)


def finding_to_dict(finding: Finding) -> dict[str, Any]:
    """Flat JSON view of one finding: the shape machine consumers parse."""
    return {
        "rule_id": finding.rule.id,
        "rule_title": finding.rule.title,
        "enforcement": finding.rule.enforcement,
        "file": finding.file_path,
        "line": finding.line_number,
        "matched_text": finding.matched_text,
        "context_line": finding.context_line,
    }


def build_json_report(
    findings: Sequence[Finding],
    *,
    strict_fail: bool = False,
    suppressed: Sequence[Finding] = (),
    baselined: Sequence[Finding] = (),
) -> dict[str, Any]:
    """The ``--format json`` payload: a summary object plus the flat findings list.

    ``findings`` holds only what counts; inline-ignored and baselined findings
    are tallied in the summary.
    """
    return {
        "summary": {
            "findings": len(findings),
            "rules_matched": len({f.rule.id for f in findings}),
            "strict_fail": strict_fail,
            "suppressed": len(suppressed),
            "baselined": len(baselined),
        },
        "findings": [finding_to_dict(f) for f in findings],
    }


def build_rules_json_report(rules: Sequence[Rule]) -> dict[str, Any]:
    """The ``list-rules --format json`` payload."""
    return {
        "summary": {"rules": len(rules)},
        "rules": [rule.to_dict() for rule in rules],
    }


def _sarif_level(enforcement: str) -> str:
    return ENFORCEMENT_LEVELS.get(enforcement.strip().upper(), DEFAULT_LEVEL)


def _sarif_rule(rule: Rule) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": rule.id,
        "name": rule.id,
        "shortDescription": {"text": rule.title or rule.summary or rule.id},
        "defaultConfiguration": {"level": _sarif_level(rule.enforcement)},
        "properties": {"enforcement": rule.enforcement, "category": rule.category},
    }
    if rule.summary:
        entry["fullDescription"] = {"text": rule.summary}
    return entry


def _sarif_result(finding: Finding) -> dict[str, Any]:
    rule = finding.rule
    result: dict[str, Any] = {
        "ruleId": rule.id,
        "level": _sarif_level(rule.enforcement),
        "message": {"text": f"{rule.title or rule.id}: matched '{finding.matched_text}'"},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": finding.file_path.replace("\\", "/")},
                    "region": {"startLine": max(finding.line_number, 1)},
                }
            }
        ],
    }
    return result


def _suppressed_result(finding: Finding, *, kind: str, justification: str) -> dict[str, Any]:
    result = _sarif_result(finding)
    result["suppressions"] = [{"kind": kind, "justification": justification}]
    return result


def build_sarif_report(
    findings: Sequence[Finding],
    *,
    suppressed: Sequence[Finding] = (),
    baselined: Sequence[Finding] = (),
) -> dict[str, Any]:
    """The ``--format sarif`` payload: a SARIF 2.1.0 log holding a single run.

    ``tool.driver.rules`` lists exactly the rules that produced results, so every
    ``results[].ruleId`` resolves within the same run. Inline-ignored findings
    carry an ``inSource`` suppression and baselined ones an ``external`` one, so
    code-scanning UIs show them as dismissed rather than dropping them.
    """
    results = [_sarif_result(finding) for finding in findings]
    for finding in suppressed:
        reason = finding.suppression.reason if finding.suppression is not None else ""
        results.append(_suppressed_result(finding, kind="inSource", justification=reason))
    for finding in baselined:
        results.append(_suppressed_result(finding, kind="external", justification="daimonion baseline"))
    matched: dict[str, Rule] = {}
    for finding in (*findings, *suppressed, *baselined):
        matched.setdefault(finding.rule.id, finding.rule)
    return {
        "version": SARIF_VERSION,
        "$schema": SARIF_SCHEMA,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "daimonion",
                        "version": tool_version(),
                        "rules": [_sarif_rule(rule) for rule in matched.values()],
                    }
                },
                "results": results,
            }
        ],
    }


__all__ = [
    "DEFAULT_LEVEL",
    "ENFORCEMENT_LEVELS",
    "SARIF_SCHEMA",
    "SARIF_VERSION",
    "build_json_report",
    "build_rules_json_report",
    "build_sarif_report",
    "dumps",
    "finding_to_dict",
    "tool_version",
]
