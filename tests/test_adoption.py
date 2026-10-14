"""Adoption controls: scan scope, inline ignores, the baseline, and adoption mode."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from daimonion.cli import main
from daimonion.engine import Linter
from daimonion.models import Rule
from daimonion.suppress import parse_line

STRUCTURAL = Rule(
    id="md5-call", title="t", triggers=r"hashlib\.md5\(", summary="s", enforcement="L2", kind="structural"
)
KEYWORD = Rule(id="md5-word", title="t", triggers=r"(?i)\bmd5\b", summary="s", enforcement="L1")


def _rules_file(root: Path) -> Path:
    path = root / "rules.yml"
    path.write_text(yaml.safe_dump({"rules": [STRUCTURAL.to_dict(), KEYWORD.to_dict()]}), encoding="utf-8")
    return path


def _json(capsys, argv: list[str]) -> tuple[int, dict]:
    rc = main(argv)
    return rc, json.loads(capsys.readouterr().out)


def _config(root: Path, **extra) -> None:
    (root / ".daimonion.yml").write_text(yaml.safe_dump({"version": 1, **extra}), encoding="utf-8")


# --- scan scope (DM-4) -------------------------------------------------------


def test_directory_scan_skips_docs_by_default(tmp_path):
    (tmp_path / "README.md").write_text("Uses md5 checksums.\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('license = "md5"\n', encoding="utf-8")
    (tmp_path / "app.py").write_text("digest = 'md5'\n", encoding="utf-8")
    files = {Path(f.file_path).name for f in Linter([KEYWORD]).scan_paths([tmp_path])}
    assert files == {"app.py"}
    files = {Path(f.file_path).name for f in Linter([KEYWORD], include_docs=True).scan_paths([tmp_path])}
    assert files == {"app.py", "README.md", "pyproject.toml"}


def test_explicit_doc_file_is_still_scanned(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("Uses md5 checksums.\n", encoding="utf-8")
    assert Linter([KEYWORD]).scan_paths([readme])


def test_docs_opt_in_via_flag_and_config(tmp_path, capsys):
    rules = str(_rules_file(tmp_path))
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "README.md").write_text("Uses md5 checksums.\n", encoding="utf-8")
    argv = ["--rules", rules, "check", str(docs), "--repo", str(tmp_path), "--format", "json"]

    assert _json(capsys, argv)[1]["summary"]["findings"] == 0
    assert _json(capsys, [*argv, "--include-docs"])[1]["summary"]["findings"] == 1
    _config(tmp_path, scan={"docs": True})
    assert _json(capsys, argv)[1]["summary"]["findings"] == 1


def test_diff_skips_docs_by_default(tmp_path, capsys):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("old\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("old\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("old\nUses md5.\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("old\ndigest = 'md5'\n", encoding="utf-8")
    findings = Linter([KEYWORD]).scan_git_diff(repo_dir=tmp_path)
    assert [f.file_path for f in findings] == ["app.py"]
    findings = Linter([KEYWORD], include_docs=True).scan_git_diff(repo_dir=tmp_path)
    assert sorted(f.file_path for f in findings) == ["README.md", "app.py"]


# --- inline ignores (DM-2) ---------------------------------------------------


def test_parse_line_directive():
    parsed = parse_line("x = 1  # daimonion: ignore[a, b] reason=not crypto until=2099-01-31")
    assert parsed.code == "x = 1  # "
    assert parsed.directive is not None
    assert parsed.directive.rule_ids == ("a", "b")
    assert parsed.directive.reason == "not crypto"
    assert str(parsed.directive.until) == "2099-01-31"
    assert parsed.directive.status() == "active"
    assert not parsed.standalone
    assert parse_line("    // daimonion: ignore[a] reason=x").standalone
    assert parse_line("<!-- daimonion: ignore[a] reason=x -->").directive.reason == "x"
    assert parse_line("x = 1").directive is None


def test_inline_ignore_same_line_and_next_line():
    text = (
        "h = hashlib.md5(b'x')  # daimonion: ignore[md5-call] reason=cache key\n"
        "# daimonion: ignore[md5-call] reason=cache key\n"
        "h = hashlib.md5(b'y')\n"
        "h = hashlib.md5(b'z')\n"
    )
    findings = Linter([STRUCTURAL]).scan_text(text)
    assert [(f.line_number, f.suppressed) for f in findings] == [(1, True), (3, True), (4, False)]


def test_ignore_only_covers_named_rules_and_reason_never_triggers():
    findings = Linter([STRUCTURAL, KEYWORD]).scan_text(
        "h = hashlib.md5(b'x')  # daimonion: ignore[md5-call] reason=md5\n"
    )
    by_rule = {f.rule.id: f.suppressed for f in findings}
    # md5-word matches the code before the directive, not the reason text.
    assert by_rule == {"md5-call": True, "md5-word": False}


def test_ignore_without_reason_or_expired_is_not_honoured():
    linter = Linter([STRUCTURAL])
    (missing,) = linter.scan_text("hashlib.md5(b'x')  # daimonion: ignore[md5-call]\n")
    assert missing.suppression is not None and missing.suppression.status() == "invalid"
    assert not missing.suppressed
    (expired,) = linter.scan_text("hashlib.md5(b'x')  # daimonion: ignore[md5-call] reason=x until=2020-01-01\n")
    assert expired.suppression is not None and expired.suppression.status() == "expired"
    assert not expired.suppressed


def test_cli_reports_expired_ignore_and_fails_strict(tmp_path, capsys):
    rules = str(_rules_file(tmp_path))
    target = tmp_path / "app.py"
    target.write_text("hashlib.md5(b'x')  # daimonion: ignore[md5-call] reason=x until=2020-01-01\n", encoding="utf-8")
    assert main(["--rules", rules, "--strict", "check", str(target), "--repo", str(tmp_path)]) == 1
    assert "ignore expired 2020-01-01" in capsys.readouterr().out
    target.write_text("hashlib.md5(b'x')  # daimonion: ignore[md5-call] reason=cache key\n", encoding="utf-8")
    rc, payload = _json(
        capsys, ["--rules", rules, "--strict", "check", str(target), "--repo", str(tmp_path), "--format", "json"]
    )
    assert rc == 0
    assert payload["summary"]["suppressed"] == 1
    # The keyword rule is not named by the directive, so it stays (as an L1 reminder).
    assert [f["rule_id"] for f in payload["findings"]] == ["md5-word"]


def test_diff_honours_directive_on_unchanged_line_above(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "app.py"
    target.write_text("# daimonion: ignore[md5-call] reason=cache key\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    target.write_text("# daimonion: ignore[md5-call] reason=cache key\nhashlib.md5(b'x')\n", encoding="utf-8")
    (finding,) = Linter([STRUCTURAL]).scan_git_diff(repo_dir=tmp_path)
    assert finding.suppressed


def test_sarif_marks_suppressed_results(tmp_path, capsys):
    rules = str(_rules_file(tmp_path))
    target = tmp_path / "app.py"
    target.write_text("hashlib.md5(b'x')  # daimonion: ignore[md5-call] reason=cache key\n", encoding="utf-8")
    rc, payload = _json(capsys, ["--rules", rules, "check", str(target), "--repo", str(tmp_path), "--format", "sarif"])
    assert rc == 0
    (result,) = [r for r in payload["runs"][0]["results"] if r["ruleId"] == "md5-call"]
    assert result["suppressions"] == [{"kind": "inSource", "justification": "cache key"}]


# --- baseline (DM-2) ---------------------------------------------------------


def test_baseline_absorbs_existing_findings_only(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rules = str(_rules_file(tmp_path))
    (tmp_path / "src").mkdir()
    target = tmp_path / "src" / "app.py"
    target.write_text("hashlib.md5(b'old')\n", encoding="utf-8")
    argv = ["--rules", rules, "--strict", "check", "src", "--repo", "."]

    assert main(argv) == 1
    capsys.readouterr()
    assert main([*argv, "--write-baseline"]) == 0
    baseline = json.loads((tmp_path / ".daimonion-baseline.json").read_text(encoding="utf-8"))
    assert {entry["file"] for entry in baseline["findings"]} == {"src/app.py"}
    capsys.readouterr()

    # Lines shifting above the old finding keep it baselined.
    target.write_text("import hashlib\n\nhashlib.md5(b'old')\n", encoding="utf-8")
    rc, payload = _json(capsys, [*argv, "--format", "json"])
    assert rc == 0
    assert payload["summary"]["baselined"] == 2  # md5-call and md5-word on the old line
    assert payload["findings"] == []

    # A new occurrence is still reported and fails --strict.
    target.write_text("hashlib.md5(b'old')\nhashlib.md5(b'new')\n", encoding="utf-8")
    rc, payload = _json(capsys, [*argv, "--format", "json"])
    assert rc == 1
    assert {f["line"] for f in payload["findings"]} == {2}


def test_explicit_missing_baseline_is_an_error(tmp_path, capsys):
    target = tmp_path / "app.py"
    target.write_text("x = 1\n", encoding="utf-8")
    assert main(["check", str(target), "--baseline", str(tmp_path / "nope.json")]) == 2
    assert "not found" in capsys.readouterr().err


# --- adoption mode (DM-2) ----------------------------------------------------


def test_adoption_flag_overrides_strict(tmp_path, capsys):
    rules = str(_rules_file(tmp_path))
    target = tmp_path / "app.py"
    target.write_text("hashlib.md5(b'x')\n", encoding="utf-8")
    argv = ["--rules", rules, "--strict", "check", str(target), "--repo", str(tmp_path)]
    assert main(argv) == 1
    capsys.readouterr()
    assert main(["--adoption", *argv]) == 0
    assert "would fail --strict" in capsys.readouterr().err


def test_config_mode_adoption_and_strict(tmp_path, capsys):
    rules = str(_rules_file(tmp_path))
    target = tmp_path / "app.py"
    target.write_text("hashlib.md5(b'x')\n", encoding="utf-8")
    argv = ["--rules", rules, "check", str(target), "--repo", str(tmp_path), "--format", "json"]

    _config(tmp_path, mode="adoption")
    rc, payload = _json(capsys, ["--strict", *argv])
    assert rc == 0
    assert payload["summary"]["mode"] == "adoption"
    assert payload["summary"]["strict_fail"] is False

    _config(tmp_path, mode="strict")
    rc, payload = _json(capsys, argv)
    assert rc == 1
    assert payload["summary"]["mode"] == "strict"


def test_invalid_config_mode_is_loud(tmp_path, capsys):
    target = tmp_path / "app.py"
    target.write_text("x = 1\n", encoding="utf-8")
    _config(tmp_path, mode="lenient")
    assert main(["check", str(target), "--repo", str(tmp_path)]) == 2
    assert "`mode` must be one of" in capsys.readouterr().err
