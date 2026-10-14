"""Shared fixtures: keep the developer's locale out of human-output assertions."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _english_output(monkeypatch):
    """Human output is English with emoji unless a test opts into ``--lang``/``--no-emoji``."""
    for var in ("DAIMONION_LANG", "DAIMONION_NO_EMOJI", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)
