# daimonion

Fast, lightweight linter that inspects source files and `git diff` changes against legal and ethical triggers (intellectual property, cryptography, privacy, data governance, security policies).

Part of the [politeuma](https://github.com/politeuma) ecosystem.

## Why daimonion?

Rather than dumping thousands of lines of full legal commentary into your AI system prompts or `AGENTS.md`, `daimonion` inspects code changes as they happen. It surfaces only the concise rules and compliance requirements relevant to the code being touched.

See the [15-second demo](docs/demo/README.md): raw PII in a log line gets flagged, with the sourced rule and the masked fix.

## Installation & Quickstart

daimonion is not on PyPI yet. Run it from a pinned git ref: a release tag
(`v0.1.0` below) or a full commit SHA. An unpinned `git+https://...` URL runs
whatever `main` is at that moment, so always pin.

```sh
# Run via uvx without installing
uvx --from "git+https://github.com/politeuma/daimonion@v0.1.0" daimonion scan

# In a copier/architekton-py-generated project, convert .copier-answers.yml
# (project_type, domain_traits, ...) into .daimonion.yml `when` conditions
uvx --from "git+https://github.com/politeuma/daimonion@v0.1.0" daimonion init --write

# Or scan specific files or directories
uvx --from "git+https://github.com/politeuma/daimonion@v0.1.0" daimonion scan src/

# Or install the pinned release as a tool; later examples call `daimonion` directly
uv tool install "git+https://github.com/politeuma/daimonion@v0.1.0"
```

## Rules block for any repository

daimonion carries a pinned snapshot of the
[rulebook](https://github.com/politeuma/law-map/tree/main/guidance/sections)
(law-map's guidance sections plus its `checks/` specs; the law-map commit is
in `src/daimonion/rulebook/LAWMAP_SHA`), so any project can pull the reviewed
rules that apply to it into its agent guide, whatever template or toolchain
it started from:

```sh
# 1. Suggest conditions from pyproject.toml / requirements*.txt /
#    package.json / Cargo.toml / go.mod, notebooks, and agent files
daimonion init --write          # writes .daimonion.yml; review it

# 2. Insert or refresh the matching sections in AGENTS.md (or CLAUDE.md)
daimonion agents-md --write                 # English `en:` title + summary (default UI lang)
daimonion --lang ja agents-md --write       # Japanese h1 + summary items

# 3. In CI: fail when the block is missing or stale
daimonion agents-md --check
```


`.daimonion.yml` speaks the rulebook's abstract `when` vocabulary and never a
template's flag names:

```yaml
version: 1
agents_md: AGENTS.md   # guide file that receives the block
when:                  # `always` sections apply without being listed
  - scraping           # scraping, oj_code, mcp, data_science, web_api,
  - jp                 # commercial, eu_market, jp, ai_assisted
packs: [core]          # optional: opt into extension packs
                       # (e.g. `competitive-programming` for contest rules)
```

`init` only proposes. It cannot detect `commercial`, `eu_market`, or `jp`
from files, so it leaves those commented out for you to decide.

The block is short on purpose: each rule is 1-3 imperative lines plus its
sources, and the long prose (facts, cases, prohibited patterns) stays behind a
link to the rulebook section at the pinned commit:

```markdown
### Personal data — minimise before collecting, and build the deletion path first

- Ask whether each item is needed before collecting it; default to the minimum.
- ...

Sources: [eur-lex.europa.eu](https://eur-lex.europa.eu/eli/reg/2016/679/oj), [ppc.go.jp](https://www.ppc.go.jp/personalinfo/legal/) · Details: [rulebook `baseline-personal-data`](https://github.com/politeuma/law-map/blob/<sha>/guidance/sections/baseline/personal-data.md)
```

`--lang en` (or the default English UI) renders each section's `en:` title
and summary; `--lang ja` renders the Japanese h1 and the numbered items of
the `> 要約:` blockquote. The block header records the pin, the conditions,
the packs, and the language (`rulebook=<sha> when=... packs=... lang=...`),
so a stale language or pack choice fails `--check`.

The block sits between `<!-- daimonion:rules:begin ... -->` and
`<!-- daimonion:rules:end -->` markers; text outside them is never touched.
The same daimonion version always renders the same text, offline. Upgrading
daimonion is how new rulebook text arrives.

**Migrating from the "ethics block".** Earlier releases wrote the block
between `daimonion:ethics:begin` / `daimonion:ethics:end` markers. Those
markers are still recognised: `agents-md --check` reports such a block as
stale, and `agents-md --write` replaces it in place with the rules block and
the new markers. Templates that pre-seed empty markers may keep the old ones
or switch to the new ones.

Maintainers refresh the snapshot from a law-map checkout:

```sh
python tools/vendor_rulebook.py ../law-map          # vendor + record LAWMAP_SHA
python tools/vendor_rulebook.py ../law-map --check  # exit 1 when stale
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
capped to L1. The builtins come from the vendored `checks/` specs, whose
trigger vocabulary is keyword by nature, so every builtin is capped at L1 and
`--strict` never fails on the default rule set: structural L2 enforcement
lives in the spec's own engine (semgrep, file-presence gates), not in
`daimonion scan`.

**Scope.** The builtins carry no gates, so `scan` always runs all of them:
project scoping lives in `agents-md`, which renders only the sections whose
`when` matches `.daimonion.yml` (and whose `pack` is opted in). Directory
scans read source code only (`.py .ts .js .go .rs .java`); `diff` skips
`.md .yml .yaml .toml` changes. Opt documents in with `--include-docs` or in
`.daimonion.yml`. A file named explicitly on the command line is always
scanned. Custom `--rules` files may still carry gates; those scope through
`for_when` as before.

**Inline ignores.** Silence named rules on one line, with a reason and an
optional expiry; a directive alone on a comment line covers the next line:

```python
ua = "crawler-agent/1.0"  # daimonion: ignore[ai/llm-tool-allowlist-gate] reason=HTTP User-Agent until=2027-01-31

# daimonion: ignore[crypto/deprecated-algorithms-prohibited] reason=cache key, not a signature
key = hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()
```

A directive without `reason=` is not honoured, and after `until=` the finding
is reported again.

**Baseline.** Record what exists today and report only new findings:

```sh
daimonion scan src/ --write-baseline   # writes .daimonion-baseline.json; commit it
daimonion --strict scan src/           # baselined findings no longer count
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

`scan` accepts `--format {human,json,sarif}` (default `human`)
for CI annotations and SARIF upload; `scan --list-rules` accepts `--format
{human,json}`.

Human-readable output is English. `--lang ja` (or `DAIMONION_LANG=ja`, or a
`ja_*` locale) switches it, including the builtin rules' titles and
summaries, to Japanese; `--no-emoji` (or `DAIMONION_NO_EMOJI=1`) drops the
leading icons. Both work before or after the subcommand. JSON and SARIF are
always English. SARIF keeps inline-ignored and baselined results, marked with
`inSource` / `external` suppressions.

## Rulebook parity

`.github/workflows/rulebook-parity.yml` runs weekly against upstream
[law-map](https://github.com/politeuma/law-map)'s `guidance/sections/MANIFEST.yml`
and `checks/` specs and fails when the vendored snapshot drifts from the
rulebook's own contracts (front matter vs the generated manifest, missing
`en:` blocks on active sections, unknown packs, L2 specs without `blocking`
and `fixtures`, disagreeing trigger regexes), filing a `drift`-labelled
issue. The test suite runs the same check against the vendored snapshot
(`tools/check_rulebook_parity.py`). The agent-eval
harness in `evals/` replays coding tasks with and without the rules block
and counts violations (`python evals/run.py --dry-run`).

## Features

- **Scan Mode (`daimonion scan`)**: Scans modified lines in `git diff` (`--staged` for staged) or, with path arguments, entire files/directories (source code by default; docs opt-in) and flags touched compliance areas.
- **Rules block (`daimonion init` / `daimonion agents-md`)**: Suggests a template-independent `.daimonion.yml` from the repository's manifests, then writes, refreshes, or checks the matching rulebook rules (English `en:` lines or Japanese summary lines, sources, and a link to the full section) in `AGENTS.md`/`CLAUDE.md` from the bundled, SHA-pinned snapshot.
- **Rule Bundles**: Ships with one builtin rule per vendored check spec (licensing, crypto, personal data, scraping, AI safety), and can load custom rule YAMLs (`--rules path/to/rules.yml`).
- **law-map check specs**: the builtins *are* the vendored `rulebook/checks/` specs — each `checks/<domain>/<slug>.yml` spec maps to a rule (enforcement from the spec's `level`, triggers from its `triggers:` regex list). `--rules` also accepts an external law-map checkout's `checks/` directory, so `daimonion --rules ../law-map/checks scan <file>` scans with the same vocabulary law-map validates.
- **Project-Aware Scoping (`daimonion init` / `agents-md`)**: Reads `.copier-answers.yml` (architekton-py/copier history) once, converts the answers to `when` conditions, and writes `.daimonion.yml` (`init --write`) alongside manifest-detected signals — e.g. a `web_api` project renders the Japanese third-party-transmission and EU accessibility duties, while a `script` project skips them. `agents-md` scopes itself from `.daimonion.yml`; `scan` always runs every rule.
- **Zero Heavy Dependencies**: Lightweight (`pyyaml` only), instant execution in CI and local pre-commit hooks.

## Previous name

The `law-lint` command name was the previous one; invoke `daimonion`.
