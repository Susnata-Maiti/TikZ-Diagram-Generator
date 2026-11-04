"""
History / undo-redo service.

Stores per-session snapshots in memory.
In production, swap the in-memory store for Redis or a DB.
"""
from __future__ import annotations

import copy
import threading
from typing import Any, Optional


class HistoryService:
    """
    Per-session undo/redo stack.

    session_id → list of (ir_dict, tikz_code) snapshots.
    """

    def __init__(self, max_depth: int = 50) -> None:
        self._lock = threading.Lock()
        self._stacks: dict[str, list[dict[str, Any]]] = {}
        self._redo_stacks: dict[str, list[dict[str, Any]]] = {}
        self._max_depth = max_depth

    def push(self, session_id: str, ir_dict: dict, tikz_code: str) -> None:
        with self._lock:
            stack = self._stacks.setdefault(session_id, [])
            stack.append({"ir": copy.deepcopy(ir_dict), "tikz": tikz_code})
            if len(stack) > self._max_depth:
                stack.pop(0)
            # Clear redo stack on new action
            self._redo_stacks.pop(session_id, None)

    def undo(self, session_id: str) -> Optional[dict[str, Any]]:
        """Pop the last snapshot and return it."""
        with self._lock:
            stack = self._stacks.get(session_id, [])
            if len(stack) < 2:
                return None
            # Move current to redo
            current = stack.pop()
            self._redo_stacks.setdefault(session_id, []).append(current)
            return copy.deepcopy(stack[-1])

    def redo(self, session_id: str) -> Optional[dict[str, Any]]:
        """Redo the last undone snapshot."""
        with self._lock:
            redo_stack = self._redo_stacks.get(session_id, [])
            if not redo_stack:
                return None
            snapshot = redo_stack.pop()
            self._stacks.setdefault(session_id, []).append(snapshot)
            return copy.deepcopy(snapshot)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._stacks.pop(session_id, None)
            self._redo_stacks.pop(session_id, None)

    def current(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            stack = self._stacks.get(session_id, [])
            return copy.deepcopy(stack[-1]) if stack else None


_history_service = HistoryService()


def get_history_service() -> HistoryService:
    return _history_service
