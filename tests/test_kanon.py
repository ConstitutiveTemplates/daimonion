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
        file=f"{id_}.md.jinja",
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
        tier, slug = section.file.removesuffix(".md.jinja").split("/")
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


def test_fold_keeps_title_and_summary_visible():
    folded = kanon.fold(_section("x", ("always",)).body)
    head, details = folded.split("<details>", 1)
    assert "# x title" in head and "> 要約: x" in head
    assert "## 事実" not in head
    assert details.startswith(f"\n{kanon.DETAILS_SUMMARY}\n\n## 事実")
    assert folded.endswith("<!-- not legal advice -->\n\n</details>\n")


def test_render_block_is_deterministic_and_records_conditions():
    pool = [_section("baseline-a", ("always",)), _section("domain-scrape", ("scraping",))]
    block = kanon.render_block(["scraping", "always", "scraping"], pool, sha="a" * 40)
    assert block == kanon.render_block(["scraping"], pool, sha="a" * 40)
    assert block.startswith(f"{BEGIN_MARKER} kanon={'a' * 12} when=always,scraping -->\n")
    assert block.endswith(f"{END_MARKER}\n")
    assert block.index("# baseline-a title") < block.index("# domain-scrape title")


def test_splice_appends_then_replaces_in_place():
    doc = "# Guide\n\nkeep me\n"
    first = kanon.splice_block(doc, f"{BEGIN_MARKER} v1 -->\nold\n{END_MARKER}\n")
    assert first == f"# Guide\n\nkeep me\n\n{BEGIN_MARKER} v1 -->\nold\n{END_MARKER}\n"

    tail = "\n## After\n"
    second = kanon.splice_block(first + tail, f"{BEGIN_MARKER} v2 -->\nnew\n{END_MARKER}\n")
    assert second == f"# Guide\n\nkeep me\n\n{BEGIN_MARKER} v2 -->\nnew\n{END_MARKER}\n{tail}"
    assert kanon.extract_block(second) == f"{BEGIN_MARKER} v2 -->\nnew\n{END_MARKER}\n"


def test_splice_into_empty_document_is_just_the_block():
    block = f"{BEGIN_MARKER} -->\n{END_MARKER}\n"
    assert kanon.splice_block("", block) == block


def test_unterminated_block_is_an_error():
    with pytest.raises(ValueError, match="without a matching"):
        kanon.splice_block(f"{BEGIN_MARKER} -->\ndangling\n", "x")
