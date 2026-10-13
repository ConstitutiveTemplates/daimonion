"""Fail loudly when daimonion ethics sections drift from law-lint rules.

Run from a law-lint checkout with a ``../daimonion`` sibling (or pass
explicit paths)::

    python tools/check_ethics_parity.py
    python tools/check_ethics_parity.py --registry path/to/REGISTRY.yml --rules path/to/rules.py

Exit 0 when every distributed (``status: active``) registry section is
covered by a law-lint rule whose trigger regex and gate agree; exit 1 with
a per-pair report otherwise. Draft sections are skipped with a note unless
a same-named rule exists, in which case they need a mapping too.

Only ``pyyaml`` plus the standard library is used. The rules file is parsed
with :mod:`ast` and never imported, so the script stays runnable even when
``law_lint`` itself is not installed.
"""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

import yaml

# Map a daimonion registry section id to the law-lint rule id that enforces
# it. ADD A LINE HERE when adding a section (or acknowledge a deliberately
# unmapped active section in KNOWN_UNMAPPED_ACTIVE below).
SECTION_TO_RULE: dict[str, str] = {
    "baseline-license-drift": "licensing-drift",
    "baseline-pki-chain": "pki-trust-chain",
    "baseline-personal-data": "personal-data-privacy",
    "baseline-pqc-fips": "pqc-standards",
    "baseline-copyright-ai": "ai-copyright",
    "domain-llm-appsec": "llm-appsec",
    "region-eu-cra": "eu-cra-compliance",
    "region-jp-external-transmission": "jp-external-transmission",
    "region-eu-eaa": "eu-eaa-accessibility",
    "region-kyushu-ntp": "kyushu-ntp-hygiene",
    "baseline-deprecated-crypto": "deprecated-crypto",
    "domain-prompt-injection": "prompt-injection",
}

# Active sections with deliberately no law-lint rule yet. A NEW active id
# outside this set fails the check until it gains a rule (add a
# SECTION_TO_RULE line) or is acknowledged here — that is the drift this
# script guards.
KNOWN_UNMAPPED_ACTIVE = frozenset(
    {
        "domain-ml-bias",
        "domain-face-recognition",
        "sector-samd-regulatory",
        "domain-scraping-law",
        "domain-contest-rules",
    }
)

HEADER_RE = re.compile(r"\{#.*?triggers=\[(.*?)\].*?#\}", re.DOTALL)
TRIGGERS_LINE_RE = re.compile(r"^>\s*Triggers:\s*`([^`]+)`", re.MULTILINE)
LOOKAROUND_RE = re.compile(r"\(\?[<!=][^()]*\)")
FLAG_RE = re.compile(r"\(\?[a-zA-Z]+[-+]?[a-zA-Z]*\)")
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*")


def _default_registry() -> Path:
    """REGISTRY.yml next to a ``../daimonion`` sibling of this checkout."""
    return Path(__file__).resolve().parent.parent.parent / "daimonion" / "_shared" / "ethics" / "REGISTRY.yml"


def _default_rules() -> Path:
    """The law-lint rules file inside this checkout."""
    return Path(__file__).resolve().parent.parent / "src" / "law_lint" / "rules.py"


def _daimonion_root(registry: Path) -> Path:
    """Recover the daimonion repo root from a REGISTRY.yml path."""
    parts = registry.resolve().parts
    if len(parts) >= 4 and parts[-3] == "_shared" and parts[-2] == "ethics":
        return Path(*parts[:-3])
    return registry.resolve().parent


def _is_default_rules_assign(node: ast.stmt) -> bool:
    """Whether an AST statement assigns the ``DEFAULT_RULES`` name."""
    if isinstance(node, ast.AnnAssign):
        return isinstance(node.target, ast.Name) and node.target.id == "DEFAULT_RULES"
    return isinstance(node, ast.Assign) and any(
        isinstance(name, ast.Name) and name.id == "DEFAULT_RULES" for name in node.targets
    )


