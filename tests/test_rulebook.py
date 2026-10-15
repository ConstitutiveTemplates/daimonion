"""The vendored rulebook snapshot, section selection, and the AGENTS.md block."""

from __future__ import annotations

import re

import pytest

from daimonion import rulebook
from daimonion.rulebook import BEGIN_MARKER, END_MARKER, WHEN_VOCABULARY, Section


def _section(
    id_: str,
    when: tuple[str, ...],
    status: str = "active",
    placement: str = "agents_md",
    pack: str = "core",
) -> Section:
    body = f"# {id_} title\n\n> 要約: {id_}\n\n## 事実\n\nfact\n\n<!-- not legal advice -->\n"
    return Section(
        id=id_,
        file=f"{id_}.md",
        when=when,
        placement=placement,
        status=status,
        version="v",
        triggers=(),
        body=body,
        pack=pack,
        en_title=f"{id_} english",
        en_summary=(f"{id_} line",),
    )


def test_snapshot_is_complete_and_well_formed():
    sections = rulebook.load_sections()
    assert sections, "the vendored rulebook has no sections"
    assert re.fullmatch(r"[0-9a-f]{40}", rulebook.lawmap_sha())
    for section in sections:
        tier, slug = section.file.removesuffix(".md").split("/")
        assert section.id == f"{tier}-{slug}"
        assert section.status in {"draft", "active"}
        assert section.body.startswith("# "), f"{section.id}: body must open with its h1 title"


def test_snapshot_when_values_stay_in_vocabulary():
    """A re-vendored rulebook that grows the vocabulary must fail here, not silently drop sections."""
    used = {condition for section in rulebook.load_sections() for condition in section.when}
    assert used <= set(WHEN_VOCABULARY), sorted(used - set(WHEN_VOCABULARY))


def test_snapshot_manifest_matches_front_matter():
    """The generated MANIFEST.yml agrees with each section file's front matter."""
    import yaml

    manifest = yaml.safe_load((rulebook.RULEBOOK_ROOT / "sections" / "MANIFEST.yml").read_text(encoding="utf-8"))
    assert manifest["schema"] == 2
    rows = {row["id"]: row for row in manifest["sections"]}
    assert len(rows) == len(rulebook.load_sections())
    for section in rulebook.load_sections():
        fields, _ = rulebook.parse_front_matter(
            (rulebook.RULEBOOK_ROOT / "sections" / section.file).read_text(encoding="utf-8")
        )
        row = rows[section.id]
        assert section.status == fields["status"] == row["status"]
        assert section.pack == row.get("pack", "core")


def test_select_sections_gates_on_status_placement_when_and_pack():
    pool = [
        _section("baseline-a", ("always",)),
        _section("domain-scrape", ("scraping",)),
        _section("domain-multi", ("mcp", "web_api")),
        _section("baseline-draft", ("always",), status="draft"),
        _section("baseline-charter", ("always",), placement="charter"),
        _section("domain-oj", ("oj_code",), pack="competitive-programming"),
    ]
    assert [s.id for s in rulebook.select_sections([], pool)] == ["baseline-a"]
    assert [s.id for s in rulebook.select_sections(["scraping"], pool)] == ["baseline-a", "domain-scrape"]
    assert [s.id for s in rulebook.select_sections(["web_api"], pool)] == ["baseline-a", "domain-multi"]
    assert [s.id for s in rulebook.select_sections(["oj_code"], pool)] == ["baseline-a"]
    assert [s.id for s in rulebook.select_sections(["oj_code"], pool, ["core", "competitive-programming"])] == [
        "baseline-a",
        "domain-oj",
    ]


def test_summary_items_split_the_numbered_summary():
    body = (
        "# t\n\n> 適用条件: x\n> 要約: (1)集める前に問う\n> (2)削除の経路を\n> 作る (3)protected\n"
        "> attributeを外すだけにしない。詳細は本文。\n\n## 事実\n"
    )
    section = _section("baseline-a", ("always",))
    section = Section(**{**section.__dict__, "body": body})
    assert section.summary_items == ("集める前に問う", "削除の経路を作る", "protected attributeを外すだけにしない")


def test_localized_renders_en_or_falls_back_to_japanese():
    section = _section("baseline-a", ("always",))
    assert section.localized("en") == ("baseline-a english", ("baseline-a line",))
    assert section.localized("ja") == ("baseline-a title", ("baseline-a",))
    bare = Section(**{**section.__dict__, "en_title": "", "en_summary": ()})
    assert bare.localized("en") == ("baseline-a title", ("baseline-a",))


def test_snapshot_active_sections_all_yield_en_and_ja_lines_and_sources():
    for section in rulebook.load_sections():
        if section.status != "active":
            continue
        assert section.en_title and section.en_summary, section.id
        assert 1 <= len(section.en_summary) <= 3, section.id
        assert section.summary_items, section.id
        assert section.sources, section.id


