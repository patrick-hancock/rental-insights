"""search_wiki and get_definition over rental-insights/wiki (C3.T3).

Sections are cut at ## and ### headings; each one is cited as wiki/<file>#<slug>.
Wiki text is returned as data for the client to quote, never as instructions.
"""

import math
import re
import time
from collections import Counter
from pathlib import Path

from rapidfuzz import fuzz, process

from tools.contract import log_call, response

WIKI_DIR = Path(__file__).resolve().parents[2] / "wiki"
TOP_K = 3
SNIPPET_CHARS = 1500
# A section must explain more than half of the query's content words (coverage gate).
MIN_COVERAGE = 0.5
# Typo fallback for get_definition (fuzz.ratio, whole string). Measured 2026-10-13 on the 8 KPI
# names and columns: 6 typo probes scored 86-97, 8 non-KPI terms scored 31-67. 80 sits between.
TYPO_FLOOR = 80
# A question or KPI name fits in 500 characters; longer input is refused (C3.T4, LLM10).
MAX_QUERY_CHARS = 500

# Instruction-like text planted in a wiki section (C3.T4, LLM01/ASI01). A flagged section is
# withheld, never returned, because the client's model would read it as part of its context.
INJECTION_PATTERNS = [re.compile(p, re.I | re.M) for p in (
    r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above|earlier|all)\b.{0,20}\b(instructions?|rules|prompts?)\b",
    r"\byou are now\b",
    r"\b(system|developer) prompt\b",
    r"^\s*(system|assistant|developer)\s*:",
    r"\b(call|run|invoke|use)\b.{0,20}\b(query_gold|search_wiki|get_definition)\b",
    r"<\|[a-z_]+\|>",
    r"\bnew instructions\b",
)]


def suspicious(text: str) -> bool:
    return any(p.search(text) for p in INJECTION_PATTERNS)


STOPWORDS = set(
    "a an and are as at be by for from how i in is it of on or per the to what when where which who why with "
    "does do did show me tell about this that these those was were".split()
)


