"""Cite-or-refuse contract shared by every tool (C3.T3).

Each tool returns one dict built here. A response that would break the contract raises
instead of reaching the client:
- answered and no_data carry at least one source key (a gold table or a wiki section);
- refused, needs_clarification and error carry a reason and no data.
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

CITED = {"answered", "no_data"}
UNCITED = {"refused", "needs_clarification", "error"}
STATUSES = CITED | UNCITED

DEFAULT_LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "tool_calls.jsonl"
LOG_PATH = DEFAULT_LOG_PATH
# Set RI_TOOL_LOG to send rows elsewhere; read at each call, so pytest (conftest.py) can point it
# at a temp file and never touch the real log (OI-237). A test that patches LOG_PATH itself wins.
LOG_ENV = "RI_TOOL_LOG"
# One id per server process, so rows from one session group together. RI_RUN_ID (read at each
# call) overrides it, for example to tag an eval run; otherwise a uuid made when this module loads.
RUN_ID_ENV = "RI_RUN_ID"
PROCESS_RUN_ID = uuid.uuid4().hex


def log_path() -> Path:
    if LOG_PATH != DEFAULT_LOG_PATH:
        return Path(LOG_PATH)
    override = os.environ.get(LOG_ENV)
    return Path(override) if override else DEFAULT_LOG_PATH


def run_id() -> str:
    return os.environ.get(RUN_ID_ENV) or PROCESS_RUN_ID


def response_bytes(result: dict) -> int:
    """Size of the response as the client receives it: UTF-8 bytes of its JSON."""
    return len(json.dumps(result, default=str).encode("utf-8"))


def response(status: str, *, source_keys=(), data=None, reason: str = "", **extra) -> dict:
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    source_keys = list(source_keys)
    if status in CITED and not source_keys:
        raise ValueError(f"{status} response has no source_keys")
    if status in UNCITED and (data is not None or not reason):
        raise ValueError(f"{status} response must carry a reason and no data")
    out = {"status": status, "source_keys": source_keys}
    if data is not None:
        out["data"] = data
    if reason:
        out["reason"] = reason
    out.update(extra)
    return out


def log_call(tool: str, started: float, result: dict, **detail) -> None:
    """One JSON line per tool call, at every return point. Never blocks the answer."""
    row = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": tool,
        "status": result.get("status"),
        "code": result.get("code"),
        "ms": round((time.perf_counter() - started) * 1000),
    }
    try:
        row["run_id"] = run_id()
        row["response_bytes"] = response_bytes(result)
    except Exception:
        pass  # observability fields are additive; never let them stop the row or the answer
    row.update(detail)
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception:
        pass  # logging is additive; a failed write must not change the answer
