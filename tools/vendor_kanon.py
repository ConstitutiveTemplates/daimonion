#!/usr/bin/env python3
"""Vendor a kanon checkout into src/daimonion/kanon/.

daimonion ships the kanon sections inside its own package so a pinned
daimonion release always renders the same rules block, offline. This script
is the only writer of that snapshot: it copies ``sections/MANIFEST.yml`` and
every file the manifest lists, then records the checkout's commit in
``KANON_SHA``. Bumping the snapshot is a deliberate, reviewable commit.

Usage:
    python tools/vendor_kanon.py ../kanon          # refresh the snapshot
    python tools/vendor_kanon.py ../kanon --check  # exit 1 when stale
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
TARGET = TOP / "src" / "daimonion" / "kanon"


def _checkout_sha(kanon: Path) -> str:
    result = subprocess.run(["git", "-C", str(kanon), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _manifest_files(kanon: Path) -> list[str]:
    """MANIFEST.yml plus every section file it lists, relative to ``sections/``."""
    manifest = yaml.safe_load((kanon / "sections" / "MANIFEST.yml").read_text(encoding="utf-8"))
    return ["MANIFEST.yml", *(str(row["file"]) for row in manifest["sections"])]


def _stale(kanon: Path, files: list[str], sha: str) -> list[str]:
    """Paths whose vendored copy differs from the checkout (empty when in sync)."""
    stale = [
        rel
        for rel in files
        if not (TARGET / "sections" / rel).is_file()
        or not filecmp.cmp(kanon / "sections" / rel, TARGET / "sections" / rel, shallow=False)
    ]
    vendored = {p.relative_to(TARGET / "sections").as_posix() for p in (TARGET / "sections").rglob("*") if p.is_file()}
    stale += sorted(vendored - set(files))
    sha_file = TARGET / "KANON_SHA"
    if not sha_file.is_file() or sha_file.read_text(encoding="utf-8").strip() != sha:
        stale.append("KANON_SHA")
    return stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("kanon", type=Path, help="Path to a kanon git checkout")
    parser.add_argument("--check", action="store_true", help="Exit 1 when the snapshot differs from the checkout")
    args = parser.parse_args(argv)

    kanon = args.kanon.resolve()
    sha = _checkout_sha(kanon)
    files = _manifest_files(kanon)

    if args.check:
        stale = _stale(kanon, files, sha) if (TARGET / "sections").is_dir() else ["sections/"]
        if stale:
            print(f"kanon snapshot is stale against {sha[:12]}: {', '.join(stale)}", file=sys.stderr)
            print(f"run: python tools/vendor_kanon.py {args.kanon}", file=sys.stderr)
            return 1
        print(f"kanon snapshot matches {sha[:12]}")
        return 0

    shutil.rmtree(TARGET / "sections", ignore_errors=True)
    for rel in files:
        dest = TARGET / "sections" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(kanon / "sections" / rel, dest)
    (TARGET / "KANON_SHA").write_text(sha + "\n", encoding="utf-8")
    print(f"vendored {len(files) - 1} sections from kanon {sha[:12]} into {TARGET.relative_to(TOP)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
