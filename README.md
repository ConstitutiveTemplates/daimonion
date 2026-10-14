# daimonion

Fast, lightweight linter that inspects source files and `git diff` changes against legal and ethical triggers (intellectual property, cryptography, privacy, data governance, security policies).

Part of the [politeuma](https://github.com/politeuma) ecosystem.

## Why daimonion?

Rather than dumping thousands of lines of full legal commentary into your AI system prompts or `AGENTS.md`, `daimonion` inspects code changes as they happen. It surfaces only the concise rules and compliance requirements relevant to the code being touched.

## Installation & Quickstart

```sh
# Run via uvx without installing
uvx --from git+https://github.com/politeuma/daimonion daimonion diff

# In a copier/architekton-py-generated project, prepare the applicable
# obligations from .copier-answers.yml (project_type, domain_traits, ...)
uvx --from git+https://github.com/politeuma/daimonion daimonion prepare --write

# Or check specific files or directories
uvx --from git+https://github.com/politeuma/daimonion daimonion check src/
```

## Ethics block for any repository

daimonion carries a pinned snapshot of
[kanon](https://github.com/politeuma/kanon)
(the commit is in `src/daimonion/kanon/KANON_SHA`), so any project can pull
the reviewed ethics sections into its agent guide, whatever template or
toolchain it started from:

```sh
# 1. Suggest conditions from pyproject.toml / requirements*.txt /
#    package.json / Cargo.toml / go.mod, notebooks, and agent files
daimonion init --write          # writes .daimonion.yml; review it

# 2. Insert or refresh the matching sections in AGENTS.md (or CLAUDE.md)
daimonion agents-md --write

# 3. In CI: fail when the block is missing or stale
daimonion agents-md --check
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
The same daimonion version always renders the same text, offline. Upgrading
daimonion is how new kanon text arrives.

Maintainers refresh the snapshot from a kanon checkout:

```sh
python tools/vendor_kanon.py ../kanon          # vendor + record KANON_SHA
python tools/vendor_kanon.py ../kanon --check  # exit 1 when stale
```

## Usage in CI / pre-commit

Scan staged changes on every commit (`diff` mode reads git itself, so no
filenames are passed):

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/politeuma/daimonion
    rev: <ref>
    hooks:
      - id: daimonion-diff
```

Or run the composite action in a workflow:

```yaml
- uses: politeuma/daimonion@<ref>
  with:
    args: diff # default; any `check ...` / `diff ...` tail works
    strict: "true" # default; fail the job on L2 findings
```

## Output formats

`check` and `diff` accept `--format {human,json,sarif}` (default `human`)
for CI annotations and SARIF upload; `list-rules` accepts `--format
{human,json}`.

## Ethics parity

`.github/workflows/ethics-parity.yml` runs weekly and fails when an
architekton-py ethics section drifts from its daimonion rule (unmapped active
section, uncovered trigger keyword, or a non-empty registry gate with an
empty rule gate), filing a `drift`-labelled issue. The mapping lives in
`tools/check_ethics_parity.py` (`SECTION_TO_RULE` — add a line when
adding a section).

## Features

- **Diff Mode (`daimonion diff`)**: Scans modified lines in `git diff` (or staged `--staged`) and flags touched compliance areas.
- **File Mode (`daimonion check <path>...`)**: Scans entire files or directories.
- **Kanon Ethics Block (`daimonion init` / `daimonion agents-md`)**: Suggests a template-independent `.daimonion.yml` from the repository's manifests, then writes, refreshes, or checks the matching kanon sections in `AGENTS.md`/`CLAUDE.md` from the bundled, SHA-pinned snapshot.
- **Rule Bundles**: Ships with built-in default rule profiles (licensing, crypto, personal data, scraping, AI safety), and can load custom rule YAMLs (`--rules path/to/rules.yml`).
- **law-map check specs**: `--rules` also accepts a law-map checkout's `checks/` directory — each `checks/<domain>/<slug>.yml` spec maps to a rule (enforcement from the spec's `level`, triggers from its `triggers:` regex list), so `daimonion --rules ../law-map/checks check <file>` scans with the same vocabulary law-map validates.
- **Project-Aware Scoping (`daimonion prepare`)**: Reads `.copier-answers.yml` (architekton-py/copier history), derives the project type and domain traits, evaluates each rule's gate, and prints or writes (`.daimonion-rules.yml` with `--write`) exactly the obligations that apply — e.g. a `web_api` project gets the Japanese third-party-transmission and EU accessibility duties, while a `script` project skips them. `check`, `diff`, and `list-rules` automatically scope themselves when a `.copier-answers.yml` or prepared rules file is present (`--all` opts out). A `.law-lint-rules.yml` prepared by the previous release is still read when `.daimonion-rules.yml` is absent.
- **Zero Heavy Dependencies**: Lightweight (`pyyaml` only), instant execution in CI and local pre-commit hooks.

## Previous name

The `law-lint` command name was the previous one; invoke `daimonion`.
