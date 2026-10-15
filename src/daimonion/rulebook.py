"""The vendored law-map rulebook and the AGENTS.md rules block built from it.

``rulebook/`` inside this package is written only by
``tools/vendor_rulebook.py``: ``sections/MANIFEST.yml``,
``sections/VOCABULARY.yml``, ``sections/LICENSE``, every section file the
manifest lists, the whole ``checks/`` tree, the whole ``obligations/`` tree
(grounding ``strength`` values drive the binding-tier labels), and
``LAWMAP_SHA``. A daimonion release therefore pins exactly one law-map
commit, and both rendering and linting never touch the network.

A section file is Markdown with YAML front matter (id, version, status,
placement, when, obligations, triggers, sources, license) plus an ``en:``
block (English title/summary/prohibited) ahead of the Japanese prose body::

    ---
    id: baseline-personal-data
    version: "2026-10-15.1"
    status: active
    placement: agents_md
    when: [personal_data, face_recognition, medtech]
    en:
      title: "Personal data — minimise before collecting, ..."
      summary:
        - "Ask whether each item is needed before collecting it; ..."
      prohibited:
        - "Collection without a defined purpose (...)."
    ---

``render_block`` localises per rule: ``--lang en`` renders the ``en:``
title and summary; any other language renders the section's Japanese h1
and the numbered items of its ``> 要約:`` blockquote. Each rule also
carries a binding-tier label derived from its obligations' grounding
``strength`` values (``binding`` = legal duty, ``persuasive`` = public
recommendation, ``background`` = private rule or lesson).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import Any
from urllib.parse import urlsplit

import yaml

RULEBOOK_ROOT: Traversable = files("daimonion") / "rulebook"

#: The rulebook's abstract ``when`` vocabulary
#: (``sections/VOCABULARY.yml``, embedded into ``sections/MANIFEST.yml``).
WHEN_VOCABULARY: tuple[str, ...] = (
    "always",
    "library",
    "cli",
    "embedded",
    "personal_data",
    "face_recognition",
    "medtech",
    "scraping",
    "oj_code",
    "kaggle",
    "mcp",
    "data_science",
    "web_api",
    "commercial",
    "eu_market",
    "jp",
    "ai_assisted",
)

BEGIN_MARKER = "<!-- daimonion:rules:begin"
END_MARKER = "<!-- daimonion:rules:end -->"
#: Markers of the block before it was renamed from "ethics" to "rules". A guide
#: that still carries them is read as a stale block: ``--check`` fails and
#: ``--write`` replaces it in place with the current markers.
LEGACY_BEGIN_MARKER = "<!-- daimonion:ethics:begin"
LEGACY_END_MARKER = "<!-- daimonion:ethics:end -->"

#: Where a section's full prose lives, at the vendored commit.
RULEBOOK_REPO_URL = "https://github.com/politeuma/law-map"
RULEBOOK_GUIDANCE_PATH = "guidance/sections"

_SUMMARY_RE = re.compile(r"^> 要約:\s*(?P<first>.*)$")
_ITEM_RE = re.compile(r"\(\d+\)\s*")
_SEE_BODY = "詳細は本文。"


@dataclass(frozen=True)
class Section:
    """One rulebook section: manifest placement plus its front matter and prose body."""

    id: str
    file: str
    when: tuple[str, ...]
    placement: str
    status: str
    version: str
    triggers: tuple[str, ...]
    body: str
    sources: tuple[str, ...] = ()
    pack: str = "core"
    en_title: str = ""
    en_summary: tuple[str, ...] = ()
    obligations: tuple[str, ...] = ()
    tier: str = ""

    @property
    def title(self) -> str:
        """The section's own h1 title (Japanese prose heading)."""
        first = self.body.split("\n", 1)[0]
        return first.removeprefix("# ").strip() if first.startswith("# ") else self.id

    @property
    def summary_items(self) -> tuple[str, ...]:
        """The numbered items of the ``> 要約:`` blockquote, or the whole summary as one item."""
        return _summary_items(self.body)

    @property
    def rule_lines(self) -> tuple[str, ...]:
        """What the block shows by default: the ``en:`` summary, else the Japanese summary items."""
        return self.en_summary or self.summary_items

    def localized(self, lang: str) -> tuple[str, tuple[str, ...]]:
        """The ``(heading, lines)`` pair the block shows for ``lang``.

        ``en`` renders the front matter's ``en:`` title and summary; any
        other language renders the Japanese h1 and summary items, so a
        missing or partial translation can never produce an empty rule.
        """
        if lang == "en" and self.en_title and self.en_summary:
            return self.en_title, self.en_summary
        return self.title, self.summary_items

    def applies(self, conditions: Iterable[str], packs: Iterable[str] = ("core",)) -> bool:
        """Whether the section lands in AGENTS.md for a project declaring ``conditions``.

        Only ``active`` sections in the opted-in ``packs`` apply; ``always``
        sections apply without being listed. Opting into an extension pack
        is a project-level decision expressed through ``packs``.
        """
        wanted = {"always", *conditions}
        return (
            self.status == "active"
            and self.placement == "agents_md"
            and self.pack in set(packs)
            and bool(wanted & set(self.when))
        )


