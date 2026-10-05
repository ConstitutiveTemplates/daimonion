# Contribute to the template
Contributions and issues are most welcome! All issues and pull requests are handled through [GitHub](https://github.com/ConstitutiveTemplates/daimonion/issues). Also, please check for any existing issues before filing a new one. If you have a great idea but it involves big changes, please file a ticket before making a pull request! We want to make sure you don't spend your time coding something that might not fit the scope of the project.

## Security

Please do not open a public issue for security vulnerabilities. Report them
privately via the [Security Advisory workflow](https://github.com/ConstitutiveTemplates/daimonion/security/advisories/new) — see [SECURITY.md](../SECURITY.md) for details.

## Issue or Discussion?

Github also offers [discussions](https://github.com/ConstitutiveTemplates/daimonion/discussions) as a place to ask questions and share ideas. If your issue is open ended and it is not obvious when it can be "closed", please raise it as a discussion instead.

## Getting changes into the template

This template is a place to pull together agreed best practices from various sources. As such, it is difficult to demonstrate a change without seeing it in action in another repo. Please link to a repo that has the desired behaviour when proposing changes to the template.


## Ethics / regional / operational rule sections

The `_shared/ethics/` sections are field rules with their own review cadence
(`review_by` per registry row), governed by
[GOVERNANCE.md](../GOVERNANCE.md): contributors draft sections and re-check
primary sources; the maintainer owns defaults and promotions. The runbook
is [docs/how-to/ethics-section.md](../docs/how-to/ethics-section.md) —
draft first, promote only when a distribution bundle forms.

## Blast radius

What a change touches decides what must pass before the PR. CI gates the
render matrix by change scope (the docs-only detector in ci.yml), so the
table below is what *you* run locally — the cheapest tier that covers the
blast radius, never the whole suite.

| Change scope | Required verification |
| --- | --- |
| Docs only (`README.md`, `docs/*.md`) | `task lint type-check` — CI skips the render matrix for docs-only PRs, so typos and format debt must be caught locally |
| Template payload (`template/`, `_shared/`, `questions/`) | `task test-fast` plus `task verify-delta` — the render twin proves which witness leaves the change can affect: a semantic diff narrows the candidate set, then only candidates are re-rendered from a baseline checkout and compared by manifest (file list + sha256, answers normalized); it exits 0 when every candidate is byte-identical |
| Questionnaire (`copier.yml`, `questions/*.yml`) | `task regen` then `task test-fast` — regen is the one-command pipeline: witness leaves, batch verdicts, tier ledger, ethics appendix, generated docs, predicate report |

## Contributing 101

The cheapest real change an outsider can make: add or update an ethics /
regional / operational rule section under `_shared/ethics/`. The walkthrough
[how-to/ethics-section.md](../docs/how-to/ethics-section.md) has the full
steps — in short: draft the section (copy `_shared/ethics/_template.md.jinja`
to the matching bundle directory, fill every field), register one
`status: draft` row in `_shared/ethics/REGISTRY.yml`, and check it with
`uv run --locked pytest tests/test_ethics_registry.py`. A promotion
(registry row goes `active` with a `gate`) then needs
`task ethics-appendix` to regenerate the appendix from the registry —
`task regen` covers that and everything else a questionnaire-facing change
touches.

## Checking your changes before making a PR

The template has tests for:

- Generating a new project from scratch
- Updating the [example project](https://github.com/kasi-x/python-copier-template-example)
- Checking that both of the above produce the same results

However, this does not test whether processes like CI and docs work correctly. You can ensure that these are checked by:

- Making your changes on a branch of <https://github.com/ConstitutiveTemplates/daimonion>
- Running `uvx copier update --vcs-ref=<branch_name>` in the repo where you would like to demonstrate the behaviour
- Linking to that demonstration repo in the PR

## Developer Information

It is recommended that developers use a [vscode devcontainer](https://code.visualstudio.com/docs/devcontainers/containers). This repository contains configuration to set up a containerized development environment that suits its own needs.

For more information on common tasks like setting up a developer environment, running the tests, and the lint workflow, see the [How-to guides](https://constitutivetemplates.github.io/daimonion/main/how-to.html)
