# Runbooks

## Completion check hook (C5.T1)

**What it does:** `.claude/settings.json` in this repo has a Stop hook. Whenever a Claude Code session in this project tries to finish a turn, it runs `pytest` (offline suite, `mcp/tests`) and `scripts/check_packs.py`. If either fails, the stop is blocked once and the last 15 lines of output are handed back to Claude to fix. If the checks still fail on the next stop (`stop_hook_active` is true), the hook lets the session stop and prints a warning, so it can never loop.

**Needs:** the project venv at `~/.venvs/rental-insights` (Git Bash runs the hook). No cloud access: live tests stay skipped unless `RI_LIVE=1`.

**When it loads:** Claude Code reads project settings at session start. A session that started before `.claude/settings.json` existed does not run it; start a new session.

**Turn it off for one session:** start Claude Code with hooks disabled, or remove the Stop entry from `.claude/settings.json` (it is versioned, so `git checkout` restores it).

### Trial log
| Date | Trial | Hook result |
|---|---|---|
| 2026-10-13 | Passing suite and template pack | exit 0 (stop allowed) |
| 2026-10-13 | Planted failing test `mcp/tests/test_trial_fail.py`, first stop | exit 2: stop blocked, failure tail returned (`.F` and the assert) |
| 2026-10-13 | Same failing test, second stop (`stop_hook_active: true`) | exit 0 with warning: blocked once only |
| 2026-10-13 | Planted pack folder `packs/zz_trial/` without PACK.md | exit 2: blocked, message names the missing PACK.md |

The trial ran the exact command from `.claude/settings.json` with a synthetic Stop payload piped in (Claude, unattended run). The planted test and folder were removed afterwards. The hook has not yet fired inside a live session: that needs a new session (open item).
