"""law-map check spec loading: --rules accepts a checks/ directory."""

from __future__ import annotations

from pathlib import Path

import yaml

from daimonion.cli import main
from daimonion.engine import Linter
from daimonion.models import Rule
from daimonion.rules import load_rules_from_checks_dir, load_rules_from_yaml


def _write_spec(checks_root: Path, ref: str, spec: dict) -> Path:
    target = checks_root / f"{ref}.yml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return target


def _pii_spec(**overrides) -> dict:
    spec = {
        "id": "privacy/no-cleartext-pii",
        "obligation": "obligation.privacy.no-cleartext-pii-logging",
        "level": "L1",
        "triggers": [r"(?i)\b(pii|personal[_ ]?data|privacy)\b"],
        "acceptance": "No raw personal identifier reaches a logging sink.",
    }
    spec.update(overrides)
    return spec


def test_from_check_spec_maps_level_and_triggers():
    rule = Rule.from_check_spec(_pii_spec())
    assert rule.id == "privacy/no-cleartext-pii"
    assert rule.enforcement == "L1"
    assert rule.category == "privacy"
    assert rule.title == "obligation.privacy.no-cleartext-pii-logging"
    assert rule.summary == "No raw personal identifier reaches a logging sink."
    assert rule.gate == ""
    findings = Linter([rule]).scan_text("logger.info(personal_data)\n")
    assert [f.rule.id for f in findings] == ["privacy/no-cleartext-pii"]


def test_from_check_spec_without_triggers_never_fires():
    rule = Rule.from_check_spec(_pii_spec(triggers=[]))
    assert rule.triggers == "(?!)"
    linter = Linter([rule])
    assert linter.scan_text("logger.info(personal_data)\n") == []
    assert [r.id for r in linter.rules] == ["privacy/no-cleartext-pii"]


def test_from_check_spec_joins_trigger_list_as_alternation():
    rule = Rule.from_check_spec(_pii_spec(triggers=[r"ntp", r"chrony"]))
    assert Linter([rule]).scan_text("sync with chrony daily\n")
    assert not Linter([rule]).scan_text("nothing relevant here\n")


def test_from_check_spec_invalid_regex_is_dropped_by_engine():
    rule = Rule.from_check_spec(_pii_spec(triggers=["([unclosed"]))
    linter = Linter([rule])
    assert linter.scan_text("anything at all\n") == []


def test_load_rules_from_checks_dir(tmp_path):
    checks = tmp_path / "checks"
    _write_spec(checks, "privacy/no-cleartext-pii", _pii_spec())
    _write_spec(
        checks,
        "crypto/no-deprecated-algorithms",
        {
            "id": "crypto/no-deprecated-algorithms",
            "obligation": "obligation.crypto.no-deprecated-algorithms",
            "level": "L2",
            "triggers": [r"(?i)\b(md5|sha-?1)\b"],
        },
    )
    _write_spec(checks, "privacy/_draft", {"id": "privacy/_draft"})
    (checks / "privacy" / "broken.yml").write_text("id: [unclosed\n", encoding="utf-8")
    rules = load_rules_from_checks_dir(checks)
    by_id = {r.id: r for r in rules}
    assert set(by_id) == {"privacy/no-cleartext-pii", "crypto/no-deprecated-algorithms"}
    # A keyword spec declared L2 is capped to L1; only `kind: structural` keeps L2.
    assert by_id["crypto/no-deprecated-algorithms"].enforcement == "L1"


def test_structural_check_spec_keeps_l2():
    spec = {"id": "crypto/md5-call", "level": "L2", "kind": "structural", "triggers": [r"hashlib\.md5\("]}
    assert Rule.from_check_spec(spec).enforcement == "L2"
    assert Rule.from_check_spec({**spec, "kind": "keyword"}).enforcement == "L1"


def test_load_rules_from_yaml_accepts_directory(tmp_path):
    checks = tmp_path / "checks"
    _write_spec(checks, "privacy/no-cleartext-pii", _pii_spec())
    rules = load_rules_from_yaml(checks)
    assert [r.id for r in rules] == ["privacy/no-cleartext-pii"]


def test_check_with_rules_pointing_at_checks_dir(tmp_path, capsys):
    checks = tmp_path / "checks"
    _write_spec(checks, "privacy/no-cleartext-pii", _pii_spec())
    target = tmp_path / "app.py"
    target.write_text("logger.info(personal_data)\n", encoding="utf-8")
    assert main(["--rules", str(checks), "check", str(target), "--all"]) == 0
    out = capsys.readouterr().out
    assert "privacy/no-cleartext-pii" in out


def test_repo_check_specs_load_and_scan(tmp_path):
    """Every shipped law-map check spec loads; the PII + NTP pair fires end to end."""
    repo_checks = Path(__file__).resolve().parent.parent.parent / "law-map" / "checks"
    rules = load_rules_from_yaml(repo_checks)
    assert len(rules) == 18
    linter = Linter(rules)
    pii = linter.scan_text("logger.info(personal_data)\n")
    assert any(f.rule.id == "privacy/no-cleartext-pii" for f in pii)
    ntp = linter.scan_text("server = clock.nc.fukuoka-u.ac.jp\n")
    assert any(f.rule.id == "security/public-ntp-hygiene" for f in ntp)
    l2_ids = {f.rule.id for f in linter.scan_text("vulnerability CVE-2024-1 found\n")}
    assert {"security/sbom-present", "security/no-known-cve"} <= l2_ids
