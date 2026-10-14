# Contributing to daimonion

daimonion is the *runner* of the politeuma stack: it scans code against rules
and renders kanon's ethics sections into agent guides. Section prose lives in
[kanon](https://github.com/politeuma/kanon); propose text changes there, not
here.

Issues and PRs in English or Japanese are welcome.

## Set up and check

```sh
uv sync --dev
uv run ruff check .
uv run ruff format --check .
uv run python -m pytest -q
uvx zizmor@1.30.1 .                     # workflows and action.yml
uv run python tools/check_ethics_parity.py   # rules vs the vendored kanon
```

CI runs the same commands; a PR must pass all of them.

## Rules

- A rule that matches vocabulary is `kind: keyword` and is at most L1.
  Declare `kind: structural` only when a match is the violating construct
  itself; only those may be L2 and fail `--strict`.
- Adding a builtin rule for a kanon section: add a `SECTION_TO_RULE` line in
  `tools/check_ethics_parity.py`, or list the section in
  `KNOWN_UNMAPPED_ACTIVE` when it deliberately has no rule.
- New scan behaviour needs a test under `tests/`.

## Refreshing the bundled kanon

`src/daimonion/kanon/` is written only by `tools/vendor_kanon.py`. Vendor a
clean, committed kanon checkout so `KANON_SHA` names exactly what was copied:

```sh
python tools/vendor_kanon.py ../kanon
python tools/vendor_kanon.py ../kanon --check
```

Commit the snapshot on its own (`chore: re-vendor kanon at <sha>`).

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/) and add a
line to `CHANGELOG.md` under `[Unreleased]` for user-visible changes.
