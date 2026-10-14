"""``.daimonion.yml``: a project's declared conditions, independent of any template.

The file speaks the kanon's abstract ``when`` vocabulary, so a hand-written
config and one a template generator emits look the same and take the same
path through law-lint::

    version: 1
    agents_md: AGENTS.md      # where `agents-md --write` puts the ethics block
    when:                     # kanon conditions that hold; `always` is implied
      - scraping
      - jp
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from law_lint.kanon import WHEN_VOCABULARY

CONFIG_NAME = ".daimonion.yml"
CONFIG_VERSION = 1


class ConfigError(ValueError):
    """``.daimonion.yml`` is missing, malformed, or uses an unknown condition."""


@dataclass(frozen=True)
class ProjectConfig:
    """The validated contents of ``.daimonion.yml``."""

    path: Path
    when: tuple[str, ...]
    agents_md: str = "AGENTS.md"

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

    return ProjectConfig(path=path, when=tuple(dict.fromkeys(when)), agents_md=agents_md)
