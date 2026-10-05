---
title: "Show HN: We mathematically verified a Python project template's 272 paths with Z3"
venue: Hacker News (Show HN) and r/Python
status: DRAFT — human edits before posting
date: 2026-10-05
source: ConstitutiveTemplates/daimonion (verified against repo at 3e2678ae)
---

Show HN: We mathematically verified a Python project template's 272 paths with Z3

Every Python project template starts as a handful of "yes/no" questions. Then
someone adds an option — a web API layer, a bot platform, a license — and the
questions gain `when:` conditions. Three years later the template has ~40
questions, and the combinations are no longer enumerable by hand. Nobody
renders the corners. The corners are where the template breaks.

The standard failure is silent: a question condition typo makes one branch
unreachable (the answer is asked and then ignored), or two options combine
into a project that installs `sentry-sdk` and never initializes it.
Push CI renders the happy path, the maintainer's own project, and the template
"works" — until a user picks the one combination nobody tested.

We got tired of this and built the fix into the template itself:
[daimonion](https://github.com/ConstitutiveTemplates/daimonion), an opinionated
[copier](https://copier.readthedocs.io) template for Python projects.

The name is Socrates' daimonion — the inner voice that never says what to
do, only when to stop — matching the template's warning/abort/refusal
posture (and the etymology of Unix *daemon*).

**The core idea: treat the questionnaire's `when:` logic as a constraint
problem, not as prose.** `tools/when_model.py` parses every `when:`
expression and encodes it as SMT constraints in Z3 — each question's
visibility, each option's domain. A path through the questionnaire is a
satisfying assignment. If a condition can never be true, or a combination
excludes a question that one of its render templates reads, Z3 finds it as
`unsat`. The full space is then enumerated: every satisfying model becomes a
"witness leaf" — a concrete set of answers with the artifacts it must
produce.

**How it works (the witness pipeline):**

1. `tools/z3_witnesses.py` builds a Z3 model of all ~40 questions' `when:`
   expressions, asserts the leaf-space restrictions (gate semantics, the
   opt-in layer rules), and asks Z3 for every satisfying model, blocking each
   one as it is found.
2. Each model becomes a batch request: id, answers, and the invariants that
   render must satisfy (`tests/matrix/witnesses.json`). Currently **272
   leaves** — 264 exercised in the fast tier, 8 in the full tier (docker +
   MCP variants, bot platforms, the domain-traits combinations).
3. CI renders every leaf end to end — a real copier `Worker._ask` per leaf —
   and fails if any leaf's artifacts deviate from its declared invariants, if
   a leaf renders no project, or if a leaf that must be byte-identical to its
   twin isn't (`tests/matrix/witnesses.jsonl` is the request list, ~25s for
   the 272-leaf pass).
4. `tools/predicates.py` proves the converse: predicates that *cannot*
   disagree (same question read, same gate) are proven equivalent over the
   272-leaf space, and a typo'd condition that silently never splits the
   space is reported instead of shipping.

Net effect: the branch you will never manually render is the branch CI
renders. Currently 278 tests execute the witness tier and 1,092 tests run in
the 30-second edit-loop tier (`test-fast`) — with budgets enforced by a cost
ledger that fails a tier when its wall time exceeds its declared budget.

What you get when the branch check passes:

- **Eight project types** — `library`, `web_api`, `cli`, `data_science`,
  `online_judge`, `script`, `ros2`, `micropython` — each with its own layout,
  CI and docs, plus opt-in layers (FastAPI service, MCP servers, Discord /
  Slack / LINE / Gmail bots, polite scraping, CTF tooling, cloud, Sentry).
- **A real toolchain** — uv (or pixi/poetry), ruff on ALL rules, basedpyright
  + pyrefly, typos/vulture/deptry/pip-audit, pytest + coverage + hypothesis,
  hardened CI with SHA-pinned actions.
- **A generated `AGENTS.md`** in every project, plus an ethics/regional
  appendix matched to the project kind — dependency-license drift,
  post-quantum crypto standards, AI-and-copyright, PKI trust chains, EU CRA
  duties, face recognition. Sections are registered, dated and
  enforcement-graded, and held to the renders by the same invariants.
- **OpenSSF Scorecard posture** — SECURITY.md, scorecard workflow, pinned
  digests; a drift detector (`tools/check_upstream.py`) checks the pins
  renovate can't track (MicroPython tags, CUDA indexes, ROS distro EOL dates,
  Python floors) against upstream weekly and opens an issue on drift.
- **Safe adoption** — `daimonion new .` inside an existing repo adds the
  missing infrastructure (CI, quality tooling, AGENTS.md) transactionally and
  verifies the files you already have stay byte-identical.

One line to try it:

```shell
uvx --from git+https://github.com/ConstitutiveTemplates/daimonion.git \
    daimonion new my-project --preset library
```

or drive copier directly (`--trust` runs the post-generation tasks):

```shell
uvx copier copy --trust https://github.com/ConstitutiveTemplates/daimonion.git my-project
```

Everything a template *is* is data: the questions, the conditions, the
derived flags, the rendered files. That means it can be verified like data —
and the verification can run forever, not just on release day. We keep it
honest with weekly scheduled checks that run the full lint/type-check/test/
docs matrix with zero code changes (toolchain drift surfaces as a failing job
and an issue), plus ethics-vendor drift and law-map obligation-freshness
checks.

We'd love a stress test: generate a project with the combination you think is
least likely to work, and open an issue if it renders something wrong.

---

## Notes for the maintainer (delete before posting)

- **Leaf count**: the TODO.md §37.4 title suggestion and HUMAN_TODO.md say
  "234" (written 2026-09-18). The repo has since grown to **272 leaves**
  (domain traits + distribution variants + bot platforms — see
  `tests/matrix/witnesses.json` "total": 272, "executed_fast": 272).
  This draft uses 272; keep the title in sync if you post.
- Numbers verified against the repo at 3e2678ae: leaves 272
  (`tests/matrix/witnesses.json`), witness-fast 278 tests / test-fast 1092
  (`tests/matrix/tiers.json`), 8 `project_type` choices (`copier.yml`),
  12 presets (`presets/`), 5 drift workflows
  (`check-upstream.yml`, `check-upstream-fork.yml`, `scheduled-check.yml`,
  `ethics-sync.yml`, `periodic.yml`, plus `law-map-review-by` inside
  `scheduled-check.yml`).
- If the maintainer prefers to keep "234" for continuity with the planned
  three-article series, the repo numbers must be re-verified first — 234 is
  not what the repo currently ships.