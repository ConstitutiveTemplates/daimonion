"""Copier answers: loading them and converting them to the ``when`` vocabulary.

``daimonion init`` reads a project's ``.copier-answers.yml`` **once** and
converts the answers into ``.daimonion.yml``. After that, ``scan`` and
``agents-md`` read only ``.daimonion.yml`` — nothing reads the answers file
at scan time.

The derivation below mirrors architekton-py's
``_shared/daimonion-when.jinja`` (``daimonion_when()``): the same answers
produce the same conditions in both places, so a template-generated
``.daimonion.yml`` and one from ``daimonion init`` agree.
"""

from __future__ import annotations

import ast
import warnings
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from daimonion.models import Rule

#: A copier questionnaire may offer these project types; only some map to a
#: ``when`` condition (``script``, ``ros2``, ``online_judge`` map indirectly,
#: via ``micropython_pkg``/``oj_code``-style flags, or not at all).
PROJECT_TYPE_TO_WHEN = {"library": "library", "cli": "cli", "micropython": "embedded"}

#: Code-submission judges: single-file solutions submitted to the judge's
#: sandbox (mirrors the template's ``oj_code`` internal: atcoder, leetcode,
#: yukicoder, aoj, codeforces, kattis, other — kaggle and ctf excluded).
OJ_CODE_KINDS = ("atcoder", "leetcode", "yukicoder", "aoj", "codeforces", "kattis", "other")

#: Answers files a generated project carries at its root.
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


def _as_bool(answers: Mapping[str, Any], key: str) -> bool:
    return bool(answers.get(key))


def _combinable(answers: Mapping[str, Any]) -> bool:
    """Whether include_* layers can apply (only the layout-carrying bases compose)."""
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


def _effective_flags(answers: Mapping[str, Any]) -> dict[str, bool]:
    """The template's ``*_effective`` internals, re-evaluated from raw answers."""
    project_type = answers.get("project_type")
    combinable = _combinable(answers)
    web_api = project_type == "web_api" or (_as_bool(answers, "include_web_api") and combinable)
    data_science_layout = project_type == "data_science" or (_as_bool(answers, "include_data_science") and combinable)
    kaggle = project_type == "online_judge" and answers.get("oj_kind") == "kaggle"
    oj_code = project_type == "online_judge" and answers.get("oj_kind") in OJ_CODE_KINDS
    return {
        "web_api": web_api,
        "data_science_layout": data_science_layout,
        "kaggle": kaggle,
        "oj_code": oj_code,
        "mcp_effective": _as_bool(answers, "include_mcp") and (project_type == "cli" or web_api),
        "scraping_effective": _as_bool(answers, "include_scraping") and project_type == "cli",
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
    try:
        tree = ast.parse(gate, mode="eval")
    except SyntaxError as exc:
        msg = f"malformed gate expression: {exc.msg}"
        raise ValueError(msg) from exc
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            msg = f"unsupported gate construct: {type(node).__name__}"
            raise TypeError(msg)
        if isinstance(node, ast.Name) and node.id not in context:
            msg = f"gate names an unbound flag: {node.id}"
            raise ValueError(msg)
    return bool(eval(compile(tree, "<gate>", "eval"), {"__builtins__": {}}, dict(context)))


def scope_rules(rules: Iterable[Rule], context: Mapping[str, Any]) -> list[Rule]:
    """Return the subset of rules whose gate holds in the derived context.

    Gates that fail to evaluate (hostile construct, unbound flag, malformed
    expression) fail closed: the rule is excluded and a ``UserWarning`` names it,
    so one broken gate can neither switch itself on nor abort the whole scan.
    """
    scoped: list[Rule] = []
    for rule in rules:
        try:
            active = gate_eval(rule.gate, context)
        except (TypeError, ValueError) as exc:
            warnings.warn(
                f"daimonion: excluding rule {rule.id!r}: malformed gate {rule.gate!r} ({exc})",
                UserWarning,
                stacklevel=2,
            )
            continue
        if active:
            scoped.append(rule)
    return scoped


def derive_context(answers: Mapping[str, Any]) -> dict[str, Any]:
    """The flag set a project's copier answers imply.

    Mirrors architekton-py ``questions/_internal.yml``: the same names, the
    same conditions, so a REGISTRY gate string means one thing in both
    places. Kept for custom ``--rules`` files whose gates still speak the
    answer vocabulary; ``scan`` itself no longer derives a context.
    """
    flags = _effective_flags(answers)
    project_type = str(answers.get("project_type") or "")
    kaggle = flags["kaggle"]
    oj_ctf = project_type == "online_judge" and answers.get("oj_kind") == "ctf"
    return {
        "true": True,
        "false": False,
        "project_type": project_type,
        "oj_kind": str(answers.get("oj_kind") or ""),
        "domain_traits": _choices(answers, "domain_traits"),
        "distribution": _choices(answers, "distribution"),
        "web_api": flags["web_api"],
        "data_science_layout": flags["data_science_layout"],
        "ds_stack": flags["data_science_layout"] or kaggle,
        "mcp_effective": flags["mcp_effective"],
        "scraping_effective": flags["scraping_effective"],
        "oj_code": flags["oj_code"],
        "oj_ctf": oj_ctf,
        "agents_md_effective": True,
        "license": str(answers.get("license") or ""),
        "scraping_memorious_effective": bool(answers.get("include_scraping"))
        and project_type == "cli"
        and answers.get("scraping_engine") in ("memorious", "all"),
    }


def answers_to_when(answers: Mapping[str, Any]) -> list[str]:
    """The rulebook ``when`` conditions a copier answers file implies.

    Mirrors architekton-py's ``_shared/daimonion-when.jinja``:
    ``project_type``/``micropython_pkg``/``domain_traits`` map directly, the
    ``*_effective`` layouts map to their condition, ``kaggle`` is its own
    condition (not ``data_science``), and ``commercial`` comes from
    ``distribution``. ``always`` is never emitted (it is implied); ``jp``,
    ``eu_market`` and ``ai_assisted`` are not derivable from the
    questionnaire and stay commented hints in the rendered config.
    """
    flags = _effective_flags(answers)
    answers = dict(answers)
    when: list[str] = []

    def _add(condition: str) -> None:
        if condition not in when:
            when.append(condition)

    project_when = PROJECT_TYPE_TO_WHEN.get(str(answers.get("project_type") or ""))
    if project_when is not None:
        _add(project_when)
    if _as_bool(answers, "micropython_pkg") or str(answers.get("project_type") or "") == "micropython":
        _add("embedded")
    for trait in _choices(answers, "domain_traits"):
        _add({"personal-data": "personal_data", "face-recognition": "face_recognition"}.get(trait, trait))
    if flags["scraping_effective"]:
        _add("scraping")
    if flags["oj_code"]:
        _add("oj_code")
    if flags["mcp_effective"]:
        _add("mcp")
    if flags["data_science_layout"]:
        _add("data_science")
    if flags["kaggle"]:
        _add("kaggle")
    if flags["web_api"]:
        _add("web_api")
    if "commercial" in _choices(answers, "distribution"):
        _add("commercial")
    return when
