"""Runner + agent interface contract for the PHI-7 agent eval.

Two modes:

* ``--dry-run`` — score the checked-in fixtures under ``evals/fixtures/``
  (``<task>_without.py`` = simulated agent output without the AGENTS.md rules
  block, ``<task>_with.py`` = with the block) and print the comparison table.
  No agent, no network, fully reproducible.
* ``--run`` — replay every task through a real agent runner (twice per task),
  score each output, and print the same table as JSON or Markdown. Needs
  ``--runner dotted.path:Class`` implementing :class:`AgentRunner`.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

ROOT = Path(__file__).resolve().parent
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from evals.scorer import SCORER_VERSION, Score, score_file
from evals.tasks import TASKS


class AgentRunner(Protocol):
    """Interface a real agent runner must implement.

    The harness replays each task prompt twice: once with no extra context
    (``rules_block=None``) and once with the AGENTS.md rules block prepended
    (``rules_block=<markdown string>``). ``run_task`` returns the agent's
    produced code as a string.
    """

    def run_task(self, task_id: str, prompt: str, rules_block: str | None) -> str:
        """Run one task; return the agent-produced code."""
        ...  # pragma: no cover


@dataclass(frozen=True)
class ArmResult:
    task_id: str
    arm: str  # "without" | "with"
    violations: int
    sinks: int
    passed: bool
    detail: str = ""


def rules_block_text() -> str:
    """The rules block injected in the ``with`` arm.

    Today: the personal-data section rendered the same way ``daimonion
    agents-md`` renders it (imperative lines + sources). Kept inline so the
    dry-run fixtures stay reproducible without a kanon checkout.
    """
    return (
        "### Personal data -- minimise before you collect\n"
        "\n"
        "- NEVER pass raw user identifiers to logging or error trackers.\n"
        "- Minimise collection: ask whether each identifier is needed.\n"
        "- Provide a deletion path for stored personal data.\n"
        "\n"
        "Sources: [eur-lex.europa.eu](https://eur-lex.europa.eu/eli/reg/2016/679/oj), "
        "[ppc.go.jp](https://www.ppc.go.jp/personalinfo/legal/)\n"
    )


def score_to_result(task_id: str, arm: str, score: Score) -> ArmResult:
    detail = "; ".join(f"line {f.line} {f.sink}: {f.reason}" for f in score.violations)
    return ArmResult(
        task_id=task_id,
        arm=arm,
        violations=score.violation_count,
        sinks=score.sink_calls,
        passed=score.passed,
        detail=detail,
    )


def dry_run_table() -> list[ArmResult]:
    """Score every fixture; return one row per (task, arm)."""
    rows: list[ArmResult] = []
    for task in TASKS:
        for arm in ("without", "with"):
            fixture = ROOT / "fixtures" / f"{task.id}_{arm}.py"
            score = score_file(str(fixture))
            rows.append(score_to_result(task.id, arm, score))
    return rows


def render_markdown(rows: list[ArmResult]) -> str:
    lines = [
        f"<!-- scorer v{SCORER_VERSION}; fixtures under evals/fixtures/ -->",
        "",
        "| task | without block | with block |",
        "| --- | --- | --- |",
    ]
    by_task: dict[str, dict[str, ArmResult]] = {}
    for row in rows:
        by_task.setdefault(row.task_id, {})[row.arm] = row

    def cell(r: ArmResult) -> str:
        mark = "PASS" if r.passed else f"FAIL ({r.violations} violation(s))"
        return f"{mark}, {r.sinks} sink(s)"

    for task in TASKS:
        arms = by_task[task.id]
        lines.append(f"| {task.id} | {cell(arms['without'])} | {cell(arms['with'])} |")
    without = sum(r.violations for r in rows if r.arm == "without")
    with_ = sum(r.violations for r in rows if r.arm == "with")
    lines += [
        "",
        (
            f"Total violations: {without} without the rules block, {with_} with it "
            f"({len(TASKS)} tasks, scorer v{SCORER_VERSION})."
        ),
    ]
    return "\n".join(lines)


def load_runner(dotted: str) -> AgentRunner:
    """Import ``dotted.path:Class`` (or ``dotted.path.Class``) and instantiate it."""
    path, _, attr = dotted.replace(":", ".").rpartition(".")
    module = importlib.import_module(path)
    cls = getattr(module, attr)
    return cls()


def live_run(runner: AgentRunner, fmt: str) -> str:  # pragma: no cover
    from evals.scorer import score_code

    rows: list[ArmResult] = []
    block = rules_block_text()
    for task in TASKS:
        for arm, rules in (("without", None), ("with", block)):
            code = runner.run_task(task.id, task.prompt, rules)
            rows.append(score_to_result(task.id, arm, score_code(code)))
    if fmt == "json":
        return json.dumps(
            {
                "scorer_version": SCORER_VERSION,
                "rows": [r.__dict__ for r in rows],
            },
            indent=2,
        )
    return render_markdown(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PHI-7 agent-eval harness")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="score checked-in fixtures")
    group.add_argument("--run", action="store_true", help="replay tasks via an agent runner")
    parser.add_argument("--runner", default="", help="dotted path to AgentRunner impl (for --run)")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)

    if args.dry_run:
        rows = dry_run_table()
    else:
        if not args.runner:
            parser.error("--run requires --runner dotted.path:Class")
        rows = []  # replaced below; keeps type-checkers calm
        output = live_run(load_runner(args.runner), args.format)
        print(output)
        return 0

    if args.format == "json":
        print(
            json.dumps(
                {
                    "scorer_version": SCORER_VERSION,
                    "mode": "dry-run",
                    "rows": [r.__dict__ for r in rows],
                },
                indent=2,
            )
        )
    else:
        print(render_markdown(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
