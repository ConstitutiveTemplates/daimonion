#!/usr/bin/env python3
"""Vendor law-map's rulebook snapshot into src/daimonion/rulebook/.

daimonion ships the rulebook (guidance sections + check specs) inside its
own package so a pinned daimonion release always renders the same rules
block and lints with the same rules, offline. This script is the only
writer of that snapshot: it copies ``guidance/sections/MANIFEST.yml``,
``VOCABULARY.yml``, ``LICENSE``, every section file the manifest lists,
and the whole ``checks/`` tree, then records the law-map checkout's
commit in ``LAWMAP_SHA``. Bumping the snapshot is a deliberate,
reviewable commit.

Usage:
    python tools/vendor_rulebook.py ../law-map          # refresh the snapshot
    python tools/vendor_rulebook.py ../law-map --check  # exit 1 when stale
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

TOP = Path(__file__).resolve().parent.parent
TARGET = TOP / "src" / "daimonion" / "rulebook"
GUIDANCE = Path("guidance") / "sections"
CHECKS = Path("checks")
STATIC_FILES = ("MANIFEST.yml", "VOCABULARY.yml", "LICENSE")


def _checkout_sha(lawmap: Path) -> str:
    result = subprocess.run(["git", "-C", str(lawmap), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _manifest_files(lawmap: Path) -> list[str]:
    """Static files plus every section file the manifest lists, relative to ``sections/``."""
    manifest = yaml.safe_load((lawmap / GUIDANCE / "MANIFEST.yml").read_text(encoding="utf-8"))
    return [*STATIC_FILES, *(str(row["file"]) for row in manifest["sections"])]


def _check_files(lawmap: Path) -> list[str]:
    """Every ``*.yml`` under the law-map checkout's ``checks/`` tree."""
    return sorted(p.relative_to(lawmap / CHECKS).as_posix() for p in (lawmap / CHECKS).rglob("*.yml"))


def _stale(lawmap: Path, files: list[str], checks: list[str], sha: str) -> list[str]:
    """Paths whose vendored copy differs from the checkout (empty when in sync)."""
    stale = [
        f"sections/{rel}"
        for rel in files
        if not (TARGET / "sections" / rel).is_file()
        or not filecmp.cmp(lawmap / GUIDANCE / rel, TARGET / "sections" / rel, shallow=False)
    ]
    stale += [
        f"checks/{rel}"
        for rel in checks
        if not (TARGET / "checks" / rel).is_file()
        or not filecmp.cmp(lawmap / CHECKS / rel, TARGET / "checks" / rel, shallow=False)
    ]
    vendored = {
        p.relative_to(TARGET).as_posix()
        for p in (*((TARGET / "sections").rglob("*")), *((TARGET / "checks").rglob("*")))
        if p.is_file()
    }
    stale += sorted(vendored - {f"sections/{rel}" for rel in files} - {f"checks/{rel}" for rel in checks})
    sha_file = TARGET / "LAWMAP_SHA"
    if not sha_file.is_file() or sha_file.read_text(encoding="utf-8").strip() != sha:
        stale.append("LAWMAP_SHA")
    return stale


def _copy_tree(lawmap: Path, files: list[str], checks: list[str], sha: str) -> None:
    shutil.rmtree(TARGET / "sections", ignore_errors=True)
    shutil.rmtree(TARGET / "checks", ignore_errors=True)
    for rel in files:
        dest = TARGET / "sections" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(lawmap / GUIDANCE / rel, dest)
    for rel in checks:
        dest = TARGET / "checks" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(lawmap / CHECKS / rel, dest)
    (TARGET / "LAWMAP_SHA").write_text(sha + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lawmap", type=Path, help="Path to a law-map git checkout")
    parser.add_argument("--check", action="store_true", help="Exit 1 when the snapshot differs from the checkout")
    args = parser.parse_args(argv)

    lawmap = args.lawmap.resolve()
    sha = _checkout_sha(lawmap)
    files = _manifest_files(lawmap)
    checks = _check_files(lawmap)

    if args.check:
        stale = _stale(lawmap, files, checks, sha)
        if stale:
            print(f"rulebook snapshot is stale against {sha[:12]}: {', '.join(stale)}", file=sys.stderr)
            print(f"run: python tools/vendor_rulebook.py {args.lawmap}", file=sys.stderr)
            return 1
        print(f"rulebook snapshot matches {sha[:12]}")
        return 0

    _copy_tree(lawmap, files, checks, sha)
    print(f"vendored {len(files) - len(STATIC_FILES)} sections + {len(checks)} checks from law-map {sha[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
