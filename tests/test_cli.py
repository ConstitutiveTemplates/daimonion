"""CLI integration tests: formats, exit codes, prepared-rule auto-loading, edge cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from daimonion.cli import main
from daimonion.models import Finding, Rule


def _write_answers(root: Path, answers: dict) -> Path:
    answers_file = root / ".copier-answers.yml"
    answers_file.write_text(yaml.safe_dump(answers, allow_unicode=True), encoding="utf-8")
    return answers_file


def _structural_rules(root: Path) -> Path:
    """A rule file with one structural L2 rule and one keyword rule declared L2 (capped to L1)."""
    rules_file = root / "rules.yml"
    rules_file.write_text(
        yaml.safe_dump(
            {
                "rules": [
                    {
                        "id": "md5-call",
                        "title": "hashlib.md5() call",
                        "triggers": r"hashlib\.md5\(",
                        "summary": "s",
                        "enforcement": "L2",
                        "kind": "structural",
                    },
                    {"id": "md5-word", "title": "md5", "triggers": "(?i)md5", "summary": "s", "enforcement": "L2"},
                ]
            }
        ),
        encoding="utf-8",
    )
    return rules_file


def _json_output(capsys, argv: list[str]) -> tuple[int, dict]:
    """Run the CLI and parse stdout as JSON (stderr notices stay out of the way)."""
    rc = main(argv)
    return rc, json.loads(capsys.readouterr().out)


def test_default_format_is_human_and_unchanged(tmp_path, capsys):
    target = tmp_path / "auth.py"
    target.write_text("import hashlib\nreturn hashlib.md5(pwd)\n", encoding="utf-8")
    assert main(["scan", str(target), "--all"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("⚠️  daimonion: Detected")
    assert "[L1]" in out
    assert "crypto/deprecated-algorithms-prohibited" in out
    assert not out.lstrip().startswith("{")


def test_default_format_clean_file(tmp_path, capsys):
    target = tmp_path / "clean.py"
    target.write_text("value = compute()\n", encoding="utf-8")
    assert main(["scan", str(target), "--all"]) == 0
    assert capsys.readouterr().out.strip() == "✨ No legal or compliance triggers matched."


def test_init_converts_answers_then_scan_runs_all_builtins(tmp_path, capsys):
    """`init` converts .copier-answers.yml into .daimonion.yml; `scan` runs every builtin.

    Builtin rules carry no gates (check specs cannot name `when`), so the
    config does not scope the scan: scoping lives in `agents-md`.
    """
    _write_answers(tmp_path, {"project_type": "cli", "include_scraping": True})
    target = tmp_path / "app.py"
    target.write_text("import hashlib\nhashlib.md5(b'x')\ncookie = True\n", encoding="utf-8")

    assert main(["init", "--repo", str(tmp_path), "--write"]) == 0
    capsys.readouterr()
    config = tmp_path / ".daimonion.yml"
    assert config.is_file()

    # Remove the answers file: only the converted config remains.
    (tmp_path / ".copier-answers.yml").unlink()

    rc, payload = _json_output(capsys, ["scan", str(target), "--repo", str(tmp_path), "--format", "json"])
    ids = {finding["rule_id"] for finding in payload["findings"]}
    assert rc == 0
    assert "crypto/deprecated-algorithms-prohibited" in ids
    assert "privacy/external-transmission-declared" in ids


def test_strict_exit_codes(tmp_path, capsys):
    rules = str(_structural_rules(tmp_path))
    l2_target = tmp_path / "l2.py"
    l2_target.write_text("hashlib.md5(b'x')\n", encoding="utf-8")
    l1_target = tmp_path / "l1.py"
    l1_target.write_text("digest_name = 'md5'\n", encoding="utf-8")

    assert main(["--rules", rules, "--strict", "scan", str(l2_target), "--all"]) == 1
    capsys.readouterr()

    # The keyword rule declared L2 is capped to L1, so it never fails --strict.
    assert main(["--rules", rules, "--strict", "scan", str(l1_target), "--all"]) == 0
    assert "[L1] md5 (md5-word)" in capsys.readouterr().out

    # Without --strict even an L2 hit exits 0.
    assert main(["--rules", rules, "scan", str(l2_target), "--all"]) == 0


def test_builtin_rules_never_fail_strict(tmp_path, capsys):
    """Every builtin is a keyword reminder: at most L1, so --strict passes."""
    from daimonion.rules import BUILTIN_RULES

    assert {rule.kind for rule in BUILTIN_RULES} == {"keyword"}
    assert {rule.enforcement for rule in BUILTIN_RULES} <= {"L0", "L1"}
    target = tmp_path / "app.py"
    target.write_text("import hashlib, requests\nhashlib.md5(b'x')\nagent = 'ua'\n", encoding="utf-8")
    assert main(["--strict", "scan", str(target), "--all"]) == 0


def test_list_rules_config_and_all_agree(tmp_path, capsys):
    """Builtin rules are ungated: the config and --all list the same set."""
    (tmp_path / ".daimonion.yml").write_text("version: 1\nwhen: [cli]\n", encoding="utf-8")

    assert main(["scan", "--list-rules", "--repo", str(tmp_path)]) == 0
    scoped = capsys.readouterr().out
    assert "copyright/tdm-optout-respected" in scoped
    assert "accessibility/european-accessibility-act" in scoped

    assert main(["scan", "--list-rules", "--repo", str(tmp_path), "--all"]) == 0
    every = capsys.readouterr().out
    assert every == scoped


def test_list_rules_json(tmp_path, capsys):
    (tmp_path / ".daimonion.yml").write_text("version: 1\nwhen: [cli]\n", encoding="utf-8")
    rc, payload = _json_output(capsys, ["scan", "--list-rules", "--repo", str(tmp_path), "--list-format", "json"])
    assert rc == 0
    ids = {rule["id"] for rule in payload["rules"]}
    assert payload["summary"]["rules"] == len(payload["rules"])
    assert "copyright/tdm-optout-respected" in ids
    assert "accessibility/european-accessibility-act" in ids
    assert {"id", "title", "triggers", "summary", "enforcement"} <= set(payload["rules"][0])


def test_custom_rules_file_gates_still_scope(tmp_path, capsys):
    """With `--rules`, a gated custom file is scoped through `for_when`; ungated rules run."""
    rules_file = tmp_path / "rules.yml"
    rules_file.write_text(
        yaml.safe_dump(
            {
                "rules": [
                    {"id": "good-rule", "title": "Good", "triggers": "good", "summary": "s", "gate": ""},
                    {
                        "id": "web-rule",
                        "title": "Web",
                        "triggers": "webthing",
                        "summary": "s",
                        "gate": "web_api",
                    },
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (tmp_path / ".daimonion.yml").write_text("version: 1\nwhen: []\n", encoding="utf-8")
    target = tmp_path / "app.py"
    target.write_text("a good line with webthing\n", encoding="utf-8")

    assert main(["--rules", str(rules_file), "scan", str(target), "--repo", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "good-rule" in out
    assert "web-rule" not in out


def test_list_rules_rejects_sarif_list_format():
    with pytest.raises(SystemExit) as excinfo:
        main(["scan", "--list-rules", "--list-format", "sarif"])
    assert excinfo.value.code == 2


def test_check_json_payload(tmp_path, capsys):
    target = tmp_path / "auth.py"
    target.write_text("import hashlib\nreturn hashlib.md5(pwd)\n", encoding="utf-8")

    rules = str(_structural_rules(tmp_path))
    rc, payload = _json_output(capsys, ["--rules", rules, "--strict", "scan", str(target), "--format", "json", "--all"])
    assert rc == 1
    assert payload["summary"]["findings"] == len(payload["findings"]) >= 1
    assert payload["summary"]["rules_matched"] == len({f["rule_id"] for f in payload["findings"]})
    assert payload["summary"]["strict_fail"] is True

    hit = next(f for f in payload["findings"] if f["rule_id"] == "md5-call")
    assert set(hit) == {
        "rule_id",
        "rule_title",
        "enforcement",
        "file",
        "line",
        "matched_text",
        "context_line",
    }
    assert hit["enforcement"] == "L2"
    assert hit["file"] == str(target)
    assert hit["line"] == 2
    assert "md5" in hit["matched_text"].lower()
    assert hit["rule_title"]


def test_check_json_summary_when_clean(tmp_path, capsys):
    target = tmp_path / "clean.py"
    target.write_text("value = compute()\n", encoding="utf-8")
    rc, payload = _json_output(capsys, ["scan", str(target), "--format", "json", "--all"])
    assert rc == 0
    assert payload["summary"] == {
        "findings": 0,
        "rules_matched": 0,
        "strict_fail": False,
        "suppressed": 0,
        "baselined": 0,
        "mode": "report",
    }
    assert payload["findings"] == []


def test_check_sarif_payload(tmp_path, capsys):
    target = tmp_path / "auth.py"
    target.write_text("return hashlib.md5(pwd)\n", encoding="utf-8")

    rc, payload = _json_output(capsys, ["scan", str(target), "--format", "sarif", "--all"])
    assert rc == 0
    assert payload["version"] == "2.1.0"
    assert "$schema" in payload
    assert len(payload["runs"]) == 1

    driver = payload["runs"][0]["tool"]["driver"]
    assert driver["name"] == "daimonion"
    assert driver["version"]
    rules = {rule["id"]: rule for rule in driver["rules"]}
    assert "crypto/deprecated-algorithms-prohibited" in rules
    assert rules["crypto/deprecated-algorithms-prohibited"]["name"] == "crypto/deprecated-algorithms-prohibited"
    assert rules["crypto/deprecated-algorithms-prohibited"]["shortDescription"]["text"]
    assert rules["crypto/deprecated-algorithms-prohibited"]["defaultConfiguration"]["level"] == "warning"

    results = payload["runs"][0]["results"]
    assert results
    result = results[0]
    assert result["ruleId"] == "crypto/deprecated-algorithms-prohibited"
    assert result["level"] == "warning"
    assert result["message"]["text"]
    location = result["locations"][0]["physicalLocation"]
    assert location["artifactLocation"]["uri"].endswith("auth.py")
    assert location["region"]["startLine"] == 1


def test_sarif_level_mapping():
    from daimonion.report import build_sarif_report

    def finding(enforcement: str) -> Finding:
        rule = Rule(id="r", title="t", triggers="x", summary="s", enforcement=enforcement, kind="structural")
        return Finding(rule=rule, file_path="f.py", line_number=1, matched_text="x", context_line="x")

    payload = build_sarif_report([finding("L2"), finding("L1"), finding("L0"), finding("")])
    levels = [result["level"] for result in payload["runs"][0]["results"]]
    assert levels == ["error", "warning", "note", "warning"]


def test_sarif_rules_only_cover_referenced_rule_ids():
    from daimonion.report import build_sarif_report

    rule_a = Rule(id="a", title="A", triggers="x", summary="s", enforcement="L2")
    rule_b = Rule(id="b", title="B", triggers="x", summary="s", enforcement="L1")
    finding = Finding(rule=rule_a, file_path="f.py", line_number=2, matched_text="x", context_line="x")
    run = build_sarif_report([finding, finding])["runs"][0]
    assert [rule["id"] for rule in run["tool"]["driver"]["rules"]] == ["a"]
    assert rule_b.id not in {r["ruleId"] for r in run["results"]}


def test_diff_outside_git_repo_is_graceful(tmp_path, capsys):
    """A directory that is not a git repo (or has no changes) yields no findings, exit 0."""
    rc, payload = _json_output(capsys, ["scan", "--repo", str(tmp_path), "--format", "json"])
    assert rc == 0
    assert payload["findings"] == []
    assert payload["summary"]["findings"] == 0


def test_check_binary_file_is_graceful(tmp_path, capsys):
    target = tmp_path / "blob.py"
    target.write_bytes(b"\x00\x01\xff\xfe binary payload \x00\x80")
    rc, payload = _json_output(capsys, ["scan", str(target), "--format", "json", "--all"])
    assert rc == 0
    assert payload["findings"] == []


def test_check_unreadable_file_is_graceful(tmp_path, capsys, monkeypatch):
    target = tmp_path / "locked.py"
    target.write_text("hashlib.md5(b'x')\n", encoding="utf-8")

    def _denied(self, *args, **kwargs):
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "read_text", _denied)
    rc, payload = _json_output(capsys, ["scan", str(target), "--format", "json", "--all"])
    assert rc == 0
    assert payload["findings"] == []


def test_scan_without_config_scopes_nothing(tmp_path, capsys):
    """Without `.daimonion.yml`, scan runs every rule (like `--all`)."""
    target = tmp_path / "app.py"
    target.write_text("cookie = True\n", encoding="utf-8")

    rc, payload = _json_output(capsys, ["scan", str(target), "--repo", str(tmp_path), "--format", "json"])
    ids = {finding["rule_id"] for finding in payload["findings"]}
    assert rc == 0
    assert "privacy/external-transmission-declared" in ids


def test_scan_config_runs_all_builtins(tmp_path, capsys):
    """A `cli` config no longer gates the scan: every builtin rule runs."""
    (tmp_path / ".daimonion.yml").write_text("version: 1\nwhen: [cli]\n", encoding="utf-8")
    target = tmp_path / "app.py"
    target.write_text("import hashlib\nhashlib.md5(b'x')\ncookie = True\n", encoding="utf-8")

    rc, payload = _json_output(capsys, ["scan", str(target), "--repo", str(tmp_path), "--format", "json"])
    ids = {finding["rule_id"] for finding in payload["findings"]}
    assert rc == 0
    assert "crypto/deprecated-algorithms-prohibited" in ids
    assert "privacy/external-transmission-declared" in ids


def test_scan_diff_mode_runs_all_builtins(tmp_path, capsys):
    """Bare `scan` reads the git diff and runs every builtin rule."""
    import subprocess

    (tmp_path / ".daimonion.yml").write_text("version: 1\nwhen: [cli]\n", encoding="utf-8")
    target = tmp_path / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    target.write_text("import hashlib\nhashlib.md5(b'x')\n", encoding="utf-8")

    rc, payload = _json_output(capsys, ["scan", "--repo", str(tmp_path), "--format", "json"])
    ids = {finding["rule_id"] for finding in payload["findings"]}
    assert rc == 0
    assert "crypto/deprecated-algorithms-prohibited" in ids
