from __future__ import annotations

import re
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from daimonion.models import Rule

#: The vendored check specs this module builds the default rule set from:
#: ``rulebook/checks/`` (law-map ``checks/`` at the ``LAWMAP_SHA`` pin).
#: Every spec carries ``id`` (``domain/slug``), ``obligation``, ``level``,
#: and a ``triggers`` list of regex strings. Specs that grow a structural
#: ``kind`` (AST/semgrep/dep/license) keep their L2; plain ``keyword``
#: specs are reminders capped at L1 — see ``models.effective_enforcement``.
VENDORED_CHECKS = files("daimonion") / "rulebook" / "checks"


def _english_title(obligation: str, spec_id: str) -> str:
    """The obligation id's trailing slug as a title fallback (no spec carries titles)."""
    slug = obligation.rsplit(".", 1)[-1] if obligation else spec_id
    return slug.replace("-", " ").replace("_", " ")


def _english_summary(spec: Mapping[str, Any]) -> str:
    """One-line English summary from the spec's ``acceptance``/``fail_when``/obligation."""
    acceptance = spec.get("acceptance")
    if isinstance(acceptance, str) and acceptance.strip():
        first = re.split(r"[.\n]", " ".join(acceptance.split()), maxsplit=1)[0].strip()
        if first:
            return first + "."
    fail_when = spec.get("fail_when")
    items = (
        [item for item in fail_when if isinstance(item, str) and item.strip()] if isinstance(fail_when, list) else []
    )
    if items:
        return "Fails when: " + " ".join(items[0].split())
    obligation = spec.get("obligation")
    if isinstance(obligation, str) and obligation:
        return f"Check for {obligation} (see the linked rulebook section for details)."
    return ""


def _check_spec_triggers(spec: Mapping[str, Any]) -> str:
    """Join a check spec's ``triggers`` list into one alternation for the engine."""
    triggers = spec.get("triggers", [])
    if isinstance(triggers, str):
        return triggers
    if isinstance(triggers, list):
        # Join bare with ``|`` (no wrapping group): wrapping a pattern
        # like ``(?i)\\b...`` in ``(?:...)`` moves the global flag off
        # the start of the expression, which ``re`` rejects.
        joined = "|".join(item for item in triggers if isinstance(item, str) and item)
        return joined if joined else "(?!)"
    return "(?!)"


def rule_from_check_spec(spec: Mapping[str, Any]) -> Rule:
    """Build a rule from a law-map ``checks/<domain>/<slug>.yml`` spec.

    A spec carries ``id`` (``domain/slug``), ``obligation``, ``level``,
    and an optional ``triggers`` list of regex strings; the rule joins
    the list into one alternation so the engine's single-pattern match
    applies. Specs without ``triggers`` map to ``(?!)`` — a pattern
    that matches nothing — so the gate they describe still shows in
    ``list-rules`` but can never fire on scanned text.
    """
    spec_id = str(spec.get("id", ""))
    obligation = spec.get("obligation", "")
    obligation = obligation if isinstance(obligation, str) else ""
    category = spec_id.split("/")[0] or "general"
    return Rule(
        id=spec_id,
        title=_english_title(obligation, spec_id),
        triggers=_check_spec_triggers(spec),
        summary=_english_summary(spec),
        category=category,
        enforcement=str(spec.get("level", "L1")),
        gate="",
        kind=str(spec.get("kind", "keyword")),
    )


def _iter_check_spec_files(checks_root: Path) -> list[Path]:
    return sorted(p for p in checks_root.rglob("*.yml") if not p.name.startswith("_"))


def load_rules_from_checks_dir(checks_root: str | Path) -> list[Rule]:
    """Load one rule per law-map check spec under ``checks_root`` (recursive)."""
    root = checks_root if isinstance(checks_root, Path) else Path(checks_root)
    if not root.is_dir():
        try:
            root = Path(str(files("daimonion") / "rulebook" / "checks" / str(checks_root)))
        except (TypeError, ValueError):
            pass
    rules: list[Rule] = []
    for spec_file in _iter_check_spec_files(root):
        try:
            data = yaml.safe_load(spec_file.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict):
            continue
        rules.append(rule_from_check_spec(data))
    return rules


