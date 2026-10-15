# Changelog

All notable changes to daimonion are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). No release has been tagged yet;
everything below is unreleased.

## [Unreleased]

### Added

- **Binding tiers in the rules block (PHI-5).** Each rendered rule now
  carries a one-line tier derived from its obligations' grounding
  `strength` values — *Binding* (legal duty), *Persuasive* (public
  recommendation), or *Background* (private rule or lesson) — in both
  English and Japanese. The snapshot vendors law-map's `obligations/`
  tree (16 files) alongside `sections/` and `checks/`; the parity check
  and test suite verify every section obligation resolves to a file
  with known strengths. Re-vendored at law-map `c4aaf02`.
- **Warn-only Action default.** The composite action now defaults to
  `adoption: "true"` / `strict: "false"`, so the first install never
  turns CI red; the README documents the switch to `strict: "true"`.
- **`python -m daimonion`** works (same entry point as the console
  script), and `.rove/init.sh` holds the one-time `uv sync` for fresh
  worktrees.
### Changed

- **Rulebook cutover (kanon merged into law-map).** The vendored snapshot
  moved from `src/daimonion/kanon/` (archived kanon repo, `KANON_SHA`) to
  `src/daimonion/rulebook/` (law-map `guidance/sections/` at `LAWMAP_SHA`
  `c4aaf02`, plus `checks/` and `obligations/`): sections are Markdown with
  YAML front matter and an `en:` block, and `tools/vendor_rulebook.py` /
  the weekly `rulebook-parity` workflow target law-map instead.
  `daimonion.kanon` and `KANON_CONDITIONS` remain as backwards-compatible
  aliases of `daimonion.rulebook` / `RULEBOOK_CONDITIONS`.
- **Lint rules load from the vendored check specs (BRK-3/DM-3).**
  `DEFAULT_RULES` is deleted: the default rule set is one rule per vendored
  `rulebook/checks/` spec (14 rules, ids like
  `privacy/cleartext-pii-logging-prohibited`). Specs name obligations, not
  project conditions, so the builtins carry no gates and `scan` always runs
  all of them — project scoping lives in `agents-md`. Inline ignores and
  baselines must name the new ids (e.g.
  `daimonion: ignore[crypto/deprecated-algorithms-prohibited]`).
- **Bilingual rules block.** `agents-md` renders each section's `en:` title
  and summary under the default English UI and the Japanese h1 plus `> 要約:`
  items under `--lang ja`; the block header records
  `rulebook=<sha> when=... packs=... lang=...`, so a stale language fails
  `--check`. New optional `packs:` key in `.daimonion.yml` opts into
  extension packs (`competitive-programming`); `core` always applies.
- **Keyword enforcement confirmed.** All vendored rules are keyword matchers
  capped at L1 (law-map L2 specs keep `blocking` + `fixtures` for their own
  structural engines; daimonion borrows only the trigger vocabulary), so
  `daimonion scan` on this repository reports findings but no L2, and
  `--strict` passes.
- Config is unified on `.daimonion.yml`: `daimonion init` reads
  `.copier-answers.yml` once and converts the answers to `when` conditions
  (mirroring the template's answer-to-condition derivation); `scan` and
  `agents-md` read only `.daimonion.yml`. Nothing reads the answers file at
  scan time.
- Subcommands are exactly `init` / `agents-md` / `scan`: `scan` takes
  optional paths (no paths scans the git diff, `--staged` for staged), and
  `scan --list-rules` (`--list-format {human,json}`) replaces `list-rules`.
  `prepare`, `check`, `diff`, and the `.daimonion-rules.yml` auto-loading
  are removed; an empty `when` scans everything, like `--all`.

- `scan` reads source code only by default (directory scans descend into
  `.py`/`.ts`/`.js`/`.go`/`.rs`/`.java`; the git-diff mode skips
  `.md`/`.yml`/`.yaml`/`.toml`); opt documents in with `--include-docs` or
  `scan: {docs: true}` in `.daimonion.yml`.
- The GitHub Action installs daimonion from its own checkout, so a pinned
  `politeuma/daimonion@<ref>` runs that ref, and it passes inputs through
  environment variables.
- The weekly ethics-parity check compares rules with kanon's
  `sections/MANIFEST.yml` instead of the removed architekton-py registry.
- Re-vendored kanon at `6f40ba3` (EU AI Act high-risk dates after the AI
  Omnibus; section files renamed `*.md`).

- Human-readable output is English by default: result headings and the
  builtin rules' titles and summaries are English, with the Japanese text kept
  in `src/daimonion/locales/ja.yml` for `--lang ja`. JSON and SARIF carry the
  English text.
- The AGENTS.md "ethics block" is now the **rules block**: each applicable
  kanon section renders as 1-3 imperative lines (the manifest's
  `directives.agent` when present, else the section summary's numbered items)
  plus its source links and a link to the full section at the pinned kanon
  commit, instead of the folded Japanese prose. The block's markers are
  `daimonion:rules:begin` / `daimonion:rules:end`; a block under the old
  `daimonion:ethics:*` markers reads as stale and `agents-md --write`
  replaces it in place.

- README install commands pin a git ref
  (`uvx --from "git+https://github.com/politeuma/daimonion@v0.1.0" ...`), as
  do the pre-commit and Action examples.

### Added

- Inline ignores: `# daimonion: ignore[rule-id] reason=... until=YYYY-MM-DD`.
- A findings baseline: `--write-baseline` / `--baseline`, default
  `.daimonion-baseline.json`.
- Adoption mode: `--adoption` or `mode: adoption` reports without ever
  failing; `mode: strict` enables strict from config. Action input `adoption`.
- SARIF output marks ignored and baselined results as suppressions.
- PyPI-ready metadata: authors, classifiers, keywords, project URLs, and
  `LICENSE`/`NOTICE` as license files (not yet published).
- `--lang {en,ja}` (or `DAIMONION_LANG`, or a `ja_*` locale) and `--no-emoji`
  (or `DAIMONION_NO_EMOJI=1`) for human-readable output, accepted before or
  after the subcommand.
- zizmor in CI; full Apache-2.0 `LICENSE` and a `NOTICE` for the bundled
  kanon prose.

### Earlier, before this log

- `check` / `diff` / `list-rules` with human, JSON, and SARIF output.
- `prepare` scoping from `.copier-answers.yml`.
- `init` and `agents-md` rendering the vendored kanon ethics block.
- law-map `checks/` directories accepted by `--rules`.
