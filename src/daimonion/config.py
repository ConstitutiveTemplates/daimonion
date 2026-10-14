"""``.daimonion.yml``: a project's declared conditions, independent of any template.

The file speaks the kanon's abstract ``when`` vocabulary, so a hand-written
config and one a template generator emits look the same and take the same
path through daimonion::

    version: 1
    agents_md: AGENTS.md      # where `agents-md --write` puts the ethics block
    when:                     # kanon conditions that hold; `always` is implied
      - scraping
      - jp
    mode: adoption            # optional: `adoption` (warn-only, nothing fails) or `strict`
    scan:
      docs: true              # optional: also scan .md/.yml/.yaml/.toml (default: source only)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from daimonion.kanon import WHEN_VOCABULARY

CONFIG_NAME = ".daimonion.yml"
CONFIG_VERSION = 1
#: Values ``mode`` accepts: ``adoption`` reports without failing, even under
#: ``--strict``; ``strict`` fails on L2 findings without passing ``--strict``.
MODES = ("adoption", "strict")


class ConfigError(ValueError):
    """``.daimonion.yml`` is missing, malformed, or uses an unknown condition."""


@dataclass(frozen=True)
class ProjectConfig:
    """The validated contents of ``.daimonion.yml``."""

    path: Path
    when: tuple[str, ...]
    agents_md: str = "AGENTS.md"
    mode: str = ""
    scan_docs: bool = False

    @property
    def agents_md_path(self) -> Path:
        return self.path.parent / self.agents_md


def find_config(repo: str | Path) -> Path | None:
    """``.daimonion.yml`` under ``repo``, if present."""
    candidate = Path(repo) / CONFIG_NAME
    return candidate if candidate.is_file() else None


def load_config(path: str | Path) -> ProjectConfig:
    """Parse and validate a ``.daimonion.yml``."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        msg = f"{path}: cannot read: {exc}"
        raise ConfigError(msg) from exc
    if not isinstance(data, dict):
        msg = f"{path}: expected a mapping"
        raise ConfigError(msg)
    if data.get("version") != CONFIG_VERSION:
        msg = f"{path}: `version` must be {CONFIG_VERSION}"
        raise ConfigError(msg)

    when = data.get("when") or []
    if not isinstance(when, list) or not all(isinstance(item, str) for item in when):
        msg = f"{path}: `when` must be a list of condition names"
        raise ConfigError(msg)
    unknown = sorted(set(when) - set(WHEN_VOCABULARY))
    if unknown:
        msg = f"{path}: unknown `when` condition(s): {', '.join(unknown)} (known: {', '.join(WHEN_VOCABULARY)})"
        raise ConfigError(msg)

    agents_md = data.get("agents_md", "AGENTS.md")
    if (
        not isinstance(agents_md, str)
        or not agents_md
        or Path(agents_md).is_absolute()
        or ".." in Path(agents_md).parts
    ):
        msg = f"{path}: `agents_md` must be a relative path inside the project"
        raise ConfigError(msg)

    mode = data.get("mode") or ""
    if mode and mode not in MODES:
        msg = f"{path}: `mode` must be one of {', '.join(MODES)}"
        raise ConfigError(msg)

    scan = data.get("scan") or {}
    if not isinstance(scan, dict) or not isinstance(scan.get("docs", False), bool):
        msg = f"{path}: `scan` must be a mapping whose `docs` is true or false"
        raise ConfigError(msg)

    return ProjectConfig(
        path=path,
        when=tuple(dict.fromkeys(when)),
        agents_md=agents_md,
        mode=mode,
        scan_docs=scan.get("docs", False),
    )
