"""C8.T2: validate agent handoffs for the multi-agent workflow pack (packs/agents).

    python scripts/validate_handoff.py FILE.json [FILE.json ...]   check handoffs; exit 0 if all valid
    python scripts/validate_handoff.py --selftest                  every good sample must pass and every
                                                                   bad sample must fail with the code its
                                                                   file name starts with
    python scripts/validate_handoff.py --sign FILE.json            print the digest a handoff should carry

Checks, in order (the first failure is reported):
  schema      shape, types and allowed values (packs/agents/handoff.schema.json)
  digest      sha256 of the canonical JSON of all other fields matches `digest`: catches a handoff
              edited after it was written. This is a tamper check, not authentication: anyone can
              recompute a digest, so the chain below is what ties a handoff to its parent.
  chain       parent_digest matches the digest of the handoff named as parent (when given)
  route       from_agent -> to_agent is an allowed step of the workflow
  sources     every evidence source_key is a gold table or a wiki/kpis.md section the project has
  evidence    status answered needs at least one evidence item; refusals and clarifications carry none
  injection   question and notes hold no instruction-like text aimed at the next agent
"""

import hashlib
import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[1]
PACK = REPO / "packs" / "agents"
SCHEMA = json.loads((PACK / "handoff.schema.json").read_text(encoding="utf-8"))
ROUTES = {
    ("user", "planner"), ("planner", "analyst"), ("planner", "user"),
    ("analyst", "writer"), ("writer", "reviewer"), ("reviewer", "user"), ("reviewer", "writer"),
}
GOLD = {"gold.fct_metro_month", "gold.fct_cbsa_affordability", "gold.dim_metro", "gold.dim_date"}
KPI_KEY = re.compile(r"^wiki/kpis\.md#k[1-8]-[a-z0-9-]+$")
NO_EVIDENCE = {"needs_clarification", "refused", "planned"}
INJECTION = re.compile(
    r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above|all)\b.{0,20}\b(instructions?|rules)\b"
    r"|\byou are now\b|\bsystem prompt\b|^\s*(system|assistant)\s*:", re.I | re.M)


def digest(handoff: dict) -> str:
    body = {k: v for k, v in handoff.items() if k != "digest"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate(handoff, parent: dict | None = None) -> tuple[str, str]:
    """Return ("ok", "") or (code, reason) for the first failed check."""
    errors = sorted(Draft202012Validator(SCHEMA).iter_errors(handoff), key=lambda e: list(e.path))
    if errors:
        e = errors[0]
        return "schema", f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}"
    if digest(handoff) != handoff["digest"]:
        return "digest", "content does not match its digest (edited after it was written)"
    if parent is not None and handoff["parent_digest"] != parent["digest"]:
        return "chain", f"parent_digest does not match {parent['handoff_id']}"
    if (handoff["from_agent"], handoff["to_agent"]) not in ROUTES:
        return "route", f"{handoff['from_agent']} -> {handoff['to_agent']} is not a step of the workflow"
    for ev in handoff["evidence"]:
        if ev["source_key"] not in GOLD and not KPI_KEY.match(ev["source_key"]):
            return "sources", f"unknown source key {ev['source_key']}"
    if handoff["status"] == "answered" and not handoff["evidence"]:
        return "evidence", "answered with no evidence"
    if handoff["status"] in NO_EVIDENCE and handoff["evidence"]:
        return "evidence", f"{handoff['status']} must not carry evidence"
    if INJECTION.search(handoff["question"] + "\n" + handoff["notes"]):
        return "injection", "instruction-like text in question or notes"
    return "ok", ""


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def parent_of(path: Path, handoff, folder: Path | None = None):
    """The parent is the handoff with the previous id (H-002's parent is H-001), looked up in `folder`
    (default: the file's own folder). The selftest looks in samples/good, the one real chain."""
    if not isinstance(handoff, dict) or not handoff.get("parent_digest"):
        return None
    m = re.match(r"^H-(\d{3})$", str(handoff.get("handoff_id", "")))
    if not m:
        return None
    want = f"H-{int(m.group(1)) - 1:03d}"
    for p in sorted((folder or path.parent).glob("*.json")):
        try:
            other = load(p)
        except json.JSONDecodeError:
            continue
        if isinstance(other, dict) and other.get("handoff_id") == want and p != path:
            return other
    return None


def selftest() -> int:
    chain = PACK / "samples" / "good"
    good = sorted(chain.glob("*.json"))
    bad = sorted((PACK / "samples" / "bad").glob("*.json"))
    failures = 0
    for p in good:
        h = load(p)
        code, reason = validate(h, parent_of(p, h, chain))
        ok = code == "ok"
        failures += not ok
        print(f"{'OK  ' if ok else 'FAIL'} good/{p.name}: {code} {reason}")
    for p in bad:
        expected = p.name.split("-", 1)[0]
        try:
            h = load(p)
            code, reason = validate(h, parent_of(p, h, chain))
        except json.JSONDecodeError as e:
            code, reason = "schema", f"not JSON: {e}"
        ok = code == expected
        failures += not ok
        print(f"{'OK  ' if ok else 'FAIL'} bad/{p.name}: rejected as {code} (expected {expected}) {reason}")
    print(f"good accepted {sum(1 for p in good if validate(load(p), parent_of(p, load(p), chain))[0] == 'ok')} of {len(good)}; "
          f"selftest {'passed' if not failures else 'FAILED'} ({failures} failure(s))")
    if len(good) < 5 or len(bad) < 5:
        print(f"FAIL need 5 or more of each; have {len(good)} good, {len(bad)} bad")
        return 1
    return 1 if failures else 0


def main(argv) -> int:
    if argv[:1] == ["--selftest"]:
        return selftest()
    if argv[:1] == ["--sign"]:
        print(digest(load(Path(argv[1]))))
        return 0
    if not argv:
        print(__doc__)
        return 2
    bad = 0
    for a in argv:
        p = Path(a)
        h = load(p)
        code, reason = validate(h, parent_of(p, h))
        bad += code != "ok"
        print(f"{'OK  ' if code == 'ok' else 'FAIL'} {p.name}: {code} {reason}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
