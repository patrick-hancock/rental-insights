"""C6.T1: keep wiki/data_dictionary.md in step with the gold tables.

    python scripts/check_dictionary.py           check; exit 0 only if every gold column is listed
                                                 with its type and a written description, and
                                                 nothing listed is missing from gold
    python scripts/check_dictionary.py --write   rewrite the tables from the live schema, keeping
                                                 every description already written (new ones: TODO)

Columns and types come from BigQuery, read as the read-only ri-reader account (D-003).
Descriptions are written by hand in the markdown; this script never invents them.
Grain lines come from models/gold/schema.yml when the markdown has none yet.
"""

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
DOC = REPO / "wiki" / "data_dictionary.md"
PROJECT = "rental-insights-511513"
DATASET = "gold"
TABLES = ["fct_metro_month", "fct_cbsa_affordability", "dim_metro", "dim_date"]
READER = f"ri-reader@{PROJECT}.iam.gserviceaccount.com"
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
TODO = "TODO"

FRONT = """# Data dictionary: gold tables

Every column of the four gold tables in `{project}.{dataset}`. Types come from BigQuery; descriptions are written by hand. `scripts/check_dictionary.py` fails when a gold column is missing here, has the wrong type or has no description. KPI formulas built on these columns are in [kpis.md](kpis.md).
"""


def live_schema() -> dict[str, list[tuple[str, str]]]:
    import google.auth
    from google.auth import impersonated_credentials
    from google.cloud import bigquery

    source, _ = google.auth.default(scopes=SCOPES)
    creds = impersonated_credentials.Credentials(source_credentials=source, target_principal=READER, target_scopes=SCOPES)
    client = bigquery.Client(project=PROJECT, credentials=creds)
    return {t: [(f.name, f.field_type) for f in client.get_table(f"{PROJECT}.{DATASET}.{t}").schema] for t in TABLES}


def parse_doc(text: str) -> dict[str, dict]:
    """{table: {"grain": str, "columns": {name: (type, description)}}} from the markdown."""
    out = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        lines = block.splitlines()
        table = lines[0].strip()
        grain = next((l.split(":", 1)[1].strip() for l in lines if l.startswith("**Grain:**")), "")
        cols = {}
        for l in lines:
            m = re.match(r"^\| `([^`]+)` \| (\w+) \| (.*) \|\s*$", l)
            if m:
                cols[m.group(1)] = (m.group(2), m.group(3).strip())
        out[table] = {"grain": grain.removeprefix("**").strip(), "columns": cols}
    return out


def schema_yml_grains() -> dict[str, str]:
    data = yaml.safe_load((REPO / "models" / "gold" / "schema.yml").read_text(encoding="utf-8"))
    return {m["name"]: m.get("description", "") for m in data.get("models", [])}


def render(schema, doc, updated: str) -> str:
    grains = schema_yml_grains()
    parts = [FRONT.format(updated=updated, project=PROJECT, dataset=DATASET)]
    for t in TABLES:
        known = doc.get(t, {"grain": "", "columns": {}})
        parts.append(f"\n## {t}\n\n**Grain:** {known['grain'] or grains.get(t, TODO)}\n\n"
                     f"**Model:** `models/gold/{t}.sql`\n\n| Column | Type | Description |\n|---|---|---|\n")
        for name, ftype in schema[t]:
            desc = known["columns"].get(name, ("", ""))[1] or TODO
            parts.append(f"| `{name}` | {ftype} | {desc} |\n")
    return "".join(parts)


def check(schema, doc) -> list[str]:
    problems = []
    for t in TABLES:
        listed = doc.get(t, {}).get("columns", {})
        if t not in doc:
            problems.append(f"{t}: table section missing")
            continue
        if not doc[t]["grain"] or doc[t]["grain"] == TODO:
            problems.append(f"{t}: grain missing")
        live = dict(schema[t])
        for name, ftype in schema[t]:
            if name not in listed:
                problems.append(f"{t}.{name}: not listed")
            elif listed[name][0] != ftype:
                problems.append(f"{t}.{name}: type {listed[name][0]} listed, {ftype} in gold")
            elif not listed[name][1] or listed[name][1] == TODO:
                problems.append(f"{t}.{name}: no description")
        for name in listed:
            if name not in live:
                problems.append(f"{t}.{name}: listed but not in gold")
    return problems


def main(argv) -> int:
    schema = live_schema()
    text = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
    doc = parse_doc(text)
    if "--write" in argv:
        from datetime import date

        DOC.write_text(render(schema, doc, date.today().isoformat()), encoding="utf-8")
        doc = parse_doc(DOC.read_text(encoding="utf-8"))
        print(f"wrote {DOC.relative_to(REPO)}")
    problems = check(schema, doc)
    total = sum(len(c) for c in schema.values())
    for p in problems:
        print(f"FAIL {p}")
    documented = sum(
        1 for t in TABLES for name, ftype in schema[t]
        if doc.get(t, {}).get("columns", {}).get(name, ("", ""))[0] == ftype
        and doc[t]["columns"][name][1] not in ("", TODO)
    )
    print(f"{documented} of {total} gold columns documented; {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
