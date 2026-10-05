---
title: Continuous Drift Detection: the 5 ways a template rots (and who notices)
venue: r/programming / DevOps communities
status: DRAFT — human edits before posting
---

A project template is one of the few programs whose most dangerous failures arrive
**without a single code change**. A pinned tool releases a new major. A dependency's
license changes underneath you. Upstream fixes a bug you never saw. A formatter
release reflows a file you hand-wrote. The template keeps rendering exactly as
confidently as before — while the world it renders against has moved.

daimonion is an opinionated [copier](https://copier.readthedocs.io) template for Python
projects. Its questionnaire is verified with an SMT solver (Z3) across 272 enumerated
witness leaves, but that only proves the *input space* is reachable; it says nothing
about whether the generated output is still correct next Tuesday. So the repo treats
drift detection as a first-class problem with **five dimensions**, each a dedicated
scheduled workflow, each with a real incident behind it. The design notes live in
`docs/explanations/drift-detection.md`; the mechanisms below are what actually runs.

The name *daimonion* is Socrates' inner voice — it never tells you what to
do, only when to stop — matching the template's warning/abort/refusal posture
(and the etymology of Unix *daemon*).

## 1. Upstream copier drift — hardcoded pins

A template hardcodes versions that renovate cannot track: release tags, CUDA wheel
indexes, distro EOL dates, image tags. `tools/check_upstream.py` parses those pins out
of the template files (no network to extract them), then resolves each one against
upstream — PyPI floors, the torch `cu12x` index, REP-2000 ROS 2 EOL dates, the Python
EOL endpoint, Postgres major tags, the copier ceiling, the devcontainer base image.
A pin whose current value no longer matches upstream prints a `[DRIFT]` line and the
script exits 1.

`.github/workflows/check-upstream.yml` (Monday 06:00) runs it and, on a `[DRIFT]` line,
files one deduplicated issue: "Template pins are behind upstream". A `[warn]` run (an
upstream lookup failed transiently) deliberately does *not* file — a red schedule
nobody subscribes to is a cell that only pretends to be filled. This is a separate
concern from the *git fork*: `check-upstream-fork.yml` (Tuesday) runs
`tools/check_upstream_fork.py` against the fork parent,
`DiamondLightSource/python-copier-template`, reporting upstream `main` commits not yet
reviewed. When that checker kept re-firing on already-reviewed commits (a
`HEAD..FETCH_HEAD` comparison against a deliberately diverged fork), the fix was the
`.upstream-fork-reviewed` marker file: the checker now diffs *marker..FETCH_HEAD* and
fails loudly if the marker ever stops being an ancestor of upstream.

## 2. Generated-project CI drift — the world moved, nobody typed

Push/PR CI only fires when someone changes code. The template's worst drift is
invisible to it: a new ruff rule, a basedpyright behaviour change, a pinned
dependency's latest release. `scheduled-check.yml` (Tuesday 07:00) re-runs the *same*
lint / type-check / test / docs jobs as `ci.yml` with zero repo changes, and files a
deduplicated "Scheduled full check failed (no code change involved)" issue.

This is the dimension that earned its keep. For three straight weeks the job died at
`startup_failure` before running anything: the reusable `_docs.yml` declares
`contents: write`, and a reusable workflow's permissions cannot exceed the caller's
grant — so the scheduled caller, which passed nothing, was refused at run creation.
After adding the permission, the weekly check immediately did its job, surfacing two
real bugs: a vendored `clean.scss` with trailing whitespace that `git diff --check`
caught, and a rehearsal test that crashed the whole suite because witness leaves
newer than the release's questionnaire were unrenderable. The earlier web-API slice
showed the same pattern: the generated test CI exported an **empty-string
`DATABASE_URL`** when no Postgres service was configured, `settings.py` adopted the
empty value instead of its default, and the import failed — red in CI only, invisible
until the scheduled run.

## 3. Ethics content drift — facts have expiry dates

The template vendors an ethics/regional appendix from
`ConstitutiveTemplates/good-future-codex` (OWASP, FIPS, regional law) into
`_shared/ethics/`. Those sections move on their own review cadence, independent of
this repo's commits. `tools/check_ethics_drift.py` clones the public codex and diffs
the vendored tree against it, keyed by the committed `.ethics-vendored` marker (a
SHA of the vendored tree); `ethics-sync.yml` (Tuesday 07:00) files an issue when the
tree is dirty or codex `main` is ahead. Obligation freshness is a separate corpus:
every grounding in `ConstitutiveTemplates/law-map` carries a `review_by` date, and the
scheduled check runs `law-map check --codex` against `good-future-codex` so an expired
statute/citation citation reddens CI as a dated obligation — not a style opinion.
Three different vendored corpora (pins, fork, ethics) fail in three differently-named
issues, so a red run names exactly one thing to fix.

## 4. Dependency drift — renovate + a dedicated audit

`renovate.json` pins GitHub Action digests (`helpers:pinGitHubActionDigests`), enables
lock-file maintenance for `uv.lock` with merge-on-green, groups non-major action
updates, and auto-merges vulnerability alerts. That covers the dependency *graph*.
The *contents* are audited separately: `dependency-audit.yml` (Thursday) runs
`task audit` — `pip-audit` over OSV — deliberately *not* in PR CI, which must stay
offline, and files a deduplicated "pip-audit found vulnerabilities" issue on failure.
Two real-world confirmations: a `mcp[cli]>=2.0` floor pointed at a version that never
shipped (empty set) and was corrected to `>=2.0.1`; and a `zizmor version: latest`
pin in generated `security.yml` was the kind of unpinned release reference that
rotates out from under you — fixed by pinning the CLI. Pins are either digest-pinned
(actions, handled by renovate) or `latest`-free.

## 5. Test-tier drift — guarding the guards

The suite is cost-tiered so the edit loop stays fast: `test-fast` (30s budget),
`test-slow` (serial witness runner), `test-heavy` (venv/network builds, pre-push),
`test-randomly`, `test-meta`. `tests/test_marker_drift.py` is the meta-guard: it
re-collects every tier once and compares against the committed ledger
`tests/matrix/tiers.json`. It reads the marker expression back from `Taskfile.yml`
and the witness selections back from `.github/workflows/witness.yml`, so a renamed or
removed task fails the ledger check on purpose; a cost older than 30 days is
re-measured, never cited; a tier measured over its `budget_seconds` fails; and the
witness leaf space is capped by `LEAF_BUDGET` (450) so the multiplicative growth a
questionnaire change can trigger is a decision, not a 30-minute-timeout surprise.
The pattern recurs: when a parametrized test added 26 nodes to the fast tier, the
ledger's own guard flagged the staleness and `UPDATE_TIERS=1` re-recorded it; when the
fast tier blew its 30s budget (30.7s), the fix was routing example tests through the
render cache (back to 27.5s) — the guard caught a *slowdown*, not a wrong answer.

## The through-line

Every mechanism above fires **without a code change**, **names exactly one concern**,
and files a **deduplicated issue** — so a red run means "fix this now," not "another
alarm." Detectors rot too, so each is guarded by a test that breaks it on purpose and
expects the detector to complain. The lesson isn't "add more checks"; it's to name the
source and the timing of every check you already have, then look at which cells your
actual incidents came from. The empty cell is where the six-months-late bug lives.