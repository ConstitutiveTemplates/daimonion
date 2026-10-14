# Changelog

All notable changes to daimonion are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). No release has been tagged yet;
everything below is unreleased.

## [Unreleased]

### Changed

- Keyword rules are reminders: a rule's `kind` is `keyword` (default) or
  `structural`, and keyword rules are capped at L1. Every builtin is a keyword
  rule, so the builtins no longer fail `--strict`; only `kind: structural`
  rules may be L2.
- `check` scans source code only by default and `diff` skips
  `.md`/`.yml`/`.yaml`/`.toml`; opt documents in with `--include-docs` or
  `scan: {docs: true}` in `.daimonion.yml`.
- The GitHub Action installs daimonion from its own checkout, so a pinned
  `politeuma/daimonion@<ref>` runs that ref, and it passes inputs through
  environment variables.
- The weekly ethics-parity check compares rules with kanon's
  `sections/MANIFEST.yml` instead of the removed architekton-py registry.
- Re-vendored kanon at `6f40ba3` (EU AI Act high-risk dates after the AI
  Omnibus; section files renamed `*.md`).

### Added

- Inline ignores: `# daimonion: ignore[rule-id] reason=... until=YYYY-MM-DD`.
- A findings baseline: `--write-baseline` / `--baseline`, default
  `.daimonion-baseline.json`.
- Adoption mode: `--adoption` or `mode: adoption` reports without ever
  failing; `mode: strict` enables strict from config. Action input `adoption`.
- SARIF output marks ignored and baselined results as suppressions.
- zizmor in CI; full Apache-2.0 `LICENSE` and a `NOTICE` for the bundled
  kanon prose.

### Earlier, before this log

- `check` / `diff` / `list-rules` with human, JSON, and SARIF output.
- `prepare` scoping from `.copier-answers.yml`.
- `init` and `agents-md` rendering the vendored kanon ethics block.
- law-map `checks/` directories accepted by `--rules`.
