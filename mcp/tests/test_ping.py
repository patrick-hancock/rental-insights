"""C3.T1: the ping tool is listed and returns 'pong', in-process and over stdio."""

import asyncio
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

from server import server  # noqa: E402


async def _list_and_call(target):
    async with Client(target, read_timeout_seconds=30) as client:
        tools = await client.list_tools()
        result = await client.call_tool("ping", {})
    return [t.name for t in tools.tools], result


def _text(result):
    return [c.text for c in result.content if getattr(c, "type", None) == "text"]


def test_ping_in_process():
    names, result = asyncio.run(_list_and_call(server))
    assert "ping" in names
    assert not result.is_error
    assert _text(result) == ["pong"]


def test_ping_over_stdio():
    # Same launch path Claude Desktop uses: this venv's python running server.py.
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_DIR / "server.py")])
    names, result = asyncio.run(_list_and_call(params))
    assert "ping" in names
    assert _text(result) == ["pong"]