def lawmap_sha() -> str:
    """The law-map commit this daimonion build vendors."""
    return (RULEBOOK_ROOT / "LAWMAP_SHA").read_text(encoding="utf-8").strip()


#: Binding tiers for the rules block (PHI-5): the strongest grounding
#: ``strength`` across a section's obligations. ``binding`` = legal duty
#: (statute/regulation), ``persuasive`` = public recommendation
#: (guidance/standard), ``background`` = private rule or incident lesson.
#: Mixed sections report the strongest tier present.
TIER_RANK: dict[str, int] = {"background": 0, "persuasive": 1, "binding": 2}

#: Human labels for each tier, keyed by UI language.
TIER_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "binding": "Legal duty — statute or regulation requires this",
        "persuasive": "Public recommendation — official guidance or standard",
        "background": "Private rule or lesson — contest rule, incident report, or community practice",
    },
    "ja": {
        "binding": "法的義務 — 法令が求めるもの",
        "persuasive": "公的推奨 — 公式ガイダンス・標準",
        "background": "私的規約・教訓 — 競技規約・事故報告・コミュニティ慣行",
    },
}


def _obligation_strengths(root: Traversable = RULEBOOK_ROOT) -> dict[str, set[str]]:
    """Map obligation id → its grounding ``strength`` values from vendored ``obligations/``."""
    out: dict[str, set[str]] = {}
    obligations_dir = root / "obligations"
    try:
        names = [p.name for p in obligations_dir.iterdir()]
    except OSError:
        return out
    for domain in sorted(names):
        domain_dir = obligations_dir / domain
        try:
            files = sorted(p.name for p in domain_dir.iterdir())
        except OSError:
            continue
        for name in files:
            if not name.endswith(".yml") or name.startswith("_"):
                continue
            try:
                data = yaml.safe_load((domain_dir / name).read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(data, dict):
                continue
            oid = str(data.get("id", ""))
            groundings = data.get("groundings", [])
            strengths = {str(g.get("strength", "")).strip() for g in groundings if isinstance(g, dict)}
            strengths.discard("")
            if oid and strengths:
                out[oid] = strengths
    return out


def section_tier(obligation_ids: Iterable[str], strengths: dict[str, set[str]] | None = None) -> str:
    """Strongest tier across ``obligation_ids`` (``binding`` > ``persuasive`` > ``background``)."""
    table = _obligation_strengths() if strengths is None else strengths
    best = ""
    for oid in obligation_ids:
        for strength in table.get(oid, ()):
            if TIER_RANK.get(strength, -1) > TIER_RANK.get(best, -1):
                best = strength
    return best


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Split a section file into its YAML front matter and the prose body."""
    if not text.startswith("---\n"):
        msg = "section file has no YAML front matter"
        raise ValueError(msg)
    head, sep, body = text[len("---\n") :].partition("\n---\n")
    if not sep:
        msg = "section file front matter is not closed"
        raise ValueError(msg)
    data = yaml.safe_load(head)
    if not isinstance(data, dict):
        msg = "section file front matter is not a mapping"
        raise TypeError(msg)
    return data, body.lstrip("\n")


def _join_wrapped(lines: Iterable[str]) -> str:
    """Re-join hard-wrapped prose: no space between two CJK characters, one otherwise."""
    text = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if text and (text[-1].isascii() or line[0].isascii()):
            text += " "
        text += line
    return text


def _summary_items(body: str) -> tuple[str, ...]:
    collected: list[str] | None = None
    for line in body.split("\n"):
        if collected is None:
            match = _SUMMARY_RE.match(line)
            if match:
                collected = [match.group("first")]
            continue
        if not line.startswith(">"):
            break
        collected.append(line[1:])
    if not collected:
        return ()
    summary = _join_wrapped(collected).removesuffix(_SEE_BODY).strip()
    items = [item.strip().removesuffix("。") for item in _ITEM_RE.split(summary) if item.strip()]
    return tuple(items)


def _en_block(fields: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    """The front matter's ``en:`` title and summary lines (empty when absent)."""
    en = fields.get("en")
    if not isinstance(en, dict):
        return "", ()
    title = en.get("title")
    summary = en.get("summary")
    lines = tuple(str(line).strip() for line in summary if str(line).strip()) if isinstance(summary, list) else ()
    return (str(title).strip() if isinstance(title, str) else ""), lines


def _as_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return ()


def load_sections(root: Traversable = RULEBOOK_ROOT) -> list[Section]:
    """Every manifest section, in manifest order."""
    sections_dir = root / "sections"
    manifest = yaml.safe_load((sections_dir / "MANIFEST.yml").read_text(encoding="utf-8"))
    strengths = _obligation_strengths(root)
    sections: list[Section] = []
    for row in manifest["sections"]:
        fields, body = parse_front_matter((sections_dir / row["file"]).read_text(encoding="utf-8"))
        triggers = fields.get("triggers")
        keywords: object = triggers.get("keywords") if isinstance(triggers, dict) else []
        en_title, en_summary = _en_block(fields)
        obligation_ids = _as_tuple(fields.get("obligations", []))
        sections.append(
            Section(
                id=str(row["id"]),
                file=str(row["file"]),
                when=_as_tuple(row.get("when", "always")),
                placement=str(row.get("placement", fields.get("placement", "agents_md"))),
                status=str(fields.get("status", row.get("status", "draft"))),
                version=str(fields.get("version", row.get("version", ""))),
                triggers=_as_tuple(keywords),
                body=body,
                sources=_as_tuple(fields.get("sources", [])),
                pack=str(row.get("pack", "core")),
                en_title=en_title,
                en_summary=en_summary,
                obligations=obligation_ids,
                tier=section_tier(obligation_ids, strengths),
            )
        )
    return sections


def select_sections(
    conditions: Iterable[str],
    sections: Iterable[Section] | None = None,
    packs: Iterable[str] = ("core",),
) -> list[Section]:
    """The sections that apply to a project declaring ``conditions``."""
    conditions = list(conditions)
    pool = load_sections() if sections is None else sections
    return [section for section in pool if section.applies(conditions, packs)]


def _source_link(url: str) -> str:
    host = urlsplit(url).netloc.removeprefix("www.") or url
    return f"[{host}]({url})"


def render_rule(section: Section, sha: str, lang: str = "ja") -> str:
    """One rule: heading, binding tier, 1-3 imperative lines, sources, and a link to the full section."""
    heading, lines = section.localized(lang)
    out = [f"### {heading}", ""]
    if section.tier:
        label = TIER_LABELS["ja" if lang == "ja" else "en"].get(section.tier, section.tier)
        prefix = "拘束力" if lang == "ja" else "Binding"
        out += [f"*{prefix}: {label}*", ""]
    out += [f"- {line}" for line in lines]
    details = f"[rulebook `{section.id}`]({RULEBOOK_REPO_URL}/blob/{sha}/{RULEBOOK_GUIDANCE_PATH}/{section.file})"
    refs = ", ".join(_source_link(url) for url in section.sources)
    out += ["", f"Sources: {refs} · Details: {details}" if refs else f"Details: {details}", ""]
    return "\n".join(out)


def render_block(
    conditions: Iterable[str],
    sections: Iterable[Section] | None = None,
    sha: str | None = None,
    lang: str = "ja",
    packs: Iterable[str] = ("core",),
) -> str:
    """The marker-delimited rules block ``agents-md`` writes into AGENTS.md."""
    conditions = sorted(set(conditions) - {"always"})
    chosen = select_sections(conditions, sections, packs)
    sha = lawmap_sha() if sha is None else sha
    when = ",".join(["always", *conditions])
    packs_name = "+".join(packs)
    lines = [
        f"{BEGIN_MARKER} rulebook={sha[:12]} when={when} packs={packs_name} lang={lang} -->",
        "<!-- Generated by `daimonion agents-md --write` from the vendored rulebook; edit .daimonion.yml, not this block. -->",
        "",
        "## Rules for this project",
        "",
        "Rules from the [rulebook](https://github.com/politeuma/law-map/tree/main/guidance/sections) that match this project's `.daimonion.yml`",
        "conditions. Follow the lines under each rule; its sources say where the rule comes from, and the",
        "linked rulebook section holds the facts, cases, and prohibited patterns behind it.",
        "Before committing, run `daimonion scan` to match changed lines against these rules. Not legal advice.",
    ]
    if any(section.localized(lang)[1] == section.summary_items and lang == "en" for section in chosen):
        lines.append("Rules without an English summary yet show their Japanese summary.")
    lines.append("")
    block = "\n".join(lines) + "\n" + "\n".join(render_rule(section, sha, lang) for section in chosen)
    return block + END_MARKER + "\n"


def _block_span(document: str) -> tuple[int, int] | None:
    """Start/end offsets of the rules block (end past its trailing newline), or None.

    A block under the legacy ``daimonion:ethics`` markers counts as the block.
    """
    for begin, end_marker in ((BEGIN_MARKER, END_MARKER), (LEGACY_BEGIN_MARKER, LEGACY_END_MARKER)):
        start = document.find(begin)
        if start != -1:
            break
    else:
        return None
    end = document.find(end_marker, start)
    if end == -1:
        msg = f"found {begin!r} without a matching {end_marker!r}"
        raise ValueError(msg)
    end += len(end_marker)
    if document[end : end + 1] == "\n":
        end += 1
    return start, end


def splice_block(document: str, block: str) -> str:
    """Replace the existing rules block in ``document``, or append one after a blank line."""
    span = _block_span(document)
    if span is None:
        return block if not document.strip() else document.rstrip("\n") + "\n\n" + block
    start, end = span
    return document[:start] + block + document[end:]


def extract_block(document: str) -> str | None:
    """The rules block currently in ``document`` (markers included), if any."""
    span = _block_span(document)
    return None if span is None else document[span[0] : span[1]]


__all__ = [
    "BEGIN_MARKER",
    "END_MARKER",
    "LEGACY_BEGIN_MARKER",
    "LEGACY_END_MARKER",
    "RULEBOOK_GUIDANCE_PATH",
    "RULEBOOK_REPO_URL",
    "RULEBOOK_ROOT",
    "TIER_LABELS",
    "TIER_RANK",
    "WHEN_VOCABULARY",
    "Section",
    "extract_block",
    "lawmap_sha",
    "load_sections",
    "parse_front_matter",
    "render_block",
    "render_rule",
    "section_tier",
    "select_sections",
    "splice_block",
]
