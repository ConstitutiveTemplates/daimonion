from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from law_lint.models import Rule

# Project types daimonion's questionnaire offers (copier.yml).
OJ_CODE_KINDS = ("atcoder", "codeforces", "kattis", "kaggle")
ANSWERS_NAMES = (".copier-answers.yml", ".copier-answers.yaml")


def find_answers_file(root: str | Path) -> Path | None:
    """Locate the copier answers file under a project root."""
    base = Path(root)
    for name in ANSWERS_NAMES:
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


def load_answers(path: str | Path) -> dict[str, Any]:
    """Parse .copier-answers.yml, tolerating the `# Changes here...` comment header."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _combinable(answers: Mapping[str, Any]) -> bool:
    """Whether include_* layers can apply (mirrors tools/ethics.py::_combinable)."""
    project_type = answers.get("project_type")
    is_kaggle = project_type == "online_judge" and answers.get("oj_kind") == "kaggle"
    return project_type in ("library", "cli", "web_api", "data_science") or is_kaggle


def _choices(answers: Mapping[str, Any], key: str) -> list[str]:
    raw = answers.get(key)
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return [str(v) for v in raw]
    return []


def derive_context(answers: Mapping[str, Any]) -> dict[str, Any]:
    """The flag set a project's copier answers imply.

    Mirrors daimonion tools/ethics.py::leaf_context: the same names, the same
    conditions, so a REGISTRY gate string means one thing in both places.
    """
    project_type = str(answers.get("project_type") or "")
    combinable = _combinable(answers)
    web_api = project_type == "web_api" or (bool(answers.get("include_web_api")) and combinable)
    data_science = project_type == "data_science" or (bool(answers.get("include_data_science")) and combinable)
    kaggle = project_type == "online_judge" and answers.get("oj_kind") == "kaggle"
    oj_ctf = project_type == "online_judge" and answers.get("oj_kind") == "ctf"
    return {
        "true": True,
        "false": False,
        "project_type": project_type,
        "oj_kind": str(answers.get("oj_kind") or ""),
        "domain_traits": _choices(answers, "domain_traits"),
        "distribution": _choices(answers, "distribution"),
        "web_api": web_api,
        "data_science_layout": data_science,
        "ds_stack": data_science or kaggle,
        "mcp_effective": bool(answers.get("include_mcp")) and (project_type == "cli" or web_api),
        "scraping_effective": bool(answers.get("include_scraping")) and project_type == "cli",
        "oj_code": project_type == "online_judge" and answers.get("oj_kind") in OJ_CODE_KINDS,
        "oj_ctf": oj_ctf,
        "agents_md_effective": True,
        "license": str(answers.get("license") or ""),
        "scraping_memorious_effective": bool(answers.get("include_scraping"))
        and project_type == "cli"
        and answers.get("scraping_engine") in ("memorious", "all"),
    }


# AST node types the gate evaluator permits. Everything else (names outside the
# allowlist, calls, attribute access, comprehensions) is rejected.
_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.In,
    ast.NotIn,
)


def gate_eval(gate: str, context: Mapping[str, Any]) -> bool:
    """Evaluate a REGISTRY gate expression against a derived context.

    Returns True when the gate is empty/missing (always-on section) or the
    expression holds. Rejects anything outside the allowlisted grammar by
    raising ValueError -- a gate that fails to parse is loud, not silently on.
    """
    gate = (gate or "").strip()
    if not gate:
        return True
    tree = ast.parse(gate, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            msg = f"unsupported gate construct: {type(node).__name__}"
            raise TypeError(msg)
        if isinstance(node, ast.Name) and node.id not in context:
            msg = f"gate names an unbound flag: {node.id}"
            raise ValueError(msg)
    return bool(eval(compile(tree, "<gate>", "eval"), {"__builtins__": {}}, dict(context)))


def scope_rules(rules: Iterable[Rule], context: Mapping[str, Any]) -> list[Rule]:
    """Return the subset of rules whose gate holds in the derived context."""
    return [rule for rule in rules if gate_eval(rule.gate, context)]


def describe_context(context: Mapping[str, Any]) -> list[str]:
    """Human-readable summary of the derived project context."""
    flags = [
        key
        for key in (
            "web_api",
            "data_science_layout",
            "ds_stack",
            "mcp_effective",
            "scraping_effective",
            "oj_code",
            "oj_ctf",
        )
        if context.get(key)
    ]
    return [
        f"project_type: {context.get('project_type') or '(unset)'}",
        f"oj_kind: {context.get('oj_kind') or '-'}",
        f"domain_traits: {', '.join(context.get('domain_traits') or []) or '-'}",
        f"distribution: {', '.join(context.get('distribution') or []) or '-'}",
        f"flags: {', '.join(flags) or '-'}",
    ]