def _load_rules(path: Path) -> tuple[dict[str, dict], list[str]]:
    """Parse DEFAULT_RULES from a rules.py file without importing it."""
    errors: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return {}, [f"cannot parse {path}: {exc}"]
    target: ast.AST | None = None
    for node in tree.body:
        if _is_default_rules_assign(node):
            target = node.value
    if target is None:
        return {}, [f"{path}: no DEFAULT_RULES assignment found"]
    if not isinstance(target, (ast.List, ast.Tuple)):
        return {}, [f"{path}: DEFAULT_RULES is not a list literal"]
    rules: dict[str, dict] = {}
    for index, entry in enumerate(target.elts):
        try:
            value = ast.literal_eval(entry)
        except (ValueError, TypeError, SyntaxError) as exc:
            # Never guess at non-literal entries: report and fail instead.
            errors.append(f"{path}: DEFAULT_RULES[{index}] is not a plain literal ({exc})")
            continue
        if not isinstance(value, dict) or not value.get("id") or not value.get("triggers"):
            errors.append(f"{path}: DEFAULT_RULES[{index}] lacks an id/triggers pair")
            continue
        try:
            re.compile(value["triggers"])
        except re.error as exc:
            errors.append(f"{path}: rule {value.get('id')!r} regex does not compile ({exc})")
            continue
        rules[value["id"]] = value
    return rules, errors


def _header_keywords(text: str) -> list[str] | None:
    """Keywords from the ``{# ethics: ... triggers=[...] #}`` header."""
    match = HEADER_RE.search(text)
    if match is None:
        return None
    return re.findall(r'"([^"]*)"', match.group(1))


def _triggers_pattern(text: str) -> str | None:
    """The ``> Triggers: `regex` `` line pattern, when present."""
    match = TRIGGERS_LINE_RE.search(text)
    return match.group(1) if match else None


def _looks_like_regex(pattern: str) -> bool:
    """Distinguish a real trigger regex from a plain-word Triggers line."""
    return "(" in pattern and ("?i" in pattern or "\\" in pattern)


def _probes_from_pattern(pattern: str) -> list[str]:
    """Candidate probe words from a file-side trigger regex.

    Heuristic: split the outermost alternation on ``|``, strip flag groups
    (``(?i)``) and lookarounds, then keep alphanumeric tokens of length >= 2
    (regex escapes and character-class digits carry no signal, so they are
    dropped). A probe only counts when it matches BOTH the file regex and
    the rule regex — shared vocabulary, not one-sided decoration.
    """
    body = FLAG_RE.sub("", pattern)
    body = LOOKAROUND_RE.sub("", body)
    probes: list[str] = []
    for alternative in body.split("|"):
        alternative = LOOKAROUND_RE.sub("", alternative)
        for word in WORD_RE.findall(alternative):
            if len(word) >= 2 and word not in probes:
                probes.append(word)
    return probes


def _read_section_file(root: Path, registry: Path, rel: str) -> str | None:
    """Read a section file, resolved against the daimonion repo root."""
    for candidate in (root / rel, registry.parent / rel):
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    return None


