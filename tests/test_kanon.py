"""The vendored kanon snapshot, section selection, and the AGENTS.md block."""

from __future__ import annotations

import re

import pytest

from daimonion import kanon
from daimonion.kanon import BEGIN_MARKER, END_MARKER, WHEN_VOCABULARY, Section


def _section(id_: str, when: tuple[str, ...], status: str = "active", placement: str = "agents_md") -> Section:
    body = f"# {id_} title\n\n> 要約: {id_}\n> Triggers: `x`.\n\n## 事実\n\nfact\n\n<!-- not legal advice -->\n"
    return Section(
        id=id_,
        file=f"{id_}.md",
        when=when,
        placement=placement,
        status=status,
        version="v",
        triggers=(),
        body=body,
    )


def test_snapshot_is_complete_and_well_formed():
    sections = kanon.load_sections()
    assert sections, "the vendored kanon has no sections"
    assert re.fullmatch(r"[0-9a-f]{40}", kanon.kanon_sha())
    for section in sections:
        tier, slug = section.file.removesuffix(".md").split("/")
        assert section.id == f"{tier}-{slug}"
        assert section.status in {"draft", "active", "kind"}
        assert section.body.startswith("# "), f"{section.id}: body must open with its h1 title"


def test_snapshot_when_values_stay_in_vocabulary():
    """A re-vendored kanon that grows the vocabulary must fail here, not silently drop sections."""
    used = {condition for section in kanon.load_sections() for condition in section.when}
    assert used <= set(WHEN_VOCABULARY), sorted(used - set(WHEN_VOCABULARY))


def test_select_sections_gates_on_status_placement_and_when():
    pool = [
        _section("baseline-a", ("always",)),
        _section("domain-scrape", ("scraping",)),
        _section("domain-multi", ("mcp", "web_api")),
        _section("baseline-draft", ("always",), status="draft"),
        _section("baseline-charter", ("always",), placement="charter"),
    ]
    assert [s.id for s in kanon.select_sections([], pool)] == ["baseline-a"]
    assert [s.id for s in kanon.select_sections(["scraping"], pool)] == ["baseline-a", "domain-scrape"]
    assert [s.id for s in kanon.select_sections(["web_api"], pool)] == ["baseline-a", "domain-multi"]


def test_summary_items_split_the_numbered_summary():
    body = (
        "# t\n\n> 適用条件: x\n> 要約: (1)集める前に問う\n> (2)削除の経路を\n> 作る (3)protected\n"
        "> attributeを外すだけにしない。詳細は本文。\n> Triggers: `x`.\n\n## 事実\n"
    )
    section = _section("baseline-a", ("always",))
    section = Section(**{**section.__dict__, "body": body})
    assert section.summary_items == ("集める前に問う", "削除の経路を作る", "protected attributeを外すだけにしない")
    assert section.rule_lines == section.summary_items


def test_snapshot_sections_all_yield_rule_lines_and_sources():
    for section in kanon.load_sections():
        assert 1 <= len(section.rule_lines) <= 3, section.id
        assert section.sources, section.id


def test_manifest_directives_and_title_take_precedence(tmp_path):
    sections = tmp_path / "sections"
    (sections / "baseline").mkdir(parents=True)
    (sections / "baseline" / "a.md").write_text(
        '{# ethics: id=baseline-a version=1 status=active triggers=["x"] sources=["https://example.org/law"] #}\n'
        "# 見出し\n\n> 要約: (1)一つ目\n",
        encoding="utf-8",
    )
    (sections / "MANIFEST.yml").write_text(
        "sections:\n"
        "  - id: baseline-a\n    file: baseline/a.md\n    when: always\n"
        "    title: Rule A\n"
        "    directives:\n      agent:\n        - NEVER do x.\n        - >\n          ALWAYS do\n          y.\n",
        encoding="utf-8",
    )
    (section,) = kanon.load_sections(tmp_path)
    assert section.title == "Rule A"
    assert section.directives == ("NEVER do x.", "ALWAYS do y.")
    block = kanon.render_block([], [section], sha="b" * 40)
    assert "### Rule A\n\n- NEVER do x.\n- ALWAYS do y.\n" in block
    assert "一つ目" not in block
    assert "in Japanese" not in block
    assert "Sources: [example.org](https://example.org/law)" in block
    assert f"(https://github.com/politeuma/kanon/blob/{'b' * 40}/sections/baseline/a.md)" in block


def test_render_block_is_deterministic_and_records_conditions():
    pool = [_section("baseline-a", ("always",)), _section("domain-scrape", ("scraping",))]
    block = kanon.render_block(["scraping", "always", "scraping"], pool, sha="a" * 40)
    assert block == kanon.render_block(["scraping"], pool, sha="a" * 40)
    assert block.startswith(f"{BEGIN_MARKER} kanon={'a' * 12} when=always,scraping -->\n")
    assert block.endswith(f"{END_MARKER}\n")
    assert block.index("### baseline-a title") < block.index("### domain-scrape title")
    assert "- baseline-a\n" in block  # summary fallback
    assert "which is in Japanese" in block
    assert "## 事実" not in block  # the prose stays behind the details link


def test_splice_appends_then_replaces_in_place():
    doc = "# Guide\n\nkeep me\n"
    first = kanon.splice_block(doc, f"{BEGIN_MARKER} v1 -->\nold\n{END_MARKER}\n")
    assert first == f"# Guide\n\nkeep me\n\n{BEGIN_MARKER} v1 -->\nold\n{END_MARKER}\n"

    tail = "\n## After\n"
    second = kanon.splice_block(first + tail, f"{BEGIN_MARKER} v2 -->\nnew\n{END_MARKER}\n")
    assert second == f"# Guide\n\nkeep me\n\n{BEGIN_MARKER} v2 -->\nnew\n{END_MARKER}\n{tail}"
    assert kanon.extract_block(second) == f"{BEGIN_MARKER} v2 -->\nnew\n{END_MARKER}\n"


def test_legacy_ethics_block_is_replaced_in_place():
    legacy = f"{kanon.LEGACY_BEGIN_MARKER} kanon=old -->\nold\n{kanon.LEGACY_END_MARKER}\n"
    doc = f"# Guide\n\n{legacy}\n## After\n"
    assert kanon.extract_block(doc) == legacy
    block = f"{BEGIN_MARKER} -->\nnew\n{END_MARKER}\n"
    assert kanon.splice_block(doc, block) == f"# Guide\n\n{block}\n## After\n"


def test_splice_into_empty_document_is_just_the_block():
    block = f"{BEGIN_MARKER} -->\n{END_MARKER}\n"
    assert kanon.splice_block("", block) == block


def test_unterminated_block_is_an_error():
    with pytest.raises(ValueError, match="without a matching"):
        kanon.splice_block(f"{BEGIN_MARKER} -->\ndangling\n", "x")