def test_front_matter_without_en_falls_back_to_summary(tmp_path):
    sections = tmp_path / "sections"
    (sections / "baseline").mkdir(parents=True)
    (sections / "baseline" / "a.md").write_text(
        "---\n"
        "id: baseline-a\nversion: '1'\nstatus: active\nplacement: agents_md\nwhen: always\n"
        "obligations: []\ntriggers:\n  keywords: ['x']\n  pattern: 'x'\nsources: ['https://example.org/law']\n"
        "license: CC-BY-4.0\n---\n# 見出し\n\n> 要約: (1)一つ目\n",
        encoding="utf-8",
    )
    (sections / "MANIFEST.yml").write_text(
        "schema: 2\nsections:\n  - id: baseline-a\n    file: baseline/a.md\n    when: always\n    pack: core\n",
        encoding="utf-8",
    )
    (section,) = rulebook.load_sections(tmp_path)
    assert section.title == "見出し"
    assert section.en_title == "" and section.en_summary == ()
    assert section.localized("en") == ("見出し", ("一つ目",))
    block = rulebook.render_block([], [section], sha="b" * 40, lang="en")
    assert "### 見出し\n\n- 一つ目\n" in block
    assert "Sources: [example.org](https://example.org/law)" in block
    assert (
        "(https://github.com/politeuma/law-map/blob/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/guidance/sections/baseline/a.md)"
        in block
    )


def test_render_block_is_deterministic_and_records_conditions_packs_and_lang():
    pool = [_section("baseline-a", ("always",)), _section("domain-scrape", ("scraping",))]
    block = rulebook.render_block(["scraping", "always", "scraping"], pool, sha="a" * 40, lang="en")
    assert block == rulebook.render_block(["scraping"], pool, sha="a" * 40, lang="en")
    assert block.startswith(f"{BEGIN_MARKER} rulebook={'a' * 12} when=always,scraping packs=core lang=en -->\n")
    assert block.endswith(f"{END_MARKER}\n")
    assert block.index("### baseline-a english") < block.index("### domain-scrape english")
    assert "- baseline-a line\n" in block
    assert "## 事実" not in block  # the prose stays behind the details link


def test_render_block_ja_renders_japanese_titles():
    pool = [_section("baseline-a", ("always",))]
    block = rulebook.render_block([], pool, sha="a" * 40, lang="ja")
    assert "### baseline-a title" in block
    assert "- baseline-a\n" in block
    assert "lang=ja" in block.split("\n", 1)[0]


def test_section_tier_prefers_strongest_strength():
    strengths = {
        "obligation.x.legal": {"binding"},
        "obligation.x.mixed": {"background", "persuasive"},
        "obligation.x.lesson": {"background"},
    }
    assert rulebook.section_tier(["obligation.x.legal", "obligation.x.lesson"], strengths) == "binding"
    assert rulebook.section_tier(["obligation.x.mixed"], strengths) == "persuasive"
    assert rulebook.section_tier(["obligation.x.lesson"], strengths) == "background"
    assert rulebook.section_tier(["obligation.x.unknown"], strengths) == ""
    assert rulebook.section_tier([], strengths) == ""


def test_render_rule_shows_binding_tier_in_both_languages():
    base = _section("baseline-a", ("always",))
    section = rulebook.Section(**{**base.__dict__, "tier": "binding"})
    en = rulebook.render_rule(section, "a" * 40, "en")
    assert "*Binding: Legal duty — statute or regulation requires this*" in en
    ja = rulebook.render_rule(section, "a" * 40, "ja")
    assert "*拘束力: 法的義務 — 法令が求めるもの*" in ja
    untiered = rulebook.Section(**{**base.__dict__, "tier": ""})
    assert "Binding:" not in rulebook.render_rule(untiered, "a" * 40, "en")


def test_vendored_sections_all_carry_tiers():
    """Every vendored section resolves its obligations to a binding tier."""
    for section in rulebook.load_sections():
        assert section.tier in ("binding", "persuasive", "background"), section.id
        assert section.obligations, section.id


def test_splice_appends_then_replaces_in_place():
    doc = "# Guide\n\nkeep me\n"
    first = rulebook.splice_block(doc, f"{BEGIN_MARKER} v1 -->\nold\n{END_MARKER}\n")
    assert first == f"# Guide\n\nkeep me\n\n{BEGIN_MARKER} v1 -->\nold\n{END_MARKER}\n"

    tail = "\n## After\n"
    second = rulebook.splice_block(first + tail, f"{BEGIN_MARKER} v2 -->\nnew\n{END_MARKER}\n")
    assert second == f"# Guide\n\nkeep me\n\n{BEGIN_MARKER} v2 -->\nnew\n{END_MARKER}\n{tail}"
    assert rulebook.extract_block(second) == f"{BEGIN_MARKER} v2 -->\nnew\n{END_MARKER}\n"


def test_legacy_ethics_block_is_replaced_in_place():
    legacy = f"{rulebook.LEGACY_BEGIN_MARKER} rulebook=old -->\nold\n{rulebook.LEGACY_END_MARKER}\n"
    doc = f"# Guide\n\n{legacy}\n## After\n"
    assert rulebook.extract_block(doc) == legacy
    block = f"{BEGIN_MARKER} -->\nnew\n{END_MARKER}\n"
    assert rulebook.splice_block(doc, block) == f"# Guide\n\n{block}\n## After\n"


def test_splice_into_empty_document_is_just_the_block():
    block = f"{BEGIN_MARKER} -->\n{END_MARKER}\n"
    assert rulebook.splice_block("", block) == block


def test_unterminated_block_is_an_error():
    with pytest.raises(ValueError, match="without a matching"):
        rulebook.splice_block(f"{BEGIN_MARKER} -->\ndangling\n", "x")


def test_front_matter_errors_are_loud():
    with pytest.raises(ValueError, match="no YAML front matter"):
        rulebook.parse_front_matter("# no front matter\n")
    with pytest.raises(ValueError, match="not closed"):
        rulebook.parse_front_matter("---\nid: x\n")
