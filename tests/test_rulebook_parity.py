"""Fixture-based unit tests for tools/check_rulebook_parity.py (offline)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

TOOLS_SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "check_rulebook_parity.py"


def load_script():
    spec = importlib.util.spec_from_file_location("check_rulebook_parity", TOOLS_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_section(root: Path, rel: str, front: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front}---\n# Title\n\n> 要約: (1)first item\n", encoding="utf-8")


FRONT = (
    "id: baseline-a\nversion: '1'\nstatus: active\nplacement: agents_md\nwhen: always\npack: core\n"
    "obligations: [obligation.x.y]\ntriggers:\n  keywords: ['md5']\n  pattern: '(?i)md5'\n"
    "sources: ['https://example.org/law']\nlicense: CC-BY-4.0\n"
    "en:\n  title: 'Rule A'\n  summary: ['Do x.']\n"
)


def _write_project(root: Path, *, manifest_extra: str = "", spec_extra: str = "") -> tuple[Path, Path]:
    sections = root / "guidance" / "sections"
    _write_section(sections, "baseline/a.md", FRONT)
    (sections / "MANIFEST.yml").write_text(
        "schema: 2\nsections:\n"
        "  - id: baseline-a\n    file: baseline/a.md\n    when: always\n    pack: core\n"
        "    status: active\n    placement: agents_md\n    obligations: [obligation.x.y]\n"
        "    triggers:\n      keywords: ['md5']\n      pattern: '(?i)md5'\n" + manifest_extra,
        encoding="utf-8",
    )
    (sections / "VOCABULARY.yml").write_text("extensions: {}\n", encoding="utf-8")
    checks = root / "checks"
    (checks / "x").mkdir(parents=True)
    (checks / "x" / "a.yml").write_text(
        "id: x/a\nobligation: obligation.x.y\nlevel: L1\ntriggers: ['(?i)md5']\n" + spec_extra,
        encoding="utf-8",
    )
    obligations = root / "obligations" / "x"
    obligations.mkdir(parents=True)
    (obligations / "y.yml").write_text(
        "version: 2\nid: obligation.x.y\ntitle: 'Rule Y'\ncategory: x\nmodality: prohibition\n"
        "summary: 'Do x.'\ngroundings:\n"
        "  - jurisdiction: EU\n    source_type: regulation\n    source_kind: primary\n"
        "    status: in_force\n    authority: 'Example regulation'\n"
        "    strength: binding\n    sources: ['https://example.org/law']\n",
        encoding="utf-8",
    )
    return root, checks


def _run(module, root: Path, capsys) -> tuple[int, str]:
    rc = module.main(["--lawmap", str(root)])
    return rc, capsys.readouterr().out


def test_happy_path(tmp_path, capsys):
    """A section whose front matter, manifest row, and spec triggers agree passes."""
    module = load_script()
    root, _ = _write_project(tmp_path)
    rc, out = _run(module, root, capsys)
    assert rc == 0, out
    assert "OK   baseline-a" in out
    assert "OK   x/a" in out
    assert "OK   obligation.x.y: strengths=binding" in out


def test_missing_obligation_file_fails(tmp_path, capsys):
    """A section naming an obligation with no vendored file fails."""
    import shutil

    module = load_script()
    root, _ = _write_project(tmp_path)
    shutil.rmtree(tmp_path / "obligations")
    rc, out = _run(module, root, capsys)
    assert rc == 1
    assert "vendored obligation x/y.yml unreadable" in out


def test_obligation_without_strengths_fails(tmp_path, capsys):
    """An obligation file with no grounding strengths fails (tiers need them)."""
    module = load_script()
    root, _ = _write_project(tmp_path)
    obl = tmp_path / "obligations" / "x" / "y.yml"
    obl.write_text(
        "version: 2\nid: obligation.x.y\ntitle: 'Rule Y'\ncategory: x\nmodality: prohibition\n"
        "summary: 'Do x.'\ngroundings:\n"
        "  - jurisdiction: EU\n    source_type: regulation\n    source_kind: primary\n"
        "    status: in_force\n    authority: 'Example regulation'\n"
        "    sources: ['https://example.org/law']\n",
        encoding="utf-8",
    )
    rc, out = _run(module, root, capsys)
    assert rc == 1
    assert "has no grounding strengths" in out


def test_stale_manifest_triggers_fail(tmp_path, capsys):
    """A manifest row disagreeing with the front matter fails (run `just manifest`)."""
    module = load_script()
    _write_project(tmp_path, manifest_extra="    version: stale\n")
    _write_section(
        tmp_path / "guidance" / "sections",
        "baseline/b.md",
        FRONT.replace("id: baseline-a", "id: baseline-b").replace("pack: core", "pack: core"),
    )
    manifest = tmp_path / "guidance" / "sections" / "MANIFEST.yml"
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(
        text.replace("pattern: '(?i)md5'", "pattern: '(?i)sha1'").replace("keywords: ['md5']", "keywords: ['sha1']"),
        encoding="utf-8",
    )
    rc, out = _run(module, tmp_path, capsys)
    assert rc == 1
    assert "disagrees with the front matter" in out


def test_active_section_without_en_fails(tmp_path, capsys):
    """An active section with no usable `en:` block fails."""
    module = load_script()
    root, _ = _write_project(tmp_path)
    _write_section(
        tmp_path / "guidance" / "sections",
        "baseline/a.md",
        FRONT.replace("en:\n  title: 'Rule A'\n  summary: ['Do x.']\n", ""),
    )
    rc, out = _run(module, root, capsys)
    assert rc == 1
    assert "lacks a usable `en:`" in out


def test_unknown_pack_fails(tmp_path, capsys):
    """A manifest row naming a pack outside VOCABULARY.yml fails."""
    module = load_script()
    root, _ = _write_project(tmp_path)
    manifest = tmp_path / "guidance" / "sections" / "MANIFEST.yml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace("pack: core", "pack: arcade"), encoding="utf-8")
    rc, out = _run(module, root, capsys)
    assert rc == 1
    assert "not a known pack" in out


def test_l2_without_blocking_or_fixtures_fails(tmp_path, capsys):
    """An L2 spec without `blocking` and `fixtures` fails."""
    module = load_script()
    root, _ = _write_project(tmp_path, spec_extra="level: L2\n")
    spec = tmp_path / "checks" / "x" / "a.yml"
    spec.write_text(spec.read_text(encoding="utf-8").replace("level: L1", "level: L2"), encoding="utf-8")
    rc, out = _run(module, root, capsys)
    assert rc == 1
    assert "must carry `blocking` and `fixtures`" in out


def test_vendored_snapshot_is_in_parity(capsys):
    """The vendored rulebook snapshot agrees with its own contracts (the default inputs)."""
    module = load_script()
    assert module.main([]) == 0, capsys.readouterr().out
