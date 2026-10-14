"""Suggest kanon ``when`` conditions from what a repository already contains.

``daimonion init`` proposes, it does not decide: every suggestion carries the
file and dependency it came from, and the conditions no file can reveal
(commercial distribution, target markets, governing law) are always left to
the user. Only the repository root's manifests are read -- no network, no
lockfile resolution.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: One-line meaning of each condition (kanon MANIFEST.yml).
WHEN_DESCRIPTIONS: dict[str, str] = {
    "library": "a library / API package project",
    "cli": "a command-line / terminal tool project",
    "embedded": "an embedded / microcontroller project",
    "scraping": "the project fetches the web (any engine)",
    "oj_code": "a code-submission judge workspace",
    "kaggle": "a kaggle (data competition) workspace",
    "mcp": "the project ships an MCP server",
    "data_science": "a data-science / kaggle layout",
    "web_api": "an HTTP API project",
    "personal_data": "the project processes personal data",
    "face_recognition": "the project does biometric identification",
    "medtech": "the project is medical / SaMD software",
    "commercial": "distributed as a commercial product",
    "eu_market": "shipped to the EU market",
    "jp": "operated under Japanese law",
    "ai_assisted": "AI coding agents work in this repository",
}

#: Conditions a repository's files cannot reveal; init always asks about these.
UNDETECTABLE: tuple[str, ...] = (
    "embedded",
    "personal_data",
    "face_recognition",
    "medtech",
    "commercial",
    "eu_market",
    "jp",
)

#: Dependency names that signal a condition, across ecosystems. Go module
#: paths match by prefix (major-version suffixes like ``/v2`` vary).
DEPENDENCY_SIGNALS: dict[str, frozenset[str]] = {
    "scraping": frozenset(
        {
            # Python
            "scrapy",
            "beautifulsoup4",
            "bs4",
            "playwright",
            "selenium",
            "crawlee",
            "trafilatura",
            # JavaScript
            "puppeteer",
            "cheerio",
            "@crawlee/core",
            # Rust
            "scraper",
            "spider",
            # Go
            "github.com/gocolly/colly",
            "github.com/PuerkitoBio/goquery",
        }
    ),
    "mcp": frozenset({"mcp", "fastmcp", "@modelcontextprotocol/sdk", "rmcp", "github.com/mark3labs/mcp-go"}),
    "data_science": frozenset(
        {
            "pandas",
            "polars",
            "numpy",
            "scikit-learn",
            "torch",
            "tensorflow",
            "jupyter",
            "jupyterlab",
            "notebook",
        }
    ),
    "web_api": frozenset(
        {
            # Python
            "fastapi",
            "flask",
            "django",
            "starlette",
            "litestar",
            "aiohttp",
            # JavaScript
            "express",
            "fastify",
            "hono",
            "koa",
            "@nestjs/core",
            "next",
            # Rust
            "axum",
            "actix-web",
            "rocket",
            "warp",
            # Go
            "github.com/gin-gonic/gin",
            "github.com/labstack/echo",
            "github.com/go-chi/chi",
            "github.com/gofiber/fiber",
        }
    ),
    "oj_code": frozenset({"online-judge-tools", "online-judge-api-client", "ac-library-python", "atcoder-cli"}),
    "kaggle": frozenset({"kaggle"}),
}

#: Files whose presence means AI coding agents already work in the repository.
AI_ASSISTANT_FILES: tuple[str, ...] = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".cursorrules",
    ".cursor",
    ".github/copilot-instructions.md",
)

_SKIP_DIRS = frozenset({".git", ".venv", "venv", "node_modules", "target", "dist", "build", "__pycache__"})
_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


@dataclass(frozen=True)
class Signal:
    """One reason to suggest a condition."""

    condition: str
    source: str
    detail: str


def _normalize(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _requirement_name(spec: str) -> str | None:
    """The distribution name in a PEP 508 requirement string."""
    match = _NAME_RE.match(spec)
    return _normalize(match.group(1)) if match else None


def _toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _pyproject_deps(path: Path) -> Iterator[str]:
    data = _toml(path)
    project = data.get("project", {})
    specs: list[Any] = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        specs.extend(group)
    for group in data.get("dependency-groups", {}).values():
        specs.extend(item for item in group if isinstance(item, str))
    for spec in specs:
        if isinstance(spec, str) and (name := _requirement_name(spec)):
            yield name
    poetry = data.get("tool", {}).get("poetry", {})
    yield from (_normalize(name) for name in poetry.get("dependencies", {}))
    for group in poetry.get("group", {}).values():
        yield from (_normalize(name) for name in group.get("dependencies", {}))


def _manifest_signals(repo: Path) -> Iterator[Signal]:
    """Conditions that a manifest's own metadata (not dependencies) reveals."""
    data = _toml(repo / "pyproject.toml") if (repo / "pyproject.toml").is_file() else {}
    project = data.get("project", {})
    if project.get("scripts") or project.get("gui-scripts"):
        yield Signal("cli", "pyproject.toml", "declares a console/GUI script")
    if (repo / "package.json").is_file():
        try:
            pkg = json.loads((repo / "package.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pkg = {}
        if pkg.get("bin"):
            yield Signal("cli", "package.json", "declares a bin entry")


def _requirements_deps(path: Path) -> Iterator[str]:
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-") and (name := _requirement_name(line)):
            yield name


def _package_json_deps(path: Path) -> Iterator[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        section = data.get(key, {})
        if isinstance(section, dict):
            yield from (name.lower() for name in section)


def _cargo_deps(path: Path) -> Iterator[str]:
    data = _toml(path)
    for key in ("dependencies", "dev-dependencies", "build-dependencies"):
        yield from (_normalize(name) for name in data.get(key, {}))
    yield from (_normalize(name) for name in data.get("workspace", {}).get("dependencies", {}))


def _go_mod_deps(path: Path) -> Iterator[str]:
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.strip().removeprefix("require").strip().split()
        if parts and "." in parts[0] and "/" in parts[0]:
            yield parts[0]


def dependencies(repo: Path) -> Iterator[tuple[str, str]]:
    """``(manifest file, dependency name)`` pairs from the repository root's manifests."""
    readers = {
        "pyproject.toml": _pyproject_deps,
        "package.json": _package_json_deps,
        "Cargo.toml": _cargo_deps,
        "go.mod": _go_mod_deps,
    }
    for name, reader in readers.items():
        if (repo / name).is_file():
            yield from ((name, dep) for dep in reader(repo / name))
    for requirements in sorted(repo.glob("requirements*.txt")):
        yield from ((requirements.name, dep) for dep in _requirements_deps(requirements))


def _matches(dep: str, signals: frozenset[str]) -> bool:
    if dep in signals:
        return True
    return any(signal.startswith("github.com/") and dep.startswith(signal) for signal in signals)


def _has_notebook(repo: Path, max_depth: int = 3) -> Path | None:
    stack = [(repo, 0)]
    while stack:
        directory, depth = stack.pop()
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_file() and entry.suffix == ".ipynb":
                return entry
            if entry.is_dir() and depth < max_depth and entry.name not in _SKIP_DIRS:
                stack.append((entry, depth + 1))
    return None


def detect(repo: str | Path) -> list[Signal]:
    """Every signal found, grouped in vocabulary order (one entry per evidence)."""
    repo = Path(repo)
    signals: list[Signal] = []
    seen: set[tuple[str, str, str]] = set()
    for source, dep in dependencies(repo):
        for condition, names in DEPENDENCY_SIGNALS.items():
            key = (condition, source, dep)
            if _matches(dep, names) and key not in seen:
                seen.add(key)
                signals.append(Signal(condition, source, f"depends on {dep}"))
    signals.extend(_manifest_signals(repo))
    notebook = _has_notebook(repo)
    if notebook is not None:
        signals.append(Signal("data_science", notebook.relative_to(repo).as_posix(), "Jupyter notebook"))
    for name in AI_ASSISTANT_FILES:
        if (repo / name).exists():
            signals.append(Signal("ai_assisted", name, "AI agent instructions present"))
    order = list(WHEN_DESCRIPTIONS)
    return sorted(signals, key=lambda s: order.index(s.condition))


def default_agents_md(repo: str | Path) -> str:
    """The guide file to write into: AGENTS.md, unless only CLAUDE.md exists."""
    repo = Path(repo)
    if not (repo / "AGENTS.md").exists() and (repo / "CLAUDE.md").is_file():
        return "CLAUDE.md"
    return "AGENTS.md"


def render_config(signals: list[Signal], agents_md: str = "AGENTS.md") -> str:
    """A commented ``.daimonion.yml`` with detected conditions on and the rest commented out."""
    detected: dict[str, list[Signal]] = {}
    for signal in signals:
        detected.setdefault(signal.condition, []).append(signal)
    width = max(len(name) for name in WHEN_DESCRIPTIONS)
    lines = [
        "# daimonion project conditions, in kanon's `when` vocabulary.",
        "# `daimonion agents-md --write` renders the matching rules into",
        "# the guide file below; `always` sections apply without being listed.",
        "version: 1",
        f"agents_md: {agents_md}",
        "when:",
    ]
    for condition in WHEN_DESCRIPTIONS:
        if condition in detected:
            evidence = "; ".join(f"{s.source}: {s.detail}" for s in detected[condition][:3])
            lines.append(f"  - {condition.ljust(width)}  # detected -- {evidence}")
    lines.append("# Not detected -- uncomment the ones that hold for this project:")
    for condition, description in WHEN_DESCRIPTIONS.items():
        if condition not in detected:
            lines.append(f"#  - {condition.ljust(width)}  # {description}")
    lines += [
        "# Scanning (`daimonion check` / `diff`):",
        "# mode: adoption   # warn-only while adopting: nothing fails, even with --strict",
        "# scan:",
        "#   docs: true     # also scan .md/.yml/.yaml/.toml (default: source code only)",
    ]
    return "\n".join(lines) + "\n"
