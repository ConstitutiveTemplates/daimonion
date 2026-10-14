"""The vendored kanon snapshot and the AGENTS.md rules block built from it.

``kanon/`` inside this package is written only by ``tools/vendor_kanon.py``:
``sections/MANIFEST.yml``, the section files it lists, and ``KANON_SHA``.
A daimonion release therefore pins exactly one kanon commit, and rendering
never touches the network.

The block gives each rule as 1-3 imperative lines plus its sources and a link
to the full kanon section at the pinned commit; the long prose stays behind
that link. A manifest row may carry the agent-facing wording law-map keeps as
``directives.agent`` (a string, or a list when several obligations share the
section) and an English ``title``::

    - id: baseline-personal-data
      file: baseline/personal-data.md
      title: Personal data -- minimise before you collect
      directives:
        agent:
          - NEVER pass raw user identifiers to logging or error trackers.

Until the manifest has them, a rule falls back to the numbered items of its
section's summary blockquote and to the section's own title.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from urllib.parse import urlsplit

import yaml

KANON_ROOT: Traversable = files("daimonion") / "kanon"

#: The kanon's abstract ``when`` vocabulary (kanon README, MANIFEST.yml).
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
KANON_REPO_URL = "https://github.com/politeuma/kanon"

_HEADER_RE = re.compile(r"\A\{#\s*ethics:(?P<body>.*?)#\}", re.DOTALL)
_FIELD_RE = re.compile(r"(\w+)=(\[.*?\]|\S+)", re.DOTALL)
_SUMMARY_RE = re.compile(r"^> 要約:\s*(?P<first>.*)$")
_ITEM_RE = re.compile(r"\(\d+\)\s*")
_SEE_BODY = "詳細は本文。"


@dataclass(frozen=True)
class Section:
    """One kanon section: manifest placement plus its header and prose body."""

    id: str
    file: str
    when: tuple[str, ...]
    placement: str
    status: str
    version: str
    triggers: tuple[str, ...]
    body: str
    sources: tuple[str, ...] = ()
    directives: tuple[str, ...] = ()
    manifest_title: str = ""

    @property
    def title(self) -> str:
        """The manifest's (English) title, else the section's h1."""
        if self.manifest_title:
            return self.manifest_title
        first = self.body.split("\n", 1)[0]
        return first.removeprefix("# ").strip() if first.startswith("# ") else self.id

    @property
    def summary_items(self) -> tuple[str, ...]:
        """The numbered items of the ``> 要約:`` blockquote, or the whole summary as one item."""
        return _summary_items(self.body)

    @property
    def rule_lines(self) -> tuple[str, ...]:
        """What the block shows: the agent directives, else the summary items."""
        return self.directives or self.summary_items

    def applies(self, conditions: Iterable[str]) -> bool:
        """Whether the section lands in AGENTS.md for a project declaring ``conditions``."""
        wanted = {"always", *conditions}
        return self.status == "active" and self.placement == "agents_md" and bool(wanted & set(self.when))


def kanon_sha() -> str:
    """The kanon commit this daimonion build vendors."""
    return (KANON_ROOT / "KANON_SHA").read_text(encoding="utf-8").strip()


def parse_header(text: str) -> tuple[dict[str, object], str]:
    """Split a section file into its ``{# ethics: ... #}`` fields and the prose body."""
    match = _HEADER_RE.match(text)
    if match is None:
        msg = "section file has no {# ethics: ... #} header"
        raise ValueError(msg)
    fields: dict[str, object] = {}
    for key, raw in _FIELD_RE.findall(match.group("body")):
        fields[key] = json.loads(raw) if raw.startswith("[") else raw
    return fields, text[match.end() :].lstrip("\n")


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
        if not line.startswith(">") or line.startswith("> Triggers:"):
            break
        collected.append(line[1:])
    if not collected:
        return ()
    summary = _join_wrapped(collected).removesuffix(_SEE_BODY).strip()
    items = [item.strip().removesuffix("。") for item in _ITEM_RE.split(summary) if item.strip()]
    return tuple(items)


def _directives(row: dict[str, object]) -> tuple[str, ...]:
    directives = row.get("directives")
    if not isinstance(directives, dict):
        return ()
    agent = directives.get("agent")
    lines = [agent] if isinstance(agent, str) else agent if isinstance(agent, list) else []
    return tuple(" ".join(str(line).split()) for line in lines if str(line).strip())


def _as_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return ()


def load_sections(root: Traversable = KANON_ROOT) -> list[Section]:
    """Every manifest section, in manifest order."""
    sections_dir = root / "sections"
    manifest = yaml.safe_load((sections_dir / "MANIFEST.yml").read_text(encoding="utf-8"))
    sections: list[Section] = []
    for row in manifest["sections"]:
        fields, body = parse_header((sections_dir / row["file"]).read_text(encoding="utf-8"))
        sections.append(
            Section(
                id=str(row["id"]),
                file=str(row["file"]),
                when=_as_tuple(row.get("when", "always")),
                placement=str(row.get("placement", "agents_md")),
                status=str(fields.get("status", "draft")),
                version=str(fields.get("version", "")),
                triggers=_as_tuple(fields.get("triggers", [])),
                body=body,
                sources=_as_tuple(fields.get("sources", [])),
                directives=_directives(row),
                manifest_title=str(row.get("title", "")),
            )
        )
    return sections


def select_sections(conditions: Iterable[str], sections: Iterable[Section] | None = None) -> list[Section]:
    """The sections that apply to a project declaring ``conditions``."""
    conditions = list(conditions)
    pool = load_sections() if sections is None else sections
    return [section for section in pool if section.applies(conditions)]


def _source_link(url: str) -> str:
    host = urlsplit(url).netloc.removeprefix("www.") or url
    return f"[{host}]({url})"


def render_rule(section: Section, sha: str) -> str:
    """One rule: heading, 1-3 imperative lines, sources, and a link to the full section."""
    lines = [f"### {section.title}", ""]
    lines += [f"- {line}" for line in section.rule_lines]
    details = f"[kanon `{section.id}`]({KANON_REPO_URL}/blob/{sha}/sections/{section.file})"
    refs = ", ".join(_source_link(url) for url in section.sources)
    lines += ["", f"Sources: {refs} · Details: {details}" if refs else f"Details: {details}", ""]
    return "\n".join(lines)


def render_block(conditions: Iterable[str], sections: Iterable[Section] | None = None, sha: str | None = None) -> str:
    """The marker-delimited rules block ``agents-md`` writes into AGENTS.md."""
    conditions = sorted(set(conditions) - {"always"})
    chosen = select_sections(conditions, sections)
    sha = kanon_sha() if sha is None else sha
    when = ",".join(["always", *conditions])
    lines = [
        f"{BEGIN_MARKER} kanon={sha[:12]} when={when} -->",
        "<!-- Generated by `daimonion agents-md --write` from kanon; edit .daimonion.yml, not this block. -->",
        "",
        "## Rules for this project",
        "",
        "Rules from [kanon](https://github.com/politeuma/kanon) that match this project's `.daimonion.yml`",
        "conditions. Follow the lines under each rule; its sources say where the rule comes from, and the",
        "linked kanon section holds the facts, cases, and prohibited patterns behind it.",
        "Before committing, run `daimonion diff` to match changed lines against these rules. Not legal advice.",
    ]
    if any(not section.directives for section in chosen):
        lines.append("Rules without an agent directive yet show their kanon summary, which is in Japanese.")
    lines.append("")
    block = "\n".join(lines) + "\n" + "\n".join(render_rule(section, sha) for section in chosen)
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
