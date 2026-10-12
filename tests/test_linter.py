from __future__ import annotations

import tempfile
from pathlib import Path

from law_lint.cli import format_findings, main
from law_lint.engine import Linter


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
        assert "law-lint: Detected" in output
        assert "個人データ" in output
    finally:
        f_path.unlink()


def test_cli_list_rules(capsys):
    """law-lint list-rules outputs the active rules."""
    rc = main(["list-rules"])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "Active compliance rules" in captured
    assert "licensing-drift" in captured


def test_cli_check_clean_file(capsys):
    """law-lint check on clean code outputs no findings."""
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


def test_cli_strict_mode_exit_code():
    """--strict exits with 1 when L2 rules are triggered."""
    with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=False) as f:
        f.write("import hashlib\nh = hashlib.md5(b'data')\n")
        f.flush()
        f_path = Path(f.name)

    try:
        rc = main(["--strict", "check", str(f_path)])
        assert rc == 1
    finally:
        f_path.unlink()