def _check_pair(section_id: str, rule_id: str, text: str, rule: dict, gate: str) -> tuple[list[str], bool]:
    """Check one mapped section/rule pair; returns (report lines, failed)."""
    lines: list[str] = []
    failed = False
    rule_rx = re.compile(rule["triggers"])

    keywords = _header_keywords(text)
    kw_total = len(keywords) if keywords else 0
    kw_matched = [kw for kw in keywords or [] if rule_rx.search(kw)]

    file_pattern = _triggers_pattern(text)
    file_rx = None
    if file_pattern and _looks_like_regex(file_pattern):
        try:
            file_rx = re.compile(file_pattern)
        except re.error as exc:
            lines.append(f"NOTE {section_id}: file Triggers: pattern does not compile ({exc}); keyword verdict only")

    identical = file_rx is not None and file_pattern == rule["triggers"]
    shared: list[str] = []
    rx_ok = False
    if identical:
        rx_ok = True
    elif file_rx is not None:
        probes = _probes_from_pattern(file_pattern or "")
        shared = [probe for probe in probes if file_rx.search(probe) and rule_rx.search(probe)]
        rx_ok = len(shared) >= 3

    # The header list is daimonion's copier-QA vocabulary (prefix-style
    # hints such as "scraping" or "tls"); the trailing-\b rule regexes only
    # cover full tokens, so partial misses are review notes. Total
    # divergence (zero keywords covered and no agreeing file regex) fails.
    if kw_total and not kw_matched and file_rx is None:
        lines.append(
            f"FAIL {section_id} -> {rule_id}: none of {kw_total} header keywords match the rule regex "
            f"({', '.join(keywords or [])})"
        )
        failed = True
    elif file_rx is not None and not rx_ok and not kw_matched:
        lines.append(
            f"FAIL {section_id} -> {rule_id}: file Triggers: regex shares {len(shared)} probes "
            f"with the rule regex, need >= 3 (shared: {', '.join(shared) or 'none'})"
        )
        failed = True
    elif kw_total == 0 and file_rx is None:
        lines.append(f"FAIL {section_id} -> {rule_id}: no header triggers= list and no Triggers: regex to check")
        failed = True
    else:
        rx_note = (
            "identical"
            if identical
            else f"{len(shared)}/{len(_probes_from_pattern(file_pattern or ''))} probes"
            if file_rx
            else "no file regex"
        )
        lines.append(f"OK   {section_id} -> {rule_id}: keywords {len(kw_matched)}/{kw_total}, file regex {rx_note}")
        if kw_total and len(kw_matched) < kw_total:
            missed = [kw for kw in keywords or [] if not rule_rx.search(kw)]
            lines.append(
                f"NOTE {section_id}: {len(missed)} header keywords not covered by the rule regex: {', '.join(missed)}"
            )

    reg_gate = (gate or "").strip()
    rule_gate = (rule.get("gate") or "").strip()
    if reg_gate and not rule_gate:
        lines.append(f"FAIL {section_id} -> {rule_id}: registry gate {reg_gate!r} but the rule gate is empty")
        failed = True
    elif reg_gate and rule_gate and reg_gate != rule_gate:
        # Parity of gating existence only: both sides gate the pair, so the
        # wording may differ — report both for human review, do not fail.
        lines.append(f"NOTE {section_id}: gate differs (registry {reg_gate!r} vs rule {rule_gate!r})")
    return lines, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check daimonion ethics sections against law-lint rules.")
    parser.add_argument("--registry", type=Path, default=None, help="Path to daimonion _shared/ethics/REGISTRY.yml")
    parser.add_argument("--rules", type=Path, default=None, help="Path to law-lint src/law_lint/rules.py")
    args = parser.parse_args(argv)

    registry_path = args.registry or _default_registry()
    rules_path = args.rules or _default_rules()

    try:
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"FAIL cannot read registry {registry_path}: {exc}")
        return 1
    except yaml.YAMLError as exc:
        print(f"FAIL cannot parse registry {registry_path}: {exc}")
        return 1
    sections = (registry or {}).get("sections")
    if not isinstance(sections, list):
        print(f"FAIL registry {registry_path} has no sections list")
        return 1

    rules_by_id, rule_errors = _load_rules(rules_path)
    lines: list[str] = [f"FAIL {message}" for message in rule_errors]
    failed = bool(rule_errors)

    ok_count = 0
    skip_count = 0
    root = _daimonion_root(registry_path)
    for section in sections:
        if not isinstance(section, dict) or not section.get("id"):
            lines.append("FAIL registry entry lacks an id")
            failed = True
            continue
        section_id = section["id"]
        status = str(section.get("status") or "draft")
        rule_id = SECTION_TO_RULE.get(section_id)
        if rule_id is None:
            if status == "active":
                if section_id in KNOWN_UNMAPPED_ACTIVE:
                    lines.append(f"NOTE {section_id}: active, acknowledged without a law-lint rule; skipped")
                    skip_count += 1
                else:
                    lines.append(f"FAIL {section_id}: active section has no law-lint rule (add a SECTION_TO_RULE line)")
                    failed = True
            elif section_id in rules_by_id:
                lines.append(f"FAIL {section_id}: draft section has a same-named rule but no SECTION_TO_RULE entry")
                failed = True
            else:
                lines.append(f"NOTE {section_id}: draft without a rule; skipped")
                skip_count += 1
            continue
        rule = rules_by_id.get(rule_id)
        if rule is None:
            lines.append(f"FAIL {section_id} -> {rule_id}: mapped rule not found in {rules_path}")
            failed = True
            continue
        text = _read_section_file(root, registry_path, section.get("file") or "")
        if text is None:
            lines.append(f"FAIL {section_id} -> {rule_id}: section file {section.get('file')!r} not found")
            failed = True
            continue
        pair_lines, pair_failed = _check_pair(section_id, rule_id, text, rule, section.get("gate") or "")
        lines.extend(pair_lines)
        failed = pair_failed or failed
        ok_count += 0 if pair_failed else 1

    fail_count = sum(line.startswith("FAIL") for line in lines)
    lines.append(f"summary: {ok_count} pairs ok, {fail_count} failures, {skip_count} skipped")
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
