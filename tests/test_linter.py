from __future__ import annotations

import tempfile
from pathlib import Path

from daimonion.cli import format_findings, main
from daimonion.engine import Linter
from daimonion.rules import VENDORED_CHECKS, load_rules_from_checks_dir


def test_default_rules_loaded():
    """Default linter loads one rule per vendored check spec."""
    linter = Linter()
    assert len(linter.rules) == len(load_rules_from_checks_dir(Path(str(VENDORED_CHECKS))))
    rule_ids = {r.id for r in linter.rules}
    assert "crypto/deprecated-algorithms-prohibited" in rule_ids
    assert "licensing/no-copyleft-contamination" in rule_ids
    assert "privacy/cleartext-pii-logging-prohibited" in rule_ids
    # All builtins are keyword matchers: capped at L1, so --strict never fails on them.
    assert {r.kind for r in linter.rules} == {"keyword"}
    assert {r.enforcement for r in linter.rules} <= {"L0", "L1"}


def test_scan_text_detects_triggers():
    """Text matching triggers generates findings."""
    linter = Linter()
    code = """
import hashlib

def hash_password(pwd):
    # Using md5 for password
    return hashlib.md5(pwd.encode()).hexdigest()
"""
    findings = linter.scan_text(code, file_path="auth.py")
    assert len(findings) >= 1
    crypto_hits = [f for f in findings if f.rule.id == "crypto/deprecated-algorithms-prohibited"]
    hit = crypto_hits[0]
    assert hit.file_path == "auth.py"
    assert "md5" in hit.matched_text.lower()


def test_scan_file_and_format():
    """Scanning a temporary file produces clear formatted findings."""
    linter = Linter()
    with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=False) as f:
        f.write("user_data = {'email': 'user@example.com', 'ip': '127.0.0.1'}\n")
        f.flush()
        f_path = Path(f.name)

    try:
        findings = linter.scan_file(f_path)
        assert len(findings) >= 1
        output = format_findings(findings)
        assert "daimonion: Detected" in output
        assert "no cleartext pii logging" in output
    finally:
        f_path.unlink()


def test_cli_list_rules(capsys):
    """daimonion scan --list-rules outputs the active rules."""
    rc = main(["scan", "--list-rules"])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "Active compliance rules" in captured
    assert "licensing/no-copyleft-contamination" in captured


def test_cli_check_clean_file(capsys):
    """daimonion check on clean code outputs no findings."""
    with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=False) as f:
        f.write("def add(a: int, b: int) -> int:\n    return a + b\n")
        f.flush()
        f_path = Path(f.name)

    try:
        rc = main(["scan", str(f_path)])
        assert rc == 0
        captured = capsys.readouterr().out
        assert "No legal or compliance triggers matched" in captured
    finally:
        f_path.unlink()


def test_cli_strict_mode_exit_code(tmp_path):
    """--strict exits with 1 when a structural L2 rule is triggered."""
    import yaml

    rules = tmp_path / "rules.yml"
    rules.write_text(
        yaml.safe_dump(
            {
                "rules": [
                    {
                        "id": "md5-call",
                        "title": "t",
                        "triggers": r"hashlib\.md5\(",
                        "summary": "s",
                        "enforcement": "L2",
                        "kind": "structural",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    target = tmp_path / "app.py"
    target.write_text("import hashlib\nh = hashlib.md5(b'data')\n", encoding="utf-8")
    assert main(["--rules", str(rules), "--strict", "scan", str(target)]) == 1


def _write_answers(tmp_path: Path, answers: dict) -> Path:
    import yaml

    answers_file = tmp_path / ".copier-answers.yml"
    answers_file.write_text(yaml.safe_dump(answers, allow_unicode=True), encoding="utf-8")
    return answers_file


def _write_config(tmp_path: Path, when: list[str]) -> Path:
    import yaml

    config = tmp_path / ".daimonion.yml"
    config.write_text(yaml.safe_dump({"version": 1, "when": when}, allow_unicode=True), encoding="utf-8")
    return config


def test_config_does_not_scope_builtin_scan(tmp_path, capsys):
    """Builtin rules carry no gates, so `scan` runs all of them whatever `when` says.

    Scoping lives in `agents-md`, which renders only the matching sections;
    `scan` is the cheap keyword net over everything. A config therefore
    announces no scoping.
    """
    _write_config(tmp_path, ["web_api", "personal_data", "commercial"])
    assert main(["scan", "--list-rules", "--repo", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "privacy/external-transmission-declared" in out
    assert "accessibility/european-accessibility-act" in out
    assert "security/sbom-present" in out
    assert "privacy/cleartext-pii-logging-prohibited" in out
    assert "copyright/tdm-optout-respected" in out


def test_init_converts_answers_to_when_config(tmp_path, capsys):
    """`init` reads .copier-answers.yml once and writes the converted conditions."""
    _write_answers(tmp_path, {"project_type": "cli", "include_scraping": True})
    assert main(["init", "--repo", str(tmp_path), "--write"]) == 0
    capsys.readouterr()
    from daimonion.config import load_config

    assert load_config(tmp_path / ".daimonion.yml").when == ("cli", "scraping")


def test_init_without_answers_still_suggests(tmp_path, capsys):
    assert main(["init", "--repo", str(tmp_path)]) == 0
    assert "version: 1" in capsys.readouterr().out


def test_diff_does_not_announce_scope(tmp_path, capsys):
    """Builtin scan runs everything, so no scope note is printed."""
    _write_config(tmp_path, ["cli"])
    (tmp_path / "x.py").write_text("print('hi')\n")
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    rc = main(["scan", "--repo", str(tmp_path)])
    err = capsys.readouterr().err
    assert "Scoped to" not in err
    assert rc == 0


def test_gate_eval_rejects_hostile_constructs():
    from daimonion.context import gate_eval

    ctx = {"project_type": "cli", "true": True}
    assert gate_eval("", ctx) is True
    assert gate_eval("project_type == 'cli'", ctx) is True
    assert gate_eval("project_type == 'web_api'", ctx) is False
    try:
        gate_eval("__import__('os').system('id')", ctx)
    except (TypeError, ValueError) as exc:
        assert "unsupported" in str(exc) or "unbound" in str(exc)
    else:
        raise AssertionError("hostile gate was not rejected")
