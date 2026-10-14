# law-lint

Fast, lightweight linter that inspects source files and `git diff` changes against legal and ethical triggers (intellectual property, cryptography, privacy, data governance, security policies).

Part of the [ConstitutiveTemplates](https://github.com/ConstitutiveTemplates) ecosystem.

## Why law-lint?

Rather than dumping thousands of lines of full legal commentary into your AI system prompts or `AGENTS.md`, `law-lint` inspects code changes as they happen. It surfaces only the concise rules and compliance requirements relevant to the code being touched.

## Installation & Quickstart

```sh
# Run via uvx without installing
uvx --from git+https://github.com/ConstitutiveTemplates/law-lint law-lint diff

# In a copier/daimonion-generated project, prepare the applicable
# obligations from .copier-answers.yml (project_type, domain_traits, ...)
uvx --from git+https://github.com/ConstitutiveTemplates/law-lint law-lint prepare --write

# Or check specific files or directories
uvx --from git+https://github.com/ConstitutiveTemplates/law-lint law-lint check src/
```

## Ethics block for any repository

law-lint carries a pinned snapshot of
[good-future-codex](https://github.com/ConstitutiveTemplates/good-future-codex)
(the commit is in `src/law_lint/kanon/KANON_SHA`), so any project can pull
the reviewed ethics sections into its agent guide, whatever template or
toolchain it started from:

```sh
# 1. Suggest conditions from pyproject.toml / requirements*.txt /
#    package.json / Cargo.toml / go.mod, notebooks, and agent files
law-lint init --write          # writes .daimonion.yml; review it

# 2. Insert or refresh the matching sections in AGENTS.md (or CLAUDE.md)
law-lint agents-md --write

# 3. In CI: fail when the block is missing or stale
law-lint agents-md --check
```

`.daimonion.yml` speaks the kanon's abstract `when` vocabulary and never a
template's flag names:

```yaml
version: 1
agents_md: AGENTS.md   # guide file that receives the block
when:                  # `always` sections apply without being listed
  - scraping           # scraping, oj_code, mcp, data_science, web_api,
  - jp                 # commercial, eu_market, jp, ai_assisted
```

`init` only proposes. It cannot detect `commercial`, `eu_market`, or `jp`
from files, so it leaves those commented out for you to decide. The block
sits between `<!-- daimonion:ethics:begin ... -->` and
`<!-- daimonion:ethics:end -->` markers; text outside them is never touched.
The same law-lint version always renders the same text, offline. Upgrading
law-lint is how new kanon text arrives.

Maintainers refresh the snapshot from a kanon checkout:

```sh
python tools/vendor_kanon.py ../good-future-codex          # vendor + record KANON_SHA
python tools/vendor_kanon.py ../good-future-codex --check  # exit 1 when stale
```

## Usage in CI / pre-commit

Scan staged changes on every commit (`diff` mode reads git itself, so no
filenames are passed):

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/ConstitutiveTemplates/law-lint
    rev: <ref>
    hooks:
      - id: law-lint-diff
```

Or run the composite action in a workflow:

```yaml
- uses: ConstitutiveTemplates/law-lint@<ref>
  with:
    args: diff # default; any `check ...` / `diff ...` tail works
    strict: "true" # default; fail the job on L2 findings
```

## Output formats

`check` and `diff` accept `--format {human,json,sarif}` (default `human`)
for CI annotations and SARIF upload; `list-rules` accepts `--format
{human,json}`.

## Ethics parity

`.github/workflows/ethics-parity.yml` runs weekly and fails when a
daimonion ethics section drifts from its law-lint rule (unmapped active
section, uncovered trigger keyword, or a non-empty registry gate with an
empty rule gate), filing a `drift`-labelled issue. The mapping lives in
`tools/check_ethics_parity.py` (`SECTION_TO_RULE` — add a line when
adding a section).

## Features

- **Diff Mode (`law-lint diff`)**: Scans modified lines in `git diff` (or staged `--staged`) and flags touched compliance areas.
- **File Mode (`law-lint check <path>...`)**: Scans entire files or directories.
- **Kanon Ethics Block (`law-lint init` / `law-lint agents-md`)**: Suggests a template-independent `.daimonion.yml` from the repository's manifests, then writes, refreshes, or checks the matching good-future-codex sections in `AGENTS.md`/`CLAUDE.md` from the bundled, SHA-pinned snapshot.
- **Rule Bundles**: Ships with built-in default rule profiles (licensing, crypto, personal data, scraping, AI safety), and can load custom rule YAMLs (`--rules path/to/rules.yml`).
- **law-map check specs**: `--rules` also accepts a law-map checkout's `checks/` directory — each `checks/<domain>/<slug>.yml` spec maps to a rule (enforcement from the spec's `level`, triggers from its `triggers:` regex list), so `law-lint --rules ../law-map/checks check <file>` scans with the same vocabulary law-map validates.
- **Project-Aware Scoping (`law-lint prepare`)**: Reads `.copier-answers.yml` (daimonion/copier history), derives the project type and domain traits, evaluates each rule's gate, and prints or writes (`.law-lint-rules.yml` with `--write`) exactly the obligations that apply — e.g. a `web_api` project gets the Japanese third-party-transmission and EU accessibility duties, while a `script` project skips them. `check`, `diff`, and `list-rules` automatically scope themselves when a `.copier-answers.yml` or prepared rules file is present (`--all` opts out).
- **Zero Heavy Dependencies**: Lightweight (`pyyaml` only), instant execution in CI and local pre-commit hooks.
