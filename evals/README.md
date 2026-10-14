# Agent eval harness (PHI-7)

Same coding task(s), twice: once with the AGENTS.md rules block, once without.
Count violations (raw PII in logs, …) per arm. Numbers get published later —
this harness only has to be reproducible.

## Quick start (no agent needed)

```sh
python evals/run.py --dry-run
```

Scores the checked-in fixtures under `evals/fixtures/` and prints the
with/without comparison table. Exit code is always 0 — the table is the
result, not a gate.

```sh
python evals/run.py --dry-run --format json
```

Machine-readable rows (`task_id`, `arm`, `violations`, `sinks`, `passed`).

## Layout

- `tasks.py` — 4 task prompts (signup logging, checkout error context,
  request debug logging, failed-login audit). Prompts stay identical across
  arms; only the rules block differs.
- `scorer.py` — regex + AST checks: finds log sink calls (`logger.*`,
  `print`, `sys.stderr.write`) receiving a raw email/phone/`.email`/`.phone`
  outside a mask/redact/hash call or a redacted (`***`) template.
  Versioned (`SCORER_VERSION`); quote it with any published number.
- `run.py` — `--dry-run` (fixtures) and `--run` (real agent) modes.
- `fixtures/` — sample agent outputs per task: `<task>_without.py`
  (violating, as if no rules block) and `<task>_with.py` (compliant, as if
  the block was followed).

## Plugging in a real agent runner

Implement this interface (see `run.py:AgentRunner`) anywhere importable:

```python
class MyRunner:
    def run_task(self, task_id: str, prompt: str, rules_block: str | None) -> str:
        """Run one task; return the agent-produced code as a string."""
        ...
```

- The harness calls `run_task` twice per task: `rules_block=None`
  (without arm) and `rules_block=<markdown>` (with arm — prepend it to the
  system prompt or the AGENTS.md context, verbatim).
- Then:

```sh
python evals/run.py --run --runner mypackage.runners:MyRunner
```

Tips for reproducible numbers: pin the model + version, temperature 0, fixed
seed where supported, one run per arm per task at minimum (note the *n*);
record all of it alongside the table. The scorer version is printed above the
table — include it too.
