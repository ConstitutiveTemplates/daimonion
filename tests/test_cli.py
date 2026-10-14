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
    assert main(["check", str(target), "--all"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("⚠️  daimonion: Detected")
    assert "[L1]" in out
    assert "deprecated-crypto" in out
    assert not out.lstrip().startswith("{")


def test_default_format_clean_file(tmp_path, capsys):
    target = tmp_path / "clean.py"
    target.write_text("value = compute()\n", encoding="utf-8")
    assert main(["check", str(target), "--all"]) == 0
    assert capsys.readouterr().out.strip() == "✨ No legal or compliance triggers matched."


def test_prepare_write_then_check_autoloads_prepared_rules(tmp_path, capsys):
    """prepare --write materializes a rule set that a later check picks up on its own."""
    _write_answers(tmp_path, {"project_type": "cli"})
    target = tmp_path / "app.py"
    target.write_text("import hashlib\nhashlib.md5(b'x')\ncookie = True\n", encoding="utf-8")

    assert main(["prepare", "--repo", str(tmp_path), "--write"]) == 0
    capsys.readouterr()
    prepared = tmp_path / ".daimonion-rules.yml"
    assert prepared.is_file()

    # Remove the answers file: only the prepared rule file can scope the next run.
    (tmp_path / ".copier-answers.yml").unlink()

    rc, payload = _json_output(capsys, ["check", str(target), "--repo", str(tmp_path), "--format", "json"])
    ids = {finding["rule_id"] for finding in payload["findings"]}
    assert rc == 0
    assert "deprecated-crypto" in ids
    assert "jp-external-transmission" not in ids  # web_api-gated, project is cli


def test_strict_exit_codes(tmp_path, capsys):
    rules = str(_structural_rules(tmp_path))
    l2_target = tmp_path / "l2.py"
    l2_target.write_text("hashlib.md5(b'x')\n", encoding="utf-8")
    l1_target = tmp_path / "l1.py"
    l1_target.write_text("digest_name = 'md5'\n", encoding="utf-8")

    assert main(["--rules", rules, "--strict", "check", str(l2_target), "--all"]) == 1
    capsys.readouterr()

    # The keyword rule declared L2 is capped to L1, so it never fails --strict.
    assert main(["--rules", rules, "--strict", "check", str(l1_target), "--all"]) == 0
    assert "[L1] md5 (md5-word)" in capsys.readouterr().out

    # Without --strict even an L2 hit exits 0.
    assert main(["--rules", rules, "check", str(l2_target), "--all"]) == 0


def test_builtin_rules_never_fail_strict(tmp_path, capsys):
    """Every builtin is a keyword reminder: at most L1, so --strict passes."""
    from daimonion.rules import BUILTIN_RULES

    assert {rule.kind for rule in BUILTIN_RULES} == {"keyword"}
    assert {rule.enforcement for rule in BUILTIN_RULES} <= {"L0", "L1"}
    target = tmp_path / "app.py"
    target.write_text("import hashlib, requests\nhashlib.md5(b'x')\nagent = 'ua'\n", encoding="utf-8")
    assert main(["--strict", "check", str(target), "--all"]) == 0


def test_list_rules_scoped_versus_all(tmp_path, capsys):
    _write_answers(tmp_path, {"project_type": "cli"})

    assert main(["list-rules", "--repo", str(tmp_path)]) == 0
    scoped = capsys.readouterr().out
    assert "ai-copyright" in scoped
    assert "eu-eaa-accessibility" not in scoped

    assert main(["list-rules", "--repo", str(tmp_path), "--all"]) == 0
    every = capsys.readouterr().out
    assert "eu-eaa-accessibility" in every
    assert every.count("- [") > scoped.count("- [")


def test_list_rules_json(tmp_path, capsys):
    _write_answers(tmp_path, {"project_type": "cli"})
    rc, payload = _json_output(capsys, ["list-rules", "--repo", str(tmp_path), "--format", "json"])
    assert rc == 0
    ids = {rule["id"] for rule in payload["rules"]}
    assert payload["summary"]["rules"] == len(payload["rules"])
    assert "ai-copyright" in ids
    assert "eu-eaa-accessibility" not in ids
    assert {"id", "title", "triggers", "summary", "enforcement"} <= set(payload["rules"][0])


def test_prepare_with_malformed_gate_warns_and_excludes(tmp_path, capsys):
    """A broken gate in a loaded rule file fails closed and names the rule in a warning."""
    _write_answers(tmp_path, {"project_type": "web_api"})
    rules_file = tmp_path / "rules.yml"
    rules_file.write_text(
        yaml.safe_dump(
            {
                "rules": [
                    {"id": "good-rule", "title": "Good", "triggers": "good", "summary": "s", "gate": "web_api"},
                    {
                        "id": "broken-rule",
                        "title": "Broken",
                        "triggers": "broken",
                        "summary": "s",
                        "gate": "web_api ==",
                    },
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    with pytest.warns(UserWarning, match="broken-rule"):
        rc = main(["--rules", str(rules_file), "prepare", "--repo", str(tmp_path)])

    assert rc == 0
    applicable, _, gated = capsys.readouterr().out.partition("⏭️")
    assert "good-rule" in applicable
    assert "broken-rule" not in applicable
    assert "broken-rule" in gated


def test_list_rules_has_no_sarif_format():
    with pytest.raises(SystemExit) as excinfo:
        main(["list-rules", "--format", "sarif"])
    assert excinfo.value.code == 2


def test_check_json_payload(tmp_path, capsys):
    target = tmp_path / "auth.py"
    target.write_text("import hashlib\nreturn hashlib.md5(pwd)\n", encoding="utf-8")

    rules = str(_structural_rules(tmp_path))
    rc, payload = _json_output(
        capsys, ["--rules", rules, "--strict", "check", str(target), "--format", "json", "--all"]
    )
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
    rc, payload = _json_output(capsys, ["check", str(target), "--format", "json", "--all"])
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

    rc, payload = _json_output(capsys, ["check", str(target), "--format", "sarif", "--all"])
    assert rc == 0
    assert payload["version"] == "2.1.0"
    assert "$schema" in payload
    assert len(payload["runs"]) == 1

    driver = payload["runs"][0]["tool"]["driver"]
    assert driver["name"] == "daimonion"
    assert driver["version"]
    rules = {rule["id"]: rule for rule in driver["rules"]}
    assert "deprecated-crypto" in rules
    assert rules["deprecated-crypto"]["name"] == "deprecated-crypto"
    assert rules["deprecated-crypto"]["shortDescription"]["text"]
    assert rules["deprecated-crypto"]["defaultConfiguration"]["level"] == "warning"

    results = payload["runs"][0]["results"]
    assert results
    result = results[0]
    assert result["ruleId"] == "deprecated-crypto"
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
    rc, payload = _json_output(capsys, ["diff", "--repo", str(tmp_path), "--format", "json"])
    assert rc == 0
    assert payload["findings"] == []
    assert payload["summary"]["findings"] == 0


def test_check_binary_file_is_graceful(tmp_path, capsys):
    target = tmp_path / "blob.py"
    target.write_bytes(b"\x00\x01\xff\xfe binary payload \x00\x80")
    rc, payload = _json_output(capsys, ["check", str(target), "--format", "json", "--all"])
    assert rc == 0
    assert payload["findings"] == []


def test_check_unreadable_file_is_graceful(tmp_path, capsys, monkeypatch):
    target = tmp_path / "locked.py"
    target.write_text("hashlib.md5(b'x')\n", encoding="utf-8")

    def _denied(self, *args, **kwargs):
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "read_text", _denied)
    rc, payload = _json_output(capsys, ["check", str(target), "--format", "json", "--all"])
    assert rc == 0
    assert payload["findings"] == []


def test_legacy_prepared_rules_file_is_used_as_fallback(tmp_path, capsys):
    """A `.law-lint-rules.yml` from the previous release still scopes check runs."""
    _write_answers(tmp_path, {"project_type": "cli"})
    assert main(["prepare", "--repo", str(tmp_path), "--write"]) == 0
    capsys.readouterr()
    prepared = tmp_path / ".daimonion-rules.yml"
    assert prepared.is_file()
    legacy = tmp_path / ".law-lint-rules.yml"
    prepared.rename(legacy)

    target = tmp_path / "app.py"
    target.write_text("import hashlib\nhashlib.md5(b'x')\ncookie = True\n", encoding="utf-8")
    (tmp_path / ".copier-answers.yml").unlink()

    rc, payload = _json_output(capsys, ["check", str(target), "--repo", str(tmp_path), "--format", "json"])
    ids = {finding["rule_id"] for finding in payload["findings"]}
    assert rc == 0
    assert "deprecated-crypto" in ids
    assert "jp-external-transmission" not in ids


def test_new_prepared_rules_file_wins_over_legacy(tmp_path, capsys):
    """When both names exist, `.daimonion-rules.yml` takes precedence."""
    _write_answers(tmp_path, {"project_type": "cli"})
    assert main(["prepare", "--repo", str(tmp_path), "--write"]) == 0
    capsys.readouterr()
    assert (tmp_path / ".daimonion-rules.yml").is_file()
    legacy = tmp_path / ".law-lint-rules.yml"
    legacy.write_text(
        yaml.safe_dump(
            {
                "rules": [
                    {
                        "id": "legacy-only",
                        "title": "Legacy",
                        "triggers": "legacy-marker-xyz",
                        "summary": "s",
                    }
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    target = tmp_path / "app.py"
    target.write_text("legacy-marker-xyz\n", encoding="utf-8")
    (tmp_path / ".copier-answers.yml").unlink()

    rc, payload = _json_output(capsys, ["check", str(target), "--repo", str(tmp_path), "--format", "json"])
    assert rc == 0
    assert payload["findings"] == []
