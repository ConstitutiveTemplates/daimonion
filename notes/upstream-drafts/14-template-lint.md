Title: A structural lint for templates (`copier template lint` or `copier copy --check`)

## Summary

Every serious Copier template ends up reimplementing the same static
checks in its own test suite: every asked question should have a `default`,
every `when:`/`default:`/`choices:` expression should only reference names
that exist (and that are defined *before* the question), every `when:`
should be satisfiable, every `_tasks`/`_migrations`/`_jinja_extensions`
reference should resolve, and every file/dir name in the template tree
should render without errors. Our own template's structural test file is
~750 lines of exactly this.

This proposes a built-in lint that runs that checklist once — either
`copier template lint <path>` or `copier copy --check <template>` — with an
error/warning split so template authors can wire it into CI without a
bespoke test harness.

## Current behavior

- The checks exist in the wild but per-template, hand-rolled, and with
  inconsistent coverage.
- Copier itself surfaces the failures late: a dead `when:` is invisible
  until someone renders that path; a dangling Jinja name surfaces as a
  `UndefinedError` at render time, not at authoring time.

## Expected behavior

- A subcommand or flag that inspects the template without rendering a
  destination, and exits non-zero on findings.
- Severity split (sketch):
  - **error**: `when:`/`default:`/`choices:` referencing an unknown name;
    a reference to a question defined *after* the consumer; an unreadable
    `copier.yml`; a `_jinja_extensions`/`_tasks` entry that cannot be
    resolved.
  - **warning**: a `when:` that can never be true; an always-true `when:`
    (noise); a question with no `default` (forces interactive use).
- Machine-readable form (`--format json`) so CI and agents can consume it
  the same way as the proposed questionnaire export.

## Design questions for discussion

- Subcommand (`copier template lint`) vs. a mode on `copy` (`--check`)?
- Should the lint be extensible (entry points / config) or a fixed
  upstream checklist?
- Should it live in copier core or as a blessed companion tool
  (`copier-lint`)?

## Environment

Copier 9.18.1, Python 3.11.14, Linux (Ubuntu)
