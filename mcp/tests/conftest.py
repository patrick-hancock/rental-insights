"""Shared pytest setup for mcp/tests.

Every test writes tool-log rows to its own temp file, never to the real
mcp/logs/tool_calls.jsonl (OI-237). RI_TOOL_LOG is read by tools/contract.py at each call.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolated_tool_log(tmp_path, monkeypatch):
    path = tmp_path / "tool_calls.jsonl"
    monkeypatch.setenv("RI_TOOL_LOG", str(path))
    return path