def _slug(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def _words(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in STOPWORDS or len(w) < 2:
            continue
        out.append(w[:-1] if len(w) > 3 and w.endswith("s") else w)  # light plural folding
    return out


def load_sections(wiki_dir: Path = WIKI_DIR) -> list[dict]:
    sections = []
    for path in sorted(wiki_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)  # drop note properties
        heading, body = None, []
        for line in text.splitlines() + ["## "]:
            m = re.match(r"^(#{2,3}) (.*)$", line)
            if m:
                if heading and "".join(body).strip():
                    sections.append({
                        "key": f"wiki/{path.name}#{_slug(heading)}",
                        "file": path.name,
                        "heading": heading,
                        "text": "\n".join(body).strip(),
                    })
                heading, body = m.group(2).strip(), []
            elif heading is not None:
                body.append(line)
    return sections


def search_wiki(query: str, sections: list[dict] | None = None) -> dict:
    started = time.perf_counter()
    sections = sections if sections is not None else load_sections()
    if len(query) > MAX_QUERY_CHARS:
        result = response("refused", code="too_large", reason=f"Input is over {MAX_QUERY_CHARS} characters.")
        log_call("search_wiki", started, result, chars=len(query))
        return result
    corpus_keys = sorted({f"wiki/{s['file']}" for s in sections})
    terms = list(dict.fromkeys(_words(query)))
    if not terms:
        result = response("needs_clarification", reason="The query has no searchable words; name a topic, KPI or decision.")
        log_call("search_wiki", started, result, query=query)
        return result

    docs = [Counter(_words(s["heading"] + " " + s["text"])) for s in sections]
    n = len(docs)
    df = {t: sum(1 for d in docs if t in d) for t in terms}
    scored = []
    for s, d in zip(sections, docs):
        matched = [t for t in terms if t in d]
        coverage = len(matched) / len(terms)
        if coverage <= MIN_COVERAGE:
            continue
        score = sum(math.log(1 + n / df[t]) * (1 + math.log(d[t])) for t in matched)
        scored.append((score, coverage, s))
    scored.sort(key=lambda x: (-x[0], x[2]["key"]))

    withheld = [s["key"] for _, _, s in scored if suspicious(s["heading"] + "\n" + s["text"])]
    clean = [(c, s) for _, c, s in scored if s["key"] not in withheld]
    if not scored:
        result = response("no_data", source_keys=corpus_keys, reason="No wiki section covers most of the query's words.")
    elif not clean:
        result = response("refused", code="suspected_injection", withheld=withheld,
                          reason="The matching wiki sections contain instruction-like text and were withheld for review.")
    else:
        hits = [
            {"key": s["key"], "heading": s["heading"], "coverage": round(c, 2), "text": s["text"][:SNIPPET_CHARS]}
            for c, s in clean[:TOP_K]
        ]
        result = response("answered", source_keys=[h["key"] for h in hits], data={"sections": hits}, withheld=withheld)
    log_call("search_wiki", started, result, query=query, withheld=withheld)
    return result


def _kpis(sections: list[dict]) -> list[dict]:
    """KPI entries from kpis.md: id, name, and the gold column on the Source line."""
    kpis, claimed = [], set()
    for s in sections:
        m = re.match(r"^(K\d+)\. (.+)$", s["heading"]) if s["file"] == "kpis.md" else None
        if not m:
            continue
        src = re.search(r"\*\*Source:\*\* `([^`]+)`", s["text"])
        column = src.group(1).rsplit(".", 1)[-1] if src else None
        # A column cited by several KPIs (rent_burdened_share: K4, K8) belongs to the first.
        if column in claimed:
            column = None
        claimed.add(column)
        kpis.append({"id": m.group(1), "name": m.group(2), "column": column, "section": s})
    return kpis


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-]+", " ", text.lower()).strip()


def get_definition(term: str, sections: list[dict] | None = None) -> dict:
    started = time.perf_counter()
    sections = sections if sections is not None else load_sections()
    if len(term) > MAX_QUERY_CHARS:
        result = response("refused", code="too_large", reason=f"Input is over {MAX_QUERY_CHARS} characters.")
        log_call("get_definition", started, result, chars=len(term))
        return result
    kpis = _kpis(sections)
    t = _norm(term)

    def answer(k, match_kind):
        s = k["section"]
        if suspicious(s["heading"] + "\n" + s["text"]):
            return response("refused", code="suspected_injection", withheld=[s["key"]],
                            reason="This KPI entry contains instruction-like text and was withheld for review.")
        data = {"id": k["id"], "name": k["name"], "column": k["column"], "match": match_kind, "text": s["text"]}
        return response("answered", source_keys=[s["key"]], data=data)

    # 1. Exact: KPI id, name or gold column.
    exact = [k for k in kpis if t in {k["id"].lower(), _norm(k["name"]), _norm(k["column"] or "")}]
    if exact:
        result = answer(exact[0], "exact")
    else:
        # 2. Every content word of the term appears in one KPI name.
        # A query word also matches a longer name word it starts ("burden" -> "burdened"), from 4 letters.
        words = set(_words(term))

        def covers(name_words):
            return all(any(n == w or (len(w) >= 4 and n.startswith(w)) for n in name_words) for w in words)

        covering = [k for k in kpis if words and covers(set(_words(k["name"])))]
        if len(covering) == 1:
            result = answer(covering[0], "name_words")
        elif len(covering) > 1:
            options = ", ".join(f"{k['id']} {k['name']}" for k in covering)
            result = response("needs_clarification", reason=f"'{term}' fits several KPIs: {options}. Which one?",
                              candidates=[k["id"] for k in covering])
        else:
            # 3. Typo fallback on whole names and columns.
            choices = {}
            for k in kpis:
                for alias in (k["name"], k["column"]):
                    if alias:
                        choices[_norm(alias)] = k
            best = process.extractOne(t, list(choices), scorer=fuzz.ratio)
            if best and best[1] >= TYPO_FLOOR:
                result = answer(choices[best[0]], "typo")
            else:
                result = response("no_data", source_keys=["wiki/kpis.md"],
                                  reason=f"No KPI definition matches '{term}'. Try search_wiki for other topics.")
    log_call("get_definition", started, result, term=term)
    return result
