"""Fixture-based unit tests for tools/check_ethics_parity.py (offline).

Builds a miniature kanon MANIFEST.yml, section files, and rules.py under
``tmp_path`` and injects their paths — no kanon checkout is needed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

TOOLS_SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "check_ethics_parity.py"


def load_script():
    spec = importlib.util.spec_from_file_location("check_ethics_parity", TOOLS_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_section(
    root: Path,
    rel: str,
    *,
    section_id: str,
    keywords: list[str] | None,
    pattern: str | None = None,
    status: str = "active",
) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ""
    if keywords is not None:
        quoted = ",".join(f'"{kw}"' for kw in keywords)
        header = f"{{# ethics: id={section_id} version=0 status={status}\n   triggers=[{quoted}] #}}\n"
    triggers_line = f"> Triggers: `{pattern}`.\n" if pattern is not None else ""
    path.write_text(f"{header}# title\n\n{triggers_line}\nbody\n", encoding="utf-8")


def _write_project(
    root: Path,
    *,
    sections: list[dict],
    rules: list[dict],
) -> tuple[Path, Path]:
    manifest_path = root / "MANIFEST.yml"
    manifest_path.write_text(yaml.safe_dump({"sections": sections}), encoding="utf-8")
    rules_path = root / "rules.py"
    rules_path.write_text(f"DEFAULT_RULES = {rules!r}\n", encoding="utf-8")
    return manifest_path, rules_path


def _run(module, manifest: Path, rules: Path, capsys) -> tuple[int, str]:
    rc = module.main(["--manifest", str(manifest), "--rules", str(rules)])
    return rc, capsys.readouterr().out


def test_happy_path(tmp_path, capsys):
    """A mapped pair with covered keywords, identical regexes, equal gates passes."""
    module = load_script()
    _write_section(
        tmp_path,
        "ethics/a.md",
        section_id="baseline-license-drift",
        keywords=["license", "gpl"],
        pattern=r"(?i)\b(license|gpl)\b",
    )
    manifest, rules = _write_project(
        tmp_path,
        sections=[{"id": "baseline-license-drift", "file": "ethics/a.md", "when": "always"}],
        rules=[{"id": "licensing-drift", "triggers": r"(?i)\b(license|gpl)\b", "gate": "true"}],
    )
    rc, out = _run(module, manifest, rules, capsys)
    assert rc == 0, out
    assert "OK   baseline-license-drift -> licensing-drift" in out


def test_unmapped_active_section_fails(tmp_path, capsys):
    """A new active section with no mapping and no acknowledgement fails."""
    module = load_script()
    _write_section(tmp_path, "ethics/new.md", section_id="x-brand-new", keywords=["zzz"], pattern=None)
    manifest, rules = _write_project(
        tmp_path,
        sections=[{"id": "x-brand-new", "file": "ethics/new.md", "when": "always"}],
        rules=[],
    )
    rc, out = _run(module, manifest, rules, capsys)
    assert rc == 1
    assert "FAIL x-brand-new: active section has no daimonion rule" in out


def test_uncovered_keyword_fails(tmp_path, capsys):
    """A mapped pair whose header keywords never match the rule regex fails."""
    module = load_script()
    _write_section(
        tmp_path,
        "ethics/b.md",
        section_id="domain-llm-appsec",
        keywords=["zzz-nope", "yyy-nada"],
        pattern=None,
    )
    manifest, rules = _write_project(
        tmp_path,
        sections=[{"id": "domain-llm-appsec", "file": "ethics/b.md", "when": "mcp"}],
        rules=[{"id": "llm-appsec", "triggers": r"(?i)\b(llm|mcp)\b", "gate": "mcp_effective"}],
    )
    rc, out = _run(module, manifest, rules, capsys)
    assert rc == 1
    assert "none of 2 header keywords match" in out


def test_divergent_file_regex_fails(tmp_path, capsys):
    """A file regex sharing fewer than 3 probes with the rule regex fails."""
    module = load_script()
    _write_section(
        tmp_path,
        "ethics/c.md",
        section_id="region-eu-cra",
        keywords=["zzz-nope"],
        pattern=r"(?i)\b(zzz|yyy|qqq|www)\b",
    )
    manifest, rules = _write_project(
        tmp_path,
        sections=[{"id": "region-eu-cra", "file": "ethics/c.md", "when": "commercial"}],
        rules=[
            {
                "id": "eu-cra-compliance",
                "triggers": r"(?i)\b(aaa|bbb|ccc|ddd)\b",
                "gate": "'commercial' in distribution",
            }
        ],
    )
    rc, out = _run(module, manifest, rules, capsys)
    assert rc == 1
    assert "need >= 3" in out


def test_gate_drift_fails(tmp_path, capsys):
    """A conditional kanon section mapped to an ungated rule fails."""
    module = load_script()
    _write_section(
        tmp_path,
        "ethics/d.md",
        section_id="domain-llm-appsec",
        keywords=["llm"],
        pattern=r"(?i)\b(llm|mcp)\b",
    )
    manifest, rules = _write_project(
        tmp_path,
        sections=[{"id": "domain-llm-appsec", "file": "ethics/d.md", "when": "mcp"}],
        rules=[{"id": "llm-appsec", "triggers": r"(?i)\b(llm|mcp)\b", "gate": ""}],
    )
    rc, out = _run(module, manifest, rules, capsys)
    assert rc == 1
    assert "kanon when mcp but the rule is ungated" in out


def test_draft_unmapped_passes(tmp_path, capsys):
    """A draft section with no same-named rule is skipped with a note."""
    module = load_script()
    _write_section(tmp_path, "ethics/e.md", section_id="x-draft-thing", keywords=["zzz"], pattern=None, status="draft")
    manifest, rules = _write_project(
        tmp_path,
        sections=[{"id": "x-draft-thing", "file": "ethics/e.md", "when": "always"}],
        rules=[],
    )
    rc, out = _run(module, manifest, rules, capsys)
    assert rc == 0, out
    assert "NOTE x-draft-thing: draft without a rule; skipped" in out


def test_ungateable_condition_is_a_note(tmp_path, capsys):
    """A `when` copier answers cannot express (jp) leaves the rule ungated with a note."""
    module = load_script()
    _write_section(
        tmp_path,
        "ethics/f.md",
        section_id="region-kyushu-ntp",
        keywords=["133.100.9.2"],
        pattern=r"(?i)\b(133\.100\.9\.2)\b",
    )
    manifest, rules = _write_project(
        tmp_path,
        sections=[{"id": "region-kyushu-ntp", "file": "ethics/f.md", "when": "jp"}],
        rules=[{"id": "kyushu-ntp-hygiene", "triggers": r"(?i)\b(133\.100\.9\.2)\b", "gate": ""}],
    )
    rc, out = _run(module, manifest, rules, capsys)
    assert rc == 0, out
    assert "has no .copier-answers.yml equivalent" in out


def test_vendored_snapshot_is_in_parity(capsys):
    """The bundled kanon snapshot and DEFAULT_RULES agree (the default inputs)."""
    module = load_script()
    rc = module.main([])
    out = capsys.readouterr().out
    assert rc == 0, out
