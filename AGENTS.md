# Agent Guide for `daimonion`

This file is for AI coding agents working in this repository. It states how
to run the checks and where edits belong. The human-facing contribution
guide is [CONTRIBUTING.md](CONTRIBUTING.md).

`daimonion` is a legal-rule linter plus AGENTS.md renderer: it scans source
files and `git diff` changes against legal/ethical triggers, and renders
matching rulebook sections into an agent guide block. Section prose and
check specs live in [law-map](https://github.com/politeuma/law-map)
(`guidance/sections/`, `checks/`) — propose text changes there, not here.
(kanon, the former sections repo, is archived.)

## Commands

```sh
uv sync --dev
uv run ruff check .
uv run ruff format --check .
uv run python -m pytest -q
uvx zizmor@1.30.1 .                     # workflows and action.yml
uv run python tools/check_rulebook_parity.py   # vendored snapshot vs rulebook contracts
```

CI runs the same commands; a PR must pass all of them. The console script
is `daimonion` (`daimonion = "daimonion.cli:main"`); `python -m daimonion`
is the same entry point.

Run the CLI in dev with `uv run daimonion`:

```sh
uv run daimonion scan                  # diff mode: no paths, reads git diff itself
uv run daimonion scan --staged         # staged changes (as the pre-commit hook does)
uv run daimonion scan src/             # path mode: whole files/directories
uv run daimonion init --write          # propose .daimonion.yml from repo manifests; review it
uv run daimonion agents-md --write     # refresh the rules block in AGENTS.md
uv run daimonion agents-md --check     # CI: fail when the block is missing or stale
```

The agent-eval harness replays coding tasks with and without the rules
block: `python evals/run.py --dry-run`.

## Where to edit

- Application/package code: `src/daimonion/` (`cli.py`, `engine.py`,
  `rules.py`, `rulebook.py`, `config.py`, `context.py`, `detect.py`,
  `suppress.py`, `report.py`, `i18n.py`, `locales/ja.yml`)
- Vendored rulebook snapshot: `src/daimonion/rulebook/` (`sections/`,
  `checks/`, `obligations/`, `LAWMAP_SHA`) — written only by
  `tools/vendor_rulebook.py`; never hand-edit
- Parity guard: `tools/check_rulebook_parity.py` (also the test in
  `tests/test_rulebook_parity.py`); extend it when a new rulebook
  contract needs guarding
- Tests: `tests/` (`test_cli.py`, `test_linter.py`, `test_checkspecs.py`,
  `test_rulebook.py`, `test_init_agents_md.py`, `test_i18n.py`,
  `test_context.py`, `test_adoption.py`, `test_evals.py`)
- Eval harness: `evals/` (`run.py`, `tasks.py`, `scorer.py`)
- Consumer-facing surfaces: `action.yml` (composite action:
  `strict`/`adoption`/`args` inputs), `.pre-commit-hooks.yaml`
  (one hook, `daimonion-diff`: `daimonion --strict scan --staged`,
  `pass_filenames: false`)

New scan behaviour needs a test under `tests/`.

## Rules

- A rule that matches vocabulary is `kind: keyword` and is at most L1.
  Declare `kind: structural` only when a match is the violating construct
  itself; only those may be L2 and fail `--strict`.
- The default rule set is one rule per vendored check spec
  (`src/daimonion/rulebook/checks/`): to cover a new obligation, add the
  spec in law-map, re-vendor, and extend the parity check when a new
  contract needs guarding.
- English is canonical. A new or changed message goes into `MESSAGES` in
  `src/daimonion/i18n.py` with its Japanese translation in
  `src/daimonion/locales/ja.yml` (same key, same `{placeholders}`); the
  same holds for a builtin rule's `title`/`summary`.
  `tests/test_i18n.py` fails when the two drift apart.

## Rulebook re-vendoring

Vendor a clean, committed law-map checkout so `LAWMAP_SHA` names exactly
what was copied:

```sh
python tools/vendor_rulebook.py ../law-map
python tools/vendor_rulebook.py ../law-map --check
```

Commit the snapshot on its own (`chore: re-vendor rulebook at <sha>`).
`.github/workflows/rulebook-parity.yml` runs the same check weekly against
upstream law-map and files a `drift`-labelled issue on mismatch.

## Config file

`.daimonion.yml` speaks the rulebook's abstract `when` vocabulary, never
a template's flag names:

```yaml
version: 1
agents_md: AGENTS.md   # guide file that receives the block
when:                  # `always` sections apply without being listed
  - scraping
  - jp
packs: [core]          # optional extension packs
mode: adoption         # or: strict; adoption reports but always exits 0
scan:
  docs: false          # true: also scan .md/.yml/.yaml/.toml
```

The rules block sits between `<!-- daimonion:rules:begin ... -->` and
`<!-- daimonion:rules:end -->` markers; text outside them is never
touched.

## Commits and CI

- Use [Conventional Commits](https://www.conventionalcommits.org/);
  `ci.yml` runs ruff check, ruff format check, and pytest; the zizmor job
  statically analyses the workflows and `action.yml`.
- Add a line to `CHANGELOG.md` under `[Unreleased]` for user-visible
  changes.
