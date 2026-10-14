"""Scorer + dry-run regression tests for the PHI-7 eval harness."""

from evals.run import dry_run_table
from evals.scorer import score_code


def test_violating_snippet_fails():
    score = score_code("import logging\nlogger.info('hi %s', user.email)\n")
    assert not score.passed
    assert score.violation_count == 1


def test_masked_snippet_passes():
    code = "import hashlib\nlogger.info('hi %s', hashlib.sha256(user.email.encode()).hexdigest())\n"
    assert score_code(code).passed


def test_dry_run_fixtures_separate():
    rows = dry_run_table()
    by_task = {}
    for row in rows:
        by_task.setdefault(row.task_id, {})[row.arm] = row
    assert len(by_task) == 4
    for arms in by_task.values():
        assert not arms["without"].passed
        assert arms["with"].passed
