"""The vendored good-future-codex snapshot and the AGENTS.md ethics block built from it.

``kanon/`` inside this package is written only by ``tools/vendor_kanon.py``:
``sections/MANIFEST.yml``, the section files it lists, and ``KANON_SHA``.
A law-lint release therefore pins exactly one kanon commit, and rendering
never touches the network.

Selection follows the kanon's own contract: a section applies when it is
``active``, wants ``placement: agents_md``, and its abstract ``when``
condition is ``always`` or one the project declared in ``.daimonion.yml``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable

import yaml

KANON_ROOT: Traversable = files("law_lint") / "kanon"

#: The kanon's abstract ``when`` vocabulary (good-future-codex README, MANIFEST.yml).
WHEN_VOCABULARY: tuple[str, ...] = (
    "always",
    "scraping",
    "oj_code",
    "mcp",
    "data_science",
    "web_api",
    "commercial",
    "eu_market",
    "jp",
    "ai_assisted",
)

BEGIN_MARKER = "<!-- daimonion:ethics:begin"
END_MARKER = "<!-- daimonion:ethics:end -->"

# Same fold the daimonion template applies when it vendors a section: the
# title and the leading summary blockquote stay visible, everything after
# collapses so agents expand the detail on demand.
DETAILS_SUMMARY = "<summary>詳細解説を展開（事実・判例・禁止パターン・制度変更ウォッチ）</summary>"

_HEADER_RE = re.compile(r"\A\{#\s*ethics:(?P<body>.*?)#\}", re.DOTALL)
_FIELD_RE = re.compile(r"(\w+)=(\[.*?\]|\S+)", re.DOTALL)


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

    def applies(self, conditions: Iterable[str]) -> bool:
        """Whether the section lands in AGENTS.md for a project declaring ``conditions``."""
        wanted = {"always", *conditions}
        return self.status == "active" and self.placement == "agents_md" and bool(wanted & set(self.when))


def kanon_sha() -> str:
    """The kanon commit this law-lint build vendors."""
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
            )
        )
    return sections


def select_sections(conditions: Iterable[str], sections: Iterable[Section] | None = None) -> list[Section]:
    """The sections that apply to a project declaring ``conditions``."""
    conditions = list(conditions)
    pool = load_sections() if sections is None else sections
    return [section for section in pool if section.applies(conditions)]


def fold(body: str) -> str:
    """Collapse everything after the title and summary blockquote into ``<details>``."""
    lines = body.split("\n")
    i = 0
    while i < len(lines) and not lines[i].startswith(">"):
        i += 1
    while i < len(lines) and lines[i].startswith(">"):
        i += 1
    head = "\n".join(lines[:i])
    rest = "\n".join(lines[i:]).strip("\n")
    return f"{head}\n\n\n<details>\n{DETAILS_SUMMARY}\n\n{rest}\n\n</details>\n"


def render_block(conditions: Iterable[str], sections: Iterable[Section] | None = None, sha: str | None = None) -> str:
    """The marker-delimited ethics block ``agents-md`` writes into AGENTS.md."""
    conditions = sorted(set(conditions) - {"always"})
    chosen = select_sections(conditions, sections)
    sha = kanon_sha() if sha is None else sha
    when = ",".join(["always", *conditions])
    lines = [
        f"{BEGIN_MARKER} kanon={sha[:12]} when={when} -->",
        "<!-- Generated by `law-lint agents-md --write` from good-future-codex; edit .daimonion.yml, not this block. -->",
        "",
        "## Ethics & legal field rules",
        "",
        "Sections from [good-future-codex](https://github.com/ConstitutiveTemplates/good-future-codex)",
        "that match this project's `.daimonion.yml` conditions. Each gives a rule summary and regex",
        "triggers up front; facts, prohibited patterns, and the change watch are folded in `<details>`.",
        "Before committing, run `law-lint diff` to match changed lines against these triggers.",
        "Sections are written in Japanese. Not legal advice.",
        "",
    ]
    block = "\n".join(lines) + "\n" + "\n".join(fold(section.body) for section in chosen)
    return block + END_MARKER + "\n"


def _block_span(document: str) -> tuple[int, int] | None:
    """Start/end offsets of the ethics block (end past its trailing newline), or None."""
    start = document.find(BEGIN_MARKER)
    if start == -1:
        return None
    end = document.find(END_MARKER, start)
    if end == -1:
        msg = f"found {BEGIN_MARKER!r} without a matching {END_MARKER!r}"
        raise ValueError(msg)
    end += len(END_MARKER)
    if document[end : end + 1] == "\n":
        end += 1
    return start, end


def splice_block(document: str, block: str) -> str:
    """Replace the existing ethics block in ``document``, or append one after a blank line."""
    span = _block_span(document)
    if span is None:
        return block if not document.strip() else document.rstrip("\n") + "\n\n" + block
    start, end = span
    return document[:start] + block + document[end:]


def extract_block(document: str) -> str | None:
    """The ethics block currently in ``document`` (markers included), if any."""
    span = _block_span(document)
    return None if span is None else document[span[0] : span[1]]
