"""
Tests for the history / undo-redo service.
"""
from __future__ import annotations

import pytest

from backend.services.history_service import HistoryService


def test_push_and_undo():
    hist = HistoryService()
    snap1 = {"ir": {"nodes": ["a"]}, "tikz": "code1"}
    snap2 = {"ir": {"nodes": ["b"]}, "tikz": "code2"}
    hist.push("sess1", snap1["ir"], snap1["tikz"])
    hist.push("sess1", snap2["ir"], snap2["tikz"])
    restored = hist.undo("sess1")
    assert restored is not None
    assert restored["ir"] == snap1["ir"]


def test_undo_nothing_returns_none():
    hist = HistoryService()
    hist.push("s", {"a": 1}, "code")
    result = hist.undo("s")
    assert result is None  # Only one entry – nothing to undo


def test_redo_after_undo():
    hist = HistoryService()
    hist.push("s", {"v": 1}, "c1")
    hist.push("s", {"v": 2}, "c2")
    hist.undo("s")
    restored = hist.redo("s")
    assert restored is not None
    assert restored["ir"] == {"v": 2}


def test_redo_nothing_returns_none():
    hist = HistoryService()
    result = hist.redo("s")
    assert result is None


def test_push_clears_redo_stack():
    hist = HistoryService()
    hist.push("s", {"v": 1}, "c1")
    hist.push("s", {"v": 2}, "c2")
    hist.undo("s")
    hist.push("s", {"v": 3}, "c3")  # New action – clears redo
    result = hist.redo("s")
    assert result is None


def test_clear():
    hist = HistoryService()
    hist.push("s", {"v": 1}, "c1")
    hist.clear("s")
    assert hist.current("s") is None
