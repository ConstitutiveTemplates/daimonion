Title: Export the resolved questionnaire as JSON for non-interactive callers (agents, CI)

## Summary

Copier's questionnaire is machine-checked internally (each question's `type`,
`when`, `choices`, `default`, `help`) but there is no way to *read* it
without rendering or parsing `copier.yml` + Jinja yourself. Non-interactive
callers — CI jobs, LLM agents, template-conformance tooling — have to guess
which answers to pass via `--data`/`--data-file`, and mistakes surface one
at a time (see the missing-answer batch-report proposal).

This proposes a read-only flag that emits the resolved question list as
JSON, e.g. `copier copy --print-questions --format json <template>`, so a
caller can enumerate the questions, answer them programmatically, and loop
until no required answer is missing.

## Current behavior

- `copier copy`/`update`/`recopy` prompt interactively; `--data`,
  `--data-file`, and `--defaults` inject answers blindly.
- There is no stable way to ask "which questions does this template ask,
  with which types, choices, and conditions?" without rendering.
- The missing-answer error reports a name but not the question's schema,
  so a caller cannot tell "string" from "choice of three" without
  re-reading `copier.yml`.

## Expected behavior

One of (name/flag shape is open to bikeshed):

- `copier copy --print-questions <template>` — resolve the questionnaire
  (with `--data`/`--defaults`/`--data-file` applied, so `when:` branches
  collapse correctly) and print the question set without rendering.
- Output shape (sketch):
  ```json
  [
    {"name": "package_name", "type": "str", "help": "...", "default": "...",
     "when": true, "required": true},
    {"name": "project_type", "type": "str", "choices": [{"value": "cli",
      "name": "CLI"}], "default": "cli", "when": true, "required": true}
  ]
  ```
- The same schema doubles as the `missing` report shape for the
  batch-missing-answer proposal, so the two features share one format.

## Design questions for discussion

- Read-only flag (`--print-questions`) vs. a subcommand
  (`copier questions <template>`)?
- Does `--format json` need a plain-text rendering too, or is JSON enough
  for the non-interactive consumers this targets?
- How to report questions whose `when:` still references unanswered
  variables (report `when` verbatim vs. partially evaluate)?

## Environment

Copier 9.18.1, Python 3.11.14, Linux (Ubuntu)
