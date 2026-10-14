# daimonion

Fast, lightweight linter that inspects source files and `git diff` changes against legal and ethical triggers (intellectual property, cryptography, privacy, data governance, security policies).

Part of the [politeuma](https://github.com/politeuma) ecosystem.

## Why daimonion?

Rather than dumping thousands of lines of full legal commentary into your AI system prompts or `AGENTS.md`, `daimonion` inspects code changes as they happen. It surfaces only the concise rules and compliance requirements relevant to the code being touched.

## Installation & Quickstart

daimonion is not on PyPI yet. Run it from a pinned git ref: a release tag
(`v0.1.0` below) or a full commit SHA. An unpinned `git+https://...` URL runs
whatever `main` is at that moment, so always pin.

```sh
# Run via uvx without installing
uvx --from "git+https://github.com/politeuma/daimonion@v0.1.0" daimonion diff

# In a copier/architekton-py-generated project, prepare the applicable
# obligations from .copier-answers.yml (project_type, domain_traits, ...)
uvx --from "git+https://github.com/politeuma/daimonion@v0.1.0" daimonion prepare --write

# Or check specific files or directories
uvx --from "git+https://github.com/politeuma/daimonion@v0.1.0" daimonion check src/

# Or install the pinned release as a tool; later examples call `daimonion` directly
uv tool install "git+https://github.com/politeuma/daimonion@v0.1.0"
```

## Rules block for any repository

daimonion carries a pinned snapshot of
[kanon](https://github.com/politeuma/kanon)
(the commit is in `src/daimonion/kanon/KANON_SHA`), so any project can pull
the reviewed rules that apply to it into its agent guide, whatever template
or toolchain it started from:

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
from files, so it leaves those commented out for you to decide.

The block is short on purpose: each rule is 1-3 imperative lines plus its
sources, and the long prose (facts, cases, prohibited patterns) stays behind a
link to the kanon section at the pinned commit:

```markdown
### Personal data -- minimise before you collect

- NEVER pass raw user identifiers to logging or error trackers.
- ...

Sources: [eur-lex.europa.eu](https://eur-lex.europa.eu/eli/reg/2016/679/oj), [ppc.go.jp](https://www.ppc.go.jp/personalinfo/legal/) · Details: [kanon `baseline-personal-data`](https://github.com/politeuma/kanon/blob/<sha>/sections/baseline/personal-data.md)
```

The lines are the agent-facing `directives.agent` wording (as kept in
[law-map](https://github.com/politeuma/law-map)) when the vendored kanon
manifest carries it for a section, and otherwise the numbered items of the
section's summary, which kanon currently writes in Japanese.

The block sits between `<!-- daimonion:rules:begin ... -->` and
`<!-- daimonion:rules:end -->` markers; text outside them is never touched.
The same daimonion version always renders the same text, offline. Upgrading
daimonion is how new kanon text arrives.

**Migrating from the "ethics block".** Earlier releases wrote the block
between `daimonion:ethics:begin` / `daimonion:ethics:end` markers. Those
markers are still recognised: `agents-md --check` reports such a block as
stale, and `agents-md --write` replaces it in place with the rules block and
the new markers. Templates that pre-seed empty markers may keep the old ones
or switch to the new ones.

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
    rev: v0.1.0 # a release tag or a full commit SHA
    hooks:
      - id: daimonion-diff
```

Or run the composite action in a workflow:

```yaml
- uses: politeuma/daimonion@v0.1.0 # better: the tag's full commit SHA
  with:
    args: diff # default; any `check ...` / `diff ...` tail works
    strict: "true" # default; fail the job on structural L2 findings
    adoption: "false" # "true": report only, never fail (overrides strict)
```

The action installs daimonion from its own checkout (`github.action_path`),
so pinning `politeuma/daimonion@<sha>` runs exactly that commit. Inputs reach
the shell only through environment variables; `args` is split on whitespace
and never evaluated by the shell.

## Severity, scope, and adoption

**Severity.** Every builtin rule is a *keyword* rule: it matches topic
vocabulary (`license`, `agent`, `md5`), which says a compliance area was
touched, not that anything is wrong. Keyword findings are reminders: L1 when
the vocabulary is specific, L0 when it is broad. Only a rule declared
`kind: structural` (one that matches the violating construct itself, e.g. via
AST, semgrep, or dependency analysis) may be L2, and only L2 fails `--strict`.
A keyword rule declared L2 in a custom rule file or law-map check spec is
capped to L1.

**Scope.** Directory scans read source code only (`.py .ts .js .go .rs
.java`); `diff` skips `.md .yml .yaml .toml` changes. Opt documents in with
`--include-docs` or in `.daimonion.yml`. A file named explicitly on the
command line is always scanned.

**Inline ignores.** Silence named rules on one line, with a reason and an
optional expiry; a directive alone on a comment line covers the next line:

```python
ua = "crawler-agent/1.0"  # daimonion: ignore[llm-appsec] reason=HTTP User-Agent until=2027-01-31

# daimonion: ignore[deprecated-crypto] reason=cache key, not a signature
key = hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()
```

A directive without `reason=` is not honoured, and after `until=` the finding
is reported again.

**Baseline.** Record what exists today and report only new findings:

```sh
daimonion check src/ --write-baseline   # writes .daimonion-baseline.json; commit it
daimonion --strict check src/           # baselined findings no longer count
```

Entries are keyed by rule, file, and line text, so shifting lines keep
matching. `--baseline PATH` points elsewhere.

**Adoption mode.** `--adoption` (or `mode: adoption` in `.daimonion.yml`)
reports everything and always exits 0, even when the pre-commit hook or the
Action passes `--strict`; it notes how many findings would fail. Switch to
`mode: strict` (or drop `mode`) once the baseline is clean.

```yaml
# .daimonion.yml
version: 1
when: [web_api, jp]
mode: adoption   # or: strict
scan:
  docs: false    # true: also scan .md/.yml/.yaml/.toml
```

## Output formats

`check` and `diff` accept `--format {human,json,sarif}` (default `human`)
for CI annotations and SARIF upload; `list-rules` accepts `--format
{human,json}`.

Human-readable output is English. `--lang ja` (or `DAIMONION_LANG=ja`, or a
`ja_*` locale) switches it, including the builtin rules' titles and
summaries, to Japanese; `--no-emoji` (or `DAIMONION_NO_EMOJI=1`) drops the
leading icons. Both work before or after the subcommand. JSON and SARIF are
always English. SARIF keeps inline-ignored and baselined results, marked with
`inSource` / `external` suppressions.

## Ethics parity

`.github/workflows/ethics-parity.yml` runs weekly against upstream
[kanon](https://github.com/politeuma/kanon)'s `sections/MANIFEST.yml` and fails
when an active section drifts from its daimonion rule (unmapped active section,
uncovered trigger keyword, or a conditional `when` whose rule is ungated),
filing a `drift`-labelled issue. The test suite runs the same check against the
vendored snapshot. The mapping lives in `tools/check_ethics_parity.py`
(`SECTION_TO_RULE` — add a line when adding a section). The agent-eval
harness in `evals/` replays coding tasks with and without the rules block
and counts violations (`python evals/run.py --dry-run`).

## Features

- **Diff Mode (`daimonion diff`)**: Scans modified lines in `git diff` (or staged `--staged`) and flags touched compliance areas.
- **File Mode (`daimonion check <path>...`)**: Scans entire files or directories (source code by default; docs opt-in).
- **Rules block (`daimonion init` / `daimonion agents-md`)**: Suggests a template-independent `.daimonion.yml` from the repository's manifests, then writes, refreshes, or checks the matching kanon rules (imperative lines, sources, and a link to the full section) in `AGENTS.md`/`CLAUDE.md` from the bundled, SHA-pinned snapshot.
- **Rule Bundles**: Ships with built-in default rule profiles (licensing, crypto, personal data, scraping, AI safety), and can load custom rule YAMLs (`--rules path/to/rules.yml`).
- **law-map check specs**: `--rules` also accepts a law-map checkout's `checks/` directory — each `checks/<domain>/<slug>.yml` spec maps to a rule (enforcement from the spec's `level`, triggers from its `triggers:` regex list), so `daimonion --rules ../law-map/checks check <file>` scans with the same vocabulary law-map validates.
- **Project-Aware Scoping (`daimonion prepare`)**: Reads `.copier-answers.yml` (architekton-py/copier history), derives the project type and domain traits, evaluates each rule's gate, and prints or writes (`.daimonion-rules.yml` with `--write`) exactly the obligations that apply — e.g. a `web_api` project gets the Japanese third-party-transmission and EU accessibility duties, while a `script` project skips them. `check`, `diff`, and `list-rules` automatically scope themselves when a `.copier-answers.yml` or prepared rules file is present (`--all` opts out). A `.law-lint-rules.yml` prepared by the previous release is still read when `.daimonion-rules.yml` is absent.
- **Zero Heavy Dependencies**: Lightweight (`pyyaml` only), instant execution in CI and local pre-commit hooks.

## Previous name

The `law-lint` command name was the previous one; invoke `daimonion`.