def _enrich_from_section_file(item: dict[str, Any], yaml_path: Path) -> None:
    """Fill a file-referencing entry with triggers/title/summary from its section file.

    Kept for custom ``--rules`` YAML files whose entries point at section
    files via ``file:``. The section file is Markdown with YAML front
    matter; triggers come from the front matter, the title from the ``en:``
    title (falling back to the prose h1), and the summary from the first
    ``en:`` summary line (falling back to the ``why`` field).
    """
    if "file" not in item or item.get("triggers"):
        return
    file_rel = str(item["file"])
    candidates = (
        yaml_path.parent / file_rel,
        yaml_path.parent.parent / file_rel,
        yaml_path.parent.parent.parent / file_rel,
    )
    sec_file = next((c for c in candidates if c.is_file()), None)
    if sec_file is None:
        return
    sec_text = sec_file.read_text(encoding="utf-8")
    front: dict[str, Any] = {}
    if sec_text.startswith("---\n"):
        head, sep, _ = sec_text[len("---\n") :].partition("\n---\n")
        if sep:
            try:
                front = yaml.safe_load(head) or {}
            except yaml.YAMLError:
                front = {}
    triggers = front.get("triggers", {})
    pattern = triggers.get("pattern") if isinstance(triggers, dict) else None
    en = front.get("en", {})
    en_title = en.get("title") if isinstance(en, dict) else None
    en_summary = en.get("summary") if isinstance(en, dict) else None
    title = re.search(r"^# (.+)$", sec_text, re.MULTILINE)
    item["triggers"] = pattern.strip() if isinstance(pattern, str) else ""
    item["title"] = (
        en_title.strip()
        if isinstance(en_title, str) and en_title.strip()
        else (title.group(1).strip() if title else item.get("id", ""))
    )
    item["summary"] = (
        str(en_summary[0]).strip()
        if isinstance(en_summary, list) and en_summary and str(en_summary[0]).strip()
        else item.get("why", "")
    )


def load_rules_from_data(data: Any, *, yaml_path: Path | None = None) -> list[Rule]:
    """Build rules from parsed YAML: a list, or a mapping holding ``sections``/``rules``."""
    if isinstance(data, Mapping):
        rules_data = data.get("sections") or data.get("rules") or data
    else:
        rules_data = data
    if not isinstance(rules_data, list):
        msg = "Expected YAML list of rules under 'sections', 'rules', or top-level"
        raise TypeError(msg)
    rules: list[Rule] = []
    for item in rules_data:
        if not isinstance(item, dict):
            continue
        if yaml_path is not None:
            _enrich_from_section_file(item, yaml_path)
        rules.append(Rule.from_dict(item))
    return rules


def load_rules_from_yaml(path: str | Path) -> list[Rule]:
    """Load rules from an external YAML file or a law-map ``checks/`` directory.

    A directory is consumed as a law-map checkout: every ``*.yml`` file
    beneath it is parsed as a check spec (``id``/``obligation``/``level``
    plus optional ``triggers``) and mapped to a rule. Files whose
    basename starts with ``_`` are skipped.
    """
    resolved = Path(path)
    if resolved.is_dir():
        return load_rules_from_checks_dir(resolved)
    data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    return load_rules_from_data(data, yaml_path=resolved)


def _builtin_rules() -> tuple[Rule, ...]:
    """The default rule set: one rule per vendored law-map check spec."""
    return tuple(load_rules_from_checks_dir(Path(str(VENDORED_CHECKS))))


#: The default rule set: one rule per vendored check spec (``rulebook/checks/``).
#: Prefer this over re-parsing; ``--rules`` replaces it outright.
BUILTIN_RULES: tuple[Rule, ...] = _builtin_rules()


__all__ = [
    "BUILTIN_RULES",
    "VENDORED_CHECKS",
    "load_rules_from_checks_dir",
    "load_rules_from_data",
    "load_rules_from_yaml",
    "rule_from_check_spec",
]
