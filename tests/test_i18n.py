"""English-canonical human output, the Japanese resource, and --no-emoji."""

from __future__ import annotations

import re
import string

import pytest

from daimonion.cli import format_findings, main
from daimonion.i18n import ICONS, MESSAGES, UI, _ja_resource, resolve_emoji, resolve_lang
from daimonion.models import Rule
from daimonion.rules import BUILTIN_RULES


@pytest.fixture
def pii_file(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("user_data = load()\n", encoding="utf-8")
    return target


def test_ja_resource_covers_every_message_and_builtin_rule():
    resource = _ja_resource()
    assert set(resource["messages"]) == set(MESSAGES)
    assert set(resource["rules"]) == {rule.id for rule in BUILTIN_RULES}
    for key, english in MESSAGES.items():
        # Same placeholders, so a translation can never raise KeyError at runtime.
        assert sorted(_fields(resource["messages"][key])) == sorted(_fields(english)), key


def _fields(template: str) -> list[str]:
    return [name.split("!")[0] for _, name, _, _ in string.Formatter().parse(template) if name]


def test_builtin_rule_text_is_english():
    japanese = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
    for rule in BUILTIN_RULES:
        assert not japanese.search(rule.title + rule.summary), rule.id


@pytest.mark.parametrize(
    ("explicit", "env", "expected"),
    [
        (None, {}, "en"),
        (None, {"LANG": "ja_JP.UTF-8"}, "ja"),
        (None, {"LC_ALL": "C", "LANG": "ja_JP.UTF-8"}, "en"),
        (None, {"DAIMONION_LANG": "ja", "LANG": "en_US.UTF-8"}, "ja"),
        ("en", {"DAIMONION_LANG": "ja"}, "en"),
        (None, {"DAIMONION_LANG": "fr"}, "en"),
    ],
)
def test_resolve_lang_precedence(explicit, env, expected):
    assert resolve_lang(explicit, env) == expected


def test_resolve_emoji():
    assert resolve_emoji(False, {}) is True
    assert resolve_emoji(True, {}) is False
    assert resolve_emoji(False, {"DAIMONION_NO_EMOJI": "1"}) is False
    assert resolve_emoji(False, {"DAIMONION_NO_EMOJI": "0"}) is True


def test_check_output_is_english_by_default(pii_file, capsys):
    assert main(["scan", str(pii_file), "--all"]) == 0
    out = capsys.readouterr().out
    assert "Summary:" in out and "Matched at:" in out and "Personal data" in out
    assert "要約" not in out


@pytest.mark.parametrize("argv", [["--lang", "ja", "scan"], ["scan", "--lang", "ja"]])
def test_lang_ja_before_or_after_the_subcommand(pii_file, capsys, argv):
    assert main([*argv, str(pii_file), "--all"]) == 0
    out = capsys.readouterr().out
    assert "要約:" in out and "検出箇所:" in out and "個人データ" in out


def test_locale_selects_japanese(pii_file, capsys, monkeypatch):
    monkeypatch.setenv("LANG", "ja_JP.UTF-8")
    assert main(["scan", str(pii_file), "--all"]) == 0
    assert "検出箇所:" in capsys.readouterr().out


def test_no_emoji_drops_every_icon(pii_file, capsys):
    assert main(["scan", str(pii_file), "--all", "--no-emoji"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("daimonion: Detected")
    assert not any(icon.strip() in out for icon in ICONS.values())


def test_custom_rule_reusing_a_builtin_id_keeps_its_own_text():
    builtin = next(r for r in BUILTIN_RULES if r.id == "deprecated-crypto")
    custom = Rule(id=builtin.id, title="Our crypto policy", triggers="md5", summary="Use our KMS.")
    ui = UI.create("ja")
    assert ui.rule_title(custom) == "Our crypto policy"
    assert ui.rule_title(builtin) == _ja_resource()["rules"][builtin.id]["title"]


def test_format_findings_without_matches_respects_ui():
    expected = _ja_resource()["messages"]["findings.none"]
    assert format_findings([], ui=UI.create("ja", emoji=False)) == expected
