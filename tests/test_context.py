"""Tests for copier-answer context derivation, gate evaluation, and rule scoping."""

from __future__ import annotations

import warnings

import pytest

from daimonion.context import derive_context, gate_eval, scope_rules
from daimonion.models import Rule
from daimonion.rules import BUILTIN_RULES


def _rule(rule_id: str, gate: str) -> Rule:
    return Rule(id=rule_id, title=f"title of {rule_id}", triggers="trigger", summary="summary", gate=gate)


def test_derive_context_web_api():
    """A web_api project with personal data and commercial distribution."""
    ctx = derive_context(
        {
            "project_type": "web_api",
            "domain_traits": ["personal-data"],
            "distribution": ["commercial"],
            "include_mcp": True,
        }
    )
    assert ctx["project_type"] == "web_api"
    assert ctx["web_api"] is True
    assert ctx["mcp_effective"] is True
    assert ctx["data_science_layout"] is False
    assert ctx["ds_stack"] is False
    assert ctx["oj_code"] is False
    assert ctx["domain_traits"] == ["personal-data"]
    assert ctx["distribution"] == ["commercial"]


def test_derive_context_script_ignores_include_layers():
    """``script`` is not combinable, so include_* layers never widen the context."""
    ctx = derive_context({"project_type": "script", "include_web_api": True, "include_data_science": True})
    assert ctx["web_api"] is False
    assert ctx["data_science_layout"] is False
    assert ctx["ds_stack"] is False
    assert ctx["mcp_effective"] is False


def test_derive_context_scraping_requires_cli():
    assert derive_context({"project_type": "cli", "include_scraping": True})["scraping_effective"] is True
    assert derive_context({"project_type": "web_api", "include_scraping": True})["scraping_effective"] is False


def test_derive_context_scraping_memorious_requires_engine():
    ctx = derive_context({"project_type": "cli", "include_scraping": True, "scraping_engine": "memorious"})
    assert ctx["scraping_memorious_effective"] is True
    off = derive_context({"project_type": "cli", "include_scraping": True, "scraping_engine": "requests"})
    assert off["scraping_memorious_effective"] is False


def test_derive_context_normalizes_trait_and_distribution_shapes():
    """A bare string is one choice, a list is many, anything else is no choice."""
    ctx = derive_context({"project_type": "cli", "domain_traits": "medtech", "distribution": 7})
    assert ctx["domain_traits"] == ["medtech"]
    assert ctx["distribution"] == []


def test_derive_context_kaggle_sets_ds_stack():
    ctx = derive_context({"project_type": "online_judge", "oj_kind": "kaggle"})
    assert ctx["ds_stack"] is True
    assert ctx["oj_code"] is True
    assert ctx["oj_ctf"] is False

    ctf = derive_context({"project_type": "online_judge", "oj_kind": "ctf"})
    assert ctf["oj_ctf"] is True
    assert ctf["oj_code"] is False


@pytest.mark.parametrize(
    "answers",
    [
        {},
        {"project_type": "cli"},
        {"project_type": "library", "license": "Apache-2.0"},
        {"project_type": "web_api", "include_mcp": True, "domain_traits": ["personal-data"]},
        {"project_type": "data_science", "include_scraping": True},
        {"project_type": "online_judge", "oj_kind": "kaggle"},
        {"project_type": "online_judge", "oj_kind": "atcoder"},
    ],
)
def test_every_builtin_gate_evaluates(answers):
    """Each gate shipped in rules.py resolves against a derived context (no NameError)."""
    ctx = derive_context(answers)
    for rule in BUILTIN_RULES:
        assert isinstance(gate_eval(rule.gate, ctx), bool)


def test_gate_eval_empty_and_whitespace_gate_is_always_on():
    ctx = derive_context({})
    assert gate_eval("", ctx) is True
    assert gate_eval("   ", ctx) is True


def test_scope_rules_includes_and_excludes():
    """cli scoping keeps always-on + cli-gated rules and drops web_api-gated ones."""
    ctx = derive_context({"project_type": "cli"})
    scoped = {rule.id for rule in scope_rules(BUILTIN_RULES, ctx)}
    assert "deprecated-crypto" in scoped  # empty gate -> always-on
    assert "ai-copyright" in scoped  # gate: project_type == 'cli'
    assert "eu-eaa-accessibility" not in scoped  # gate: web_api
    assert "jp-external-transmission" not in scoped  # gate: web_api
    assert "personal-data-privacy" not in scoped  # gate: domain_traits


def test_scope_rules_web_api_includes_web_gated_rules():
    ctx = derive_context({"project_type": "web_api", "distribution": ["commercial"]})
    scoped = {rule.id for rule in scope_rules(BUILTIN_RULES, ctx)}
    assert {"eu-eaa-accessibility", "jp-external-transmission", "eu-cra-compliance"} <= scoped
    assert "ai-copyright" not in scoped  # cli/data_science only


def test_scope_rules_malformed_gate_fails_closed():
    """A gate that cannot be evaluated excludes its rule and warns, without crashing."""
    rules = [
        _rule("ok", ""),
        _rule("broken", "project_type =="),
        _rule("hostile", "__import__('os').system('id')"),
        _rule("unbound", "mystery_flag"),
        _rule("also-ok", "project_type == 'cli'"),
    ]
    with pytest.warns(UserWarning) as record:
        scoped = scope_rules(rules, derive_context({"project_type": "cli"}))

    assert [rule.id for rule in scoped] == ["ok", "also-ok"]
    messages = " ".join(str(warning.message) for warning in record)
    for rule_id in ("broken", "hostile", "unbound"):
        assert rule_id in messages
    assert "also-ok" not in messages


def test_scope_rules_does_not_warn_on_valid_gates():
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        scope_rules(BUILTIN_RULES, derive_context({"project_type": "web_api"}))
    assert [w for w in record if issubclass(w.category, UserWarning)] == []


@pytest.mark.parametrize("gate", ["project_type ==", "project_type == 'cli' and", "not a gate ("])
def test_gate_eval_rejects_malformed_expressions(gate):
    with pytest.raises(ValueError):
        gate_eval(gate, derive_context({}))


def test_gate_eval_rejects_unbound_flag():
    with pytest.raises(ValueError, match="unbound"):
        gate_eval("mystery_flag", derive_context({}))
