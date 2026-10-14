"""`.daimonion.yml`, `daimonion init` detection, and `daimonion agents-md` end to end."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from daimonion import kanon
from daimonion.cli import main
from daimonion.config import ConfigError, load_config
from daimonion.detect import detect, render_config


def _config(root: Path, text: str) -> Path:
    path = root / ".daimonion.yml"
    path.write_text(text, encoding="utf-8")
    return path


# --- .daimonion.yml -----------------------------------------------------------


def test_load_config_reads_conditions_and_guide_file(tmp_path):
    config = load_config(_config(tmp_path, "version: 1\nagents_md: CLAUDE.md\nwhen: [jp, scraping, jp]\n"))
    assert config.when == ("jp", "scraping")
    assert config.agents_md_path == tmp_path / "CLAUDE.md"


def test_load_config_allows_empty_when(tmp_path):
    assert load_config(_config(tmp_path, "version: 1\nwhen:\n")).when == ()


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("when: [jp]\n", "version"),
        ("version: 1\nwhen: [scrapping]\n", "unknown `when` condition"),
        ("version: 1\nwhen: jp\n", "must be a list"),
        ("version: 1\nagents_md: ../outside.md\n", "relative path inside"),
        ("- just a list\n", "expected a mapping"),
    ],
)
def test_load_config_rejects_malformed_files(tmp_path, text, message):
    with pytest.raises(ConfigError, match=message):
        load_config(_config(tmp_path, text))


# --- detection ---------------------------------------------------------------


def test_detect_reads_every_ecosystem(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["FastAPI>=0.110", "pandas"]\n'
        '[dependency-groups]\ndev = ["pytest", {include-group = "x"}]\n',
        encoding="utf-8",
    )
    (tmp_path / "requirements-scrape.txt").write_text("scrapy==2.11  # crawler\n-r base.txt\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({"devDependencies": {"@modelcontextprotocol/sdk": "1"}}))
    (tmp_path / "Cargo.toml").write_text('[dependencies]\naxum = "0.7"\n', encoding="utf-8")
    (tmp_path / "go.mod").write_text("module x\n\nrequire (\n\tgithub.com/gocolly/colly/v2 v2.1.0\n)\n")
    (tmp_path / "AGENTS.md").write_text("# guide\n", encoding="utf-8")

    found = {(s.condition, s.source, s.detail) for s in detect(tmp_path)}
    assert ("web_api", "pyproject.toml", "depends on fastapi") in found
    assert ("data_science", "pyproject.toml", "depends on pandas") in found
    assert ("scraping", "requirements-scrape.txt", "depends on scrapy") in found
    assert ("mcp", "package.json", "depends on @modelcontextprotocol/sdk") in found
    assert ("web_api", "Cargo.toml", "depends on axum") in found
    assert ("scraping", "go.mod", "depends on github.com/gocolly/colly/v2") in found
    assert ("ai_assisted", "AGENTS.md", "AI agent instructions present") in found


def test_detect_finds_notebooks_but_skips_vendored_dirs(tmp_path):
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "demo.ipynb").write_text("{}")
    assert detect(tmp_path) == []
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "notebooks" / "eda.ipynb").write_text("{}")
    assert [(s.condition, s.source) for s in detect(tmp_path)] == [("data_science", "notebooks/eda.ipynb")]


def test_rendered_config_round_trips_through_the_loader(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"puppeteer": "22"}}))
    path = _config(tmp_path, render_config(detect(tmp_path)))
    config = load_config(path)
    assert config.when == ("scraping",)
    assert "#  - jp" in path.read_text(encoding="utf-8")


# --- CLI ---------------------------------------------------------------------


def test_init_prints_without_writing_and_refuses_to_overwrite(tmp_path, capsys):
    assert main(["init", "--repo", str(tmp_path)]) == 0
    assert "version: 1" in capsys.readouterr().out
    assert not (tmp_path / ".daimonion.yml").exists()

    assert main(["init", "--repo", str(tmp_path), "--write"]) == 0
    assert main(["init", "--repo", str(tmp_path), "--write"]) == 2
    assert main(["init", "--repo", str(tmp_path), "--write", "--force"]) == 0


def test_init_targets_claude_md_when_it_is_the_only_guide(tmp_path, capsys):
    (tmp_path / "CLAUDE.md").write_text("# guide\n", encoding="utf-8")
    assert main(["init", "--repo", str(tmp_path), "--write"]) == 0
    assert load_config(tmp_path / ".daimonion.yml").agents_md == "CLAUDE.md"


def test_agents_md_write_check_cycle(tmp_path, capsys):
    _config(tmp_path, "version: 1\nwhen: [scraping]\n")
    guide = tmp_path / "AGENTS.md"
    guide.write_text("# Guide\n\nproject notes\n", encoding="utf-8")

    assert main(["agents-md", "--repo", str(tmp_path), "--check"]) == 1
    assert "is missing" in capsys.readouterr().err

    assert main(["agents-md", "--repo", str(tmp_path), "--write"]) == 0
    text = guide.read_text(encoding="utf-8")
    assert text.startswith("# Guide\n\nproject notes\n\n")
    assert text.count(kanon.BEGIN_MARKER) == 1
    scraping = next(s for s in kanon.load_sections() if s.id == "domain-scraping-law")
    assert f"### {scraping.title}" in text
    assert main(["agents-md", "--repo", str(tmp_path), "--check"]) == 0

    # A second write is a no-op; a condition change makes the block stale.
    assert main(["agents-md", "--repo", str(tmp_path), "--write"]) == 0
    assert guide.read_text(encoding="utf-8") == text
    _config(tmp_path, "version: 1\nwhen: []\n")
    capsys.readouterr()
    assert main(["agents-md", "--repo", str(tmp_path), "--check"]) == 1
    assert "is stale" in capsys.readouterr().err


def test_agents_md_creates_missing_guide_and_prints_by_default(tmp_path, capsys):
    _config(tmp_path, "version: 1\nagents_md: docs/AGENTS.md\nwhen: []\n")
    assert main(["agents-md", "--repo", str(tmp_path)]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith(kanon.BEGIN_MARKER)
    assert not (tmp_path / "docs").exists()

    assert main(["agents-md", "--repo", str(tmp_path), "--write"]) == 0
    assert (tmp_path / "docs" / "AGENTS.md").read_text(encoding="utf-8") == printed


@pytest.mark.parametrize("config", [None, "version: 2\n"])
def test_agents_md_config_errors_exit_2(tmp_path, capsys, config):
    if config is not None:
        _config(tmp_path, config)
    assert main(["agents-md", "--repo", str(tmp_path), "--check"]) == 2


def test_agents_md_migrates_a_legacy_ethics_block(tmp_path, capsys):
    _config(tmp_path, "version: 1\nwhen: []\n")
    guide = tmp_path / "AGENTS.md"
    legacy = f"{kanon.LEGACY_BEGIN_MARKER} kanon=old -->\nold prose\n{kanon.LEGACY_END_MARKER}\n"
    guide.write_text(f"# Guide\n\n{legacy}\n## Mine\n", encoding="utf-8")

    assert main(["agents-md", "--repo", str(tmp_path), "--check"]) == 1
    assert "is stale" in capsys.readouterr().err
    assert main(["agents-md", "--repo", str(tmp_path), "--write"]) == 0
    text = guide.read_text(encoding="utf-8")
    assert kanon.LEGACY_BEGIN_MARKER not in text and "old prose" not in text
    assert text.startswith(f"# Guide\n\n{kanon.BEGIN_MARKER}") and text.endswith(f"{kanon.END_MARKER}\n\n## Mine\n")
    assert main(["agents-md", "--repo", str(tmp_path), "--check"]) == 0
