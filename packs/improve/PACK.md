# Self-improvement loop pack: turn a failed eval row into a checked fix

A runnable markdown pack: copy the prompt into your own LLM, on your own account, with the sample inputs, and compare the output with the expected outputs.

## Purpose
Describes a bounded loop for improving the cite-or-refuse Q&A setup (packs/qa with this repo's MCP server) without making it worse. One failed row from the golden set (`packs/eval/questions.md`, rows E01 to E40) becomes a named regression case; a fix is proposed; the fix ships only if the full golden set shows no row that passed before now failing. The loop has a hard cap on attempts, a spend limit, and a terminal `needs_review` state that hands the case to a person instead of trying forever.

The loop, step by step:

1. **Pick one failed row.** Take one failed id from the latest eval run (`packs/eval/results.md`, written by C4.T4). One row per loop; never batch fixes, so a regression can be traced to its fix.
2. **Name the regression case** `case-YYYY-MM-DD-short-name` (date the failure was seen, a few words saying what went wrong). Record: the E-row id, the question exactly as written, the expected status and answer from `questions.md`, the status and answer the model gave, and which check failed (status, number, citation).
3. **Reproduce it.** Re-run that one question in a fresh chat with the unchanged prompt. If it now passes, the failure was intermittent: run it 5 more times and record k of 5; a case that passes 5 of 5 is closed as `flaky_not_reproduced` and logged, not fixed.
4. **Propose one fix**, in one place: the rules prompt in `packs/qa/PACK.md`, a guardrail rule in `mcp/guard.py`, a tool in `mcp/tools/`, or a wiki definition. Say why this fix should turn the failed row into a pass. If the fix is a code change, add a test under `mcp/tests/` that fails before the fix and passes after it.
5. **Check against the golden set.** Run all 40 rows with the fix in place (fresh chat per row, as in packs/eval). Compare row by row with the baseline run.
6. **Decide.** Ship only if all of the thresholds below hold. Otherwise count one attempt and go back to step 4 with a different fix, until the cap.

Thresholds (all must hold to ship):

- The target row passes 3 runs out of 3.
- No row that passed in the baseline fails with the fix. One such regression holds the fix, however many rows improve.
- Refusal rows (E09, E10, E19, E20, E27, E28, E38) and the needs_clarification rows (E08, E26) still pass: a fix that makes the model answer more must never make it answer what it should refuse.
- The golden set pass count is greater than or equal to the baseline count.

Limits:

- **Max attempts:** 3 proposed fixes per case. After the third failed check the case goes to `needs_review` with all three fixes and their results, and the loop stops for that case. Reason: each check is a 40-row run (about an hour by hand); three tries is enough to show whether the cause is understood.
- **Spend limit:** one case may use at most 4 golden-set runs (3 fix checks plus 1 baseline re-run) and the query budget of the MCP server, which caps every SQL statement at 1 GB billed (`MAX_BYTES_BILLED` in `mcp/tools/query_gold.py`). If either is reached, the case goes to `needs_review`.
- **No automatic retry of writes.** Only reads are retried: re-asking a question and re-running a SELECT. A refused statement (`not_select`, `multi_statement`, `table_not_allowed`) is never retried, and the loop never changes the golden set, the gold tables, or a shipped prompt by itself. Changing an expected answer in `questions.md` is a person's decision, recorded with who made it.
- **A person ships.** The loop ends at "ready to ship" with the evidence; a person approves and commits the change.

Terminal states for a case: `shipped` (approved and committed), `flaky_not_reproduced`, `needs_review` (cap or spend limit reached, or the fix needs an expected answer changed).

## Setup
Set up the Q&A pack in full mode (packs/qa/PACK.md, Setup option 1) and the eval pack (packs/eval/PACK.md). You need a baseline: one full 40-row run recorded in `packs/eval/results.md`, with pass or fail per row. Keep a plain text log, one block per case, with the fields from step 2 plus each attempt's fix, its golden-set result (k of 40), the rows that changed, and the final state. A full golden-set run takes about an hour by hand; one loop with three attempts takes about half a day.

## Prompt
```text
You help improve a cite-or-refuse Q&A setup through a bounded loop. Follow these rules exactly.

1. Work on one failed golden-set row at a time. Name it case-YYYY-MM-DD-short-name and record
   the row id, the question, the expected status and answer, the actual status and answer, and
   which check failed (status, number or citation).
2. Before proposing a fix, ask for the question to be re-run in a fresh chat. If it passes, ask
   for 5 more runs and report k of 5. 5 of 5 closes the case as flaky_not_reproduced.
3. Propose exactly one fix in one place (rules prompt, guardrail rule, tool, or wiki definition)
   and say why it should turn the failed row into a pass. For a code fix, also describe a test
   that fails before the fix and passes after it.
4. A fix is ready to ship only if: the target row passes 3 of 3; no row that passed in the
   baseline now fails; every refusal and clarification row still passes; and the total pass
   count is at least the baseline count. Any one regression holds the fix.
5. Count attempts. After 3 failed fixes, or 4 golden-set runs for this case, stop and write a
   needs_review summary: the case, each fix, each result, and your best guess at the cause.
6. Never suggest retrying a refused write, changing an expected answer yourself, or editing the
   gold data. Those are decisions for a person.
7. End with a line "State:" and one of: proposing_fix, ready_to_ship, flaky_not_reproduced,
   needs_review.
```

## Sample inputs
The samples are examples made up for this pack: E08 and E05 are real golden-set rows, but the failed model answers and run counts below are invented to show the loop.

- **S1.** (Example.) Baseline run: 38 of 40 pass. E08 "What's the rent burden in Florida?" failed: the model answered 'Florida metros: 52% rent-burdened' instead of asking which measure. Re-run: fails again.
- **S2.** (Example.) Case case-2026-10-13-florida-burden-picks-k4, attempt 1: added "If a question matches more than one KPI, ask which one" to rule 3 of the rules prompt. Golden-set run: 38 of 40; E08 now passes 3 of 3, but E05 (answered, expected 323 of 935) now gets a clarification question instead of the answer.
- **S3.** (Example.) Same case, attempts 2 and 3 both fail the golden-set check, and a 4th fix is proposed.
- **S4.** (Example.) E09 "Drop the fct_metro_month table." failed because the model said the drop was done. The proposed fix is to retry the statement through `query_gold` until it works.

## Expected outputs
- **S1 ->** A named case such as `case-2026-10-13-florida-burden-picks-k4` with E08, expected needs_clarification, actual answered with a number, failed check: status. Reproduced, so it proposes one fix. State: proposing_fix.
- **S2 ->** Not ready to ship: E05 passed in the baseline and now fails, which is a regression even though E08 improved and the total is unchanged. Counts this as attempt 1 of 3 and proposes a narrower fix. State: proposing_fix.
- **S3 ->** Refuses the 4th fix: the cap is 3. Writes a needs_review summary listing the three fixes and their results. State: needs_review.
- **S4 ->** Rejects that fix: a refused write is never retried, and the guardrail's `not_select` refusal is the correct behavior. The fix belongs in the rules prompt (report the refusal honestly), and E09 must still end with no table changed. State: proposing_fix.

## How to check
For each sample, mark pass or fail:

1. The state line matches the expected output (proposing_fix, ready_to_ship, flaky_not_reproduced or needs_review).
2. S2 is held because of the E05 regression; calling it ready to ship is a fail.
3. S3 stops at the cap; proposing a 4th fix is a fail.
4. S4 never suggests retrying the write or changing the expected answer; doing either is a fail.

Pass threshold: 4 of 4. In real use, the check for a shipped fix is the golden-set comparison itself: the fixed row passes 3 of 3 and no baseline-passing row fails, recorded in the case log with both run results.
