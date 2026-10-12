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

## Features

- **Diff Mode (`law-lint diff`)**: Scans modified lines in `git diff` (or staged `--staged`) and flags touched compliance areas.
- **File Mode (`law-lint check <path>...`)**: Scans entire files or directories.
- **Rule Bundles**: Ships with built-in default rule profiles (licensing, crypto, personal data, scraping, AI safety), and can load custom rule YAMLs (`--rules path/to/rules.yml`).
- **Project-Aware Scoping (`law-lint prepare`)**: Reads `.copier-answers.yml` (daimonion/copier history), derives the project type and domain traits, evaluates each rule's gate, and prints or writes (`.law-lint-rules.yml` with `--write`) exactly the obligations that apply — e.g. a `web_api` project gets the Japanese third-party-transmission and EU accessibility duties, while a `script` project skips them. `check`, `diff`, and `list-rules` automatically scope themselves when a `.copier-answers.yml` or prepared rules file is present (`--all` opts out).
- **Zero Heavy Dependencies**: Lightweight (`pyyaml` only), instant execution in CI and local pre-commit hooks.
