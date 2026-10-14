from __future__ import annotations

import tempfile
from pathlib import Path

from daimonion.cli import format_findings, main
from daimonion.engine import Linter


def test_default_rules_loaded():
    """Default linter loads standard compliance rules."""
    linter = Linter()
    assert len(linter.rules) >= 10
    rule_ids = {r.id for r in linter.rules}
    assert "deprecated-crypto" in rule_ids
    assert "licensing-drift" in rule_ids
    assert "personal-data-privacy" in rule_ids


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
    crypto_hits = [f for f in findings if f.rule.id == "deprecated-crypto"]
    assert len(crypto_hits) >= 1
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
        assert "Personal data" in output
    finally:
        f_path.unlink()


def test_cli_list_rules(capsys):
    """daimonion list-rules outputs the active rules."""
    rc = main(["list-rules"])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "Active compliance rules" in captured
    assert "licensing-drift" in captured


def test_cli_check_clean_file(capsys):
    """daimonion check on clean code outputs no findings."""
    with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=False) as f:
        f.write("def add(a: int, b: int) -> int:\n    return a + b\n")
        f.flush()
        f_path = Path(f.name)

    try:
        rc = main(["check", str(f_path)])
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
    assert main(["--rules", str(rules), "--strict", "check", str(target)]) == 1


def _write_answers(tmp_path: Path, answers: dict) -> Path:
    import yaml

    answers_file = tmp_path / ".copier-answers.yml"
    answers_file.write_text(yaml.safe_dump(answers, allow_unicode=True), encoding="utf-8")
    return answers_file


def test_prepare_scopes_rules_from_copier_answers(tmp_path, capsys):
    """A web_api + commercial project gets JP transmission/EAA/CRA rules,
    while cli-scraping copyright stays gated out."""
    _write_answers(
        tmp_path,
        {
            "project_type": "web_api",
            "domain_traits": ["personal-data"],
            "distribution": ["commercial"],
            "include_mcp": True,
        },
    )
    assert main(["prepare", "--repo", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "project_type: web_api" in out
    assert "jp-external-transmission" in out
    assert "eu-eaa-accessibility" in out
    assert "eu-cra-compliance" in out
    assert "ai-copyright" in out  # in the gated-out list


def test_prepare_write_emits_rules_file(tmp_path, capsys):
    _write_answers(tmp_path, {"project_type": "cli", "include_scraping": True})
    assert main(["prepare", "--repo", str(tmp_path), "--write"]) == 0
    generated = tmp_path / ".daimonion-rules.yml"
    assert generated.is_file()
    import yaml

    rules = yaml.safe_load(generated.read_text())["rules"]
    ids = {r["id"] for r in rules}
    assert "ai-copyright" in ids  # scraping_effective -> copyright gate on
    assert "eu-eaa-accessibility" not in ids


def test_prepare_without_answers_fails_loudly(tmp_path, capsys):
    assert main(["prepare", "--repo", str(tmp_path)]) == 2
    assert "No .copier-answers.yml" in capsys.readouterr().err


def test_diff_scopes_via_copier_answers(tmp_path, capsys):
    """Without --all, a project-derived scope is announced on stderr."""
    _write_answers(tmp_path, {"project_type": "script"})
    (tmp_path / "x.py").write_text("print('hi')\n")
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    rc = main(["diff", "--repo", str(tmp_path)])
    err = capsys.readouterr().err
    assert "Scoped to" in err
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
