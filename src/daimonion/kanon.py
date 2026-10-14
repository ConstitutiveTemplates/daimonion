"""Backwards-compatible alias for :mod:`daimonion.rulebook`.

The vendored snapshot moved from ``kanon/`` (the archived kanon repo) to
``rulebook/`` (law-map's ``guidance/sections/`` plus ``checks/``). Import
:mod:`daimonion.rulebook` in new code; this module keeps the old import
path and the names its tests used working.
"""

from __future__ import annotations

from daimonion.rulebook import (  # noqa: F401
    BEGIN_MARKER,
    END_MARKER,
    LEGACY_BEGIN_MARKER,
    LEGACY_END_MARKER,
    RULEBOOK_GUIDANCE_PATH,
    RULEBOOK_REPO_URL,
    RULEBOOK_ROOT,
    WHEN_VOCABULARY,
    Section,
    extract_block,
    load_sections,
    render_block,
    render_rule,
    select_sections,
    splice_block,
)

KANON_ROOT = RULEBOOK_ROOT
KANON_REPO_URL = RULEBOOK_REPO_URL


def kanon_sha() -> str:
    """The vendored law-map commit (kept under the old name)."""
    from daimonion.rulebook import lawmap_sha

    return lawmap_sha()


def parse_header(text: str) -> tuple[dict[str, object], str]:
    """Split a section file into front-matter fields and the prose body (old name)."""
    from daimonion.rulebook import parse_front_matter

    fields, body = parse_front_matter(text)
    return fields, body
