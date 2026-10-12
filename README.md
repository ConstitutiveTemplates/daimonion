# law-lint

Fast, lightweight linter that inspects source files and `git diff` changes against legal and ethical triggers (intellectual property, cryptography, privacy, data governance, security policies).

Part of the [ConstitutiveTemplates](https://github.com/ConstitutiveTemplates) ecosystem.

## Why law-lint?

Rather than dumping thousands of lines of full legal commentary into your AI system prompts or `AGENTS.md`, `law-lint` inspects code changes as they happen. It surfaces only the concise rules and compliance requirements relevant to the code being touched.

## Installation & Quickstart

```sh
# Run via uvx without installing
uvx law-lint diff

# Or check specific files or directories
uvx law-lint check src/
```

## Features

- **Diff Mode (`law-lint diff`)**: Scans modified lines in `git diff` (or staged `--staged`) and flags touched compliance areas.
- **File Mode (`law-lint check <path>...`)**: Scans entire files or directories.
- **Rule Bundles**: Ships with built-in default rule profiles (licensing, crypto, personal data, scraping, AI safety), and can load custom rule YAMLs (`--rules path/to/rules.yml`).
- **Zero Heavy Dependencies**: Lightweight (`pyyaml` only), instant execution in CI and local pre-commit hooks.
