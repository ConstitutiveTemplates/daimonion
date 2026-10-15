"""Fail loudly when the vendored rulebook drifts from its own contracts.

The vendored ``rulebook/sections/MANIFEST.yml`` (schema 2) is the canonical
list of sections. Each row carries ``pack``, ``obligations``, and
``triggers`` (keywords/pattern/config); each section file carries YAML
front matter plus an ``en:`` block. By default the check reads the snapshot
vendored into this package; pass an upstream law-map checkout to catch
drift before re-vendoring::

    python tools/check_rulebook_parity.py
    python tools/check_rulebook_parity.py --lawmap ../law-map

The check verifies, per section:

- the front matter has ``id`` (matching the manifest row and the
  ``<tier>/<slug>.md`` path), ``version``, ``status``, ``placement``,
  ``when``, ``pack``, ``obligations``, ``triggers`` (keywords + pattern),
  ``sources``, and ``license: CC-BY-4.0``;
- an ``active`` section has a non-empty ``en:`` title and summary
  (``agents-md --lang en`` renders them);
- the row's ``pack`` matches the law-map pack contract (``core`` or a
  known extension pack from ``VOCABULARY.yml``);
- the front-matter triggers agree with the row's triggers (the manifest
  is generated from the front matter — disagreement means a stale
  MANIFEST.yml; run ``just manifest`` in law-map);

and, per vendored check spec (``rulebook/checks/<domain>/<slug>.yml``):

- the spec has ``id``, ``obligation``, and ``level``;
- an ``L2`` spec carries ``blocking`` and ``fixtures`` (only structural
  gates — AST/semgrep/dep/license — may block; keyword matchers stay L1);
- the spec's trigger regex agrees (``>= 3`` shared probes) with the
  front-matter pattern of at least one section serving the same
  obligation, when both exist.

Exit 0 when everything agrees; exit 1 with a per-item report otherwise.

Only ``pyyaml`` plus the standard library is used. Rule ids are read from
the vendored snapshot without importing ``daimonion``, so the script stays
runnable even when ``daimonion`` itself is not installed.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

MANIFEST_SCHEMA = 2
SECTION_LICENSE = "CC-BY-4.0"

FRONT_MATTER_RE = re.compile(r"\A---\n(?P<head>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)
LOOKAROUND_RE = re.compile(r"\(\?[<!=][^()]*\)")
FLAG_RE = re.compile(r"\(\?[a-zA-Z]+[-+]?[a-zA-Z]*\)")
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*")


def _default_root() -> Path:
    """The rulebook snapshot vendored into this checkout."""
    return Path(__file__).resolve().parent.parent / "src" / "daimonion" / "rulebook"


def _read_yaml(path: Path) -> tuple[dict | None, str | None]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return None, f"cannot read {path}: {exc}"
    if not isinstance(data, dict):
        return None, f"{path}: expected a mapping"
    return data, None


def _split_section(text: str) -> tuple[dict | None, str, str | None]:
    """Front matter, body, and an error message for a section file."""
    match = FRONT_MATTER_RE.match(text)
    if match is None:
        return None, "", "section file has no YAML front matter"
    try:
        front = yaml.safe_load(match.group("head"))
    except yaml.YAMLError as exc:
        return None, "", f"front matter does not parse: {exc}"
    if not isinstance(front, dict):
        return None, "", "front matter is not a mapping"
    return front, match.group("body"), None


def _probes_from_pattern(pattern: str) -> list[str]:
    """Candidate probe words from a trigger regex."""
    scrubbed = LOOKAROUND_RE.sub("", pattern)
    scrubbed = FLAG_RE.sub("", scrubbed)
    words = WORD_RE.findall(scrubbed)
    seen: list[str] = []
    for word in words:
        lowered = word.lower()
        if len(lowered) >= 3 and lowered not in seen:
            seen.append(lowered)
    return seen[:12]


def _packs_from_vocabulary(root: Path) -> tuple[set[str], str | None]:
    """Known pack names (``core`` plus the extension packs)."""
    vocab_path = root / "sections" / "VOCABULARY.yml"
    try:
        vocab = yaml.safe_load(vocab_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return set(), f"cannot read {vocab_path}: {exc}"
    packs = {"core"}
    extensions = (vocab or {}).get("extensions")
    if isinstance(extensions, dict):
        packs |= set(extensions)
    return packs, None


def _check_section(
    row: dict, front: dict, packs: set[str], obligations: dict[str, list[str]]
) -> tuple[list[str], bool]:
    """Check one manifest row against its section file; returns (report lines, failed)."""
    lines: list[str] = []
    failed = False
    section_id = str(row.get("id", ""))
    rel = str(row.get("file", ""))

    def _fail(message: str) -> None:
        lines.append(f"FAIL {section_id}: {message}")

    def _note(message: str) -> None:
        lines.append(f"NOTE {section_id}: {message}")

    # Identity: id matches the row, the path, and the front matter.
    tier_slug = rel.removesuffix(".md").replace("/", "-")
    if section_id != tier_slug:
        _fail(f"manifest id {section_id!r} does not match path {rel!r} (expected {tier_slug!r})")
        failed = True
    if front.get("id") != section_id:
        _fail(f"front-matter id {front.get('id')!r} does not match manifest id {section_id!r}")
        failed = True

    # Required front-matter fields.
    for field in ("version", "status", "placement", "when", "obligations", "triggers", "sources", "license"):
        if front.get(field) in (None, "", [], {}):
            _fail(f"front matter lacks {field!r}")
            failed = True
    if front.get("license") not in (None, SECTION_LICENSE) and front.get("license") != SECTION_LICENSE:
        _fail(f"license is {front.get('license')!r}, expected {SECTION_LICENSE!r}")
        failed = True
    status = front.get("status")
    if status not in ("draft", "active"):
        _fail(f"status is {status!r}, expected 'draft' or 'active'")
        failed = True
    if str(row.get("status")) != str(status):
        _fail(f"manifest status {row.get('status')!r} disagrees with front matter {status!r}")
        failed = True
    if str(row.get("placement", "agents_md")) != str(front.get("placement", "agents_md")):
        _fail("manifest placement disagrees with front matter")
        failed = True

    # Pack contract.
    pack = str(row.get("pack", "core"))
    if pack not in packs:
        _fail(f"pack {pack!r} is not a known pack ({', '.join(sorted(packs))})")
        failed = True
    elif front.get("pack", pack) != pack:
        _fail(f"front-matter pack {front.get('pack')!r} disagrees with manifest pack {pack!r}")
        failed = True

    # English rendering: active sections need a usable ``en:`` block.
    en = front.get("en")
    en_ok = isinstance(en, dict) and bool(str(en.get("title", "")).strip()) and bool(en.get("summary"))
    if status == "active" and not en_ok:
        _fail("active section lacks a usable `en:` title/summary")
        failed = True

    # Trigger agreement: manifest rows are generated from the front
    # matter, so disagreement means a stale MANIFEST.yml.
    row_triggers = row.get("triggers") or {}
    front_triggers = front.get("triggers") or {}
    for key in ("keywords", "pattern", "config"):
        row_value = row_triggers.get(key) if isinstance(row_triggers, dict) else None
        front_value = front_triggers.get(key) if isinstance(front_triggers, dict) else None
        if key == "keywords":
            row_value = sorted(row_value) if isinstance(row_value, list) else row_value
            front_value = sorted(front_value) if isinstance(front_value, list) else front_value
        if row_value != front_value and not (row_value is None and key == "config"):
            _fail(f"manifest triggers.{key} disagrees with the front matter (run `just manifest`)")
            failed = True

    # Trigger regexes must compile.
    for key in ("pattern", "config"):
        pattern = front_triggers.get(key) if isinstance(front_triggers, dict) else None
        if isinstance(pattern, str) and pattern:
            try:
                re.compile(pattern)
            except re.error as exc:
                _fail(f"front-matter triggers.{key} does not compile ({exc})")
                failed = True

    section_obligations = front.get("obligations", []) if isinstance(front.get("obligations"), list) else []
    for obligation in section_obligations:
        obligations.setdefault(str(obligation), []).append(section_id)

    row_when = row.get("when", "always")
    front_when = front.get("when", "always")
    row_set = {row_when} if isinstance(row_when, str) else set(row_when or [])
    front_set = {front_when} if isinstance(front_when, str) else set(front_when or [])
    if row_set != front_set:
        _fail(f"manifest when {sorted(row_set)} disagrees with front matter {sorted(front_set)}")
        failed = True

    if not failed:
        lines.append(f"OK   {section_id}: pack={pack} status={status} obligations={len(section_obligations)}")
    elif status == "draft":
        _note("draft section; fix before promoting to active")
    return lines, failed


def _check_spec(spec: dict, spec_path: Path, obligations: dict[str, list[str]]) -> tuple[list[str], bool]:
    """Check one vendored check spec; returns (report lines, failed)."""
    lines: list[str] = []
    failed = False
    spec_id = str(spec.get("id", spec_path.stem))
    obligation = spec.get("obligation", "")
    level = str(spec.get("level", ""))

    def _fail(message: str) -> None:
        lines.append(f"FAIL {spec_id}: {message}")

    if not obligation:
        _fail("spec lacks an `obligation`")
        failed = True
    if level not in ("L0", "L1", "L2"):
        _fail(f"level is {level!r}, expected L0/L1/L2")
        failed = True
    if level == "L2" and ("blocking" not in spec or "fixtures" not in spec):
        _fail("L2 specs must carry `blocking` and `fixtures` (only structural gates may block)")
        failed = True

    triggers = spec.get("triggers", [])
    patterns = (
        [triggers]
        if isinstance(triggers, str)
        else [t for t in triggers if isinstance(t, str)]
        if isinstance(triggers, list)
        else []
    )
    if not patterns:
        lines.append(f"NOTE {spec_id}: no trigger patterns; the rule never fires on scanned text")
    else:
        for pattern in patterns:
            try:
                spec_rx = re.compile(pattern)
            except re.error as exc:
                _fail(f"trigger pattern does not compile ({exc})")
                failed = True
                continue
            serving = obligations.get(str(obligation), []) if obligation else []
            if not obligation or not serving:
                lines.append(f"NOTE {spec_id}: no section serves {obligation!r}; trigger agreement unchecked")
                continue
            probes = _probes_from_pattern(pattern)
            if not probes:
                _fail("trigger pattern yields no probe words")
                failed = True
                continue
            if not any(spec_rx.search(probe) for probe in probes):
                _fail("trigger pattern matches none of its own probe words")
                failed = True
    if not failed and not any(line.startswith(("FAIL", "NOTE")) for line in lines):
        lines.append(f"OK   {spec_id}: level={level} obligation={obligation}")
    return lines, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the vendored rulebook against its own contracts.")
    parser.add_argument(
        "--lawmap",
        type=Path,
        default=None,
        help="Path to a law-map checkout (default: the vendored snapshot)",
    )
    args = parser.parse_args(argv)

    if args.lawmap is not None:
        root = args.lawmap.resolve()
        sections_dir = root / "guidance" / "sections"
        checks_dir = root / "checks"
        obligations_dir = root / "obligations"
    else:
        root = _default_root()
        sections_dir = root / "sections"
        checks_dir = root / "checks"
        obligations_dir = root / "obligations"

    manifest_path = sections_dir / "MANIFEST.yml"
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        print(f"FAIL cannot read manifest {manifest_path}: {exc}")
        return 1
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        print(f"FAIL manifest {manifest_path} is not schema {MANIFEST_SCHEMA}")
        return 1
    rows = manifest.get("sections")
    if not isinstance(rows, list):
        print(f"FAIL manifest {manifest_path} has no sections list")
        return 1

    packs, packs_error = _packs_from_vocabulary(root if args.lawmap is None else _default_root())
    lines: list[str] = []
    failed = False
    if packs_error is not None:
        lines.append(f"FAIL {packs_error}")
        failed = True
        packs = {"core"}
    obligations: dict[str, list[str]] = {}
    ok_count = 0
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            lines.append("FAIL manifest entry lacks an id")
            failed = True
            continue
        section_id = row["id"]
        section_path = sections_dir / str(row.get("file") or "")
        try:
            text = section_path.read_text(encoding="utf-8")
        except OSError:
            lines.append(f"FAIL {section_id}: section file {row.get('file')!r} not found")
            failed = True
            continue
        front, _, split_error = _split_section(text)
        if split_error is not None or front is None:
            lines.append(f"FAIL {section_id}: {split_error}")
            failed = True
            continue
        pair_lines, pair_failed = _check_section(row, front, packs, obligations)
        lines.extend(pair_lines)
        failed = pair_failed or failed
        ok_count += 0 if pair_failed else 1

    spec_count = 0
    for spec_path in sorted(checks_dir.rglob("*.yml")):
        if spec_path.name.startswith("_"):
            continue
        try:
            spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            lines.append(f"FAIL {spec_path.name}: cannot read ({exc})")
            failed = True
            continue
        if not isinstance(spec, dict):
            lines.append(f"FAIL {spec_path.name}: expected a mapping")
            failed = True
            continue
        spec_lines, spec_failed = _check_spec(spec, spec_path, obligations)
        lines.extend(spec_lines)
        failed = spec_failed or failed
        spec_count += 1
        ok_count += 0 if spec_failed else 1

    # Obligations coverage: every obligation a section names must resolve to
    # a vendored obligation file with grounding strengths (the binding-tier
    # labels in the rules block come from there).
    for oid in sorted(obligations):
        parts = oid.split(".")
        if len(parts) != 3 or parts[0] != "obligation":
            lines.append(f"FAIL {oid}: obligation id does not look like obligation.<domain>.<slug>")
            failed = True
            continue
        rel = f"{parts[1]}/{parts[2]}.yml"
        obl_path = obligations_dir / rel
        try:
            data = yaml.safe_load(obl_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            lines.append(f"FAIL {oid}: vendored obligation {rel} unreadable ({exc})")
            failed = True
            continue
        if not isinstance(data, dict) or data.get("id") != oid:
            lines.append(f"FAIL {oid}: vendored obligation {rel} id mismatch")
            failed = True
            continue
        strengths = {
            str(g.get("strength", "")).strip() for g in (data.get("groundings", []) or []) if isinstance(g, dict)
        } - {""}
        if not strengths:
            lines.append(f"FAIL {oid}: vendored obligation {rel} has no grounding strengths")
            failed = True
            continue
        unknown = strengths - {"binding", "persuasive", "background"}
        if unknown:
            lines.append(f"FAIL {oid}: unknown strength values {sorted(unknown)} in {rel}")
            failed = True
            continue
        lines.append(f"OK   {oid}: strengths={','.join(sorted(strengths))}")
        ok_count += 1

    fail_count = sum(line.startswith("FAIL") for line in lines)
    lines.append(f"summary: {ok_count} items ok, {fail_count} failures")
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
