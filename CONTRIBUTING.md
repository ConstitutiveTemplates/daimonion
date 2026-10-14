# Contributing to daimonion

daimonion is the *runner* of the politeuma stack: it scans code against rules
and renders the rulebook's sections into agent guides as a block of sourced rules.
Section prose and check specs live in [law-map](https://github.com/politeuma/law-map)
(`guidance/sections/`, `checks/`); propose text changes there, not here.
(kanon, the former sections repo, is archived.)

Issues and PRs in English or Japanese are welcome.

## Set up and check

```sh
uv sync --dev
uv run ruff check .
uv run ruff format --check .
uv run python -m pytest -q
uvx zizmor@1.30.1 .                     # workflows and action.yml
uv run python tools/check_rulebook_parity.py   # snapshot vs the rulebook contracts
```

CI runs the same commands; a PR must pass all of them.

## Rules

- A rule that matches vocabulary is `kind: keyword` and is at most L1.
  Declare `kind: structural` only when a match is the violating construct
  itself; only those may be L2 and fail `--strict`.
- The default rule set is one rule per vendored check spec
  (`src/daimonion/rulebook/checks/`): to cover a new obligation, add the
  spec in law-map, re-vendor, and extend `tools/check_rulebook_parity.py`
  when a new contract needs guarding.
- New scan behaviour needs a test under `tests/`.

## Refreshing the bundled rulebook

`src/daimonion/rulebook/` is written only by `tools/vendor_rulebook.py`.
Vendor a clean, committed law-map checkout so `LAWMAP_SHA` names exactly
what was copied:

```sh
python tools/vendor_rulebook.py ../law-map
python tools/vendor_rulebook.py ../law-map --check
```

Commit the snapshot on its own (`chore: re-vendor rulebook at <sha>`).

## Human-readable text

English is canonical. A new or changed message goes into `MESSAGES` in
`src/daimonion/i18n.py` and its Japanese translation into
`src/daimonion/locales/ja.yml` (same key, same `{placeholders}`); the same
holds for a builtin rule's `title` and `summary` (one entry per vendored
check-spec id). `tests/test_i18n.py` fails when the two drift apart.

## Releasing

Not automated yet, and nothing is on PyPI. A release is:

1. Move `[Unreleased]` in `CHANGELOG.md` under the version and bump
   `version` in `pyproject.toml`.
2. `uv build` and check the wheel: `daimonion/locales/ja.yml`,
   `daimonion/rulebook/`, and `LICENSE`/`NOTICE` under `licenses/` must be in it.
3. Tag `vX.Y.Z`, push the tag, and update the pinned `@vX.Y.Z` / `rev:`
   examples in `README.md`.
4. Publish with `uv publish` (PyPI trusted publishing once it is set up).

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/) and add a
line to `CHANGELOG.md` under `[Unreleased]` for user-visible changes.
