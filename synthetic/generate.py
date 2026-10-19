"""SYNTHETIC DATA GENERATOR. Every value this script writes is made up.

Builds a fictional 8-property apartment portfolio (about 400 units, Oct 2024 to Sep 2026)
for the budget-vs-actual demo in models/synthetic. Real metro names are labels only; no
number comes from Zillow, HUD, Census or any real property. See synthetic/README.md.

Run: python synthetic/generate.py   (writes synthetic/seeds/synthetic/synthetic_*.csv)
Same seed, same output: each table draws from its own random stream, so adding a table
never changes the rows of another.
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 20261013  # fixed so the CSVs are reproducible (decision U-005)
# The extra "synthetic" folder puts seeds under fqn rental_insights.synthetic, so `--select synthetic` finds them.
OUT = Path(__file__).resolve().parent / "seeds" / "synthetic"

# Properties: made-up names in real metros (labels only). base_rent is an invented
# 1-bed monthly rent for Oct 2024; actual_growth is the invented yearly market move.
PROPERTIES = [
    # id, name, metro label, city, state, units, base_rent, actual_growth
    ("SYN-P01", "Cedar Row (synthetic)", "Austin-Round Rock-San Marcos, TX", "Austin", "TX", 48, 1450, -0.02),
    ("SYN-P02", "Mesa Vista (synthetic)", "Phoenix-Mesa-Chandler, AZ", "Mesa", "AZ", 64, 1350, 0.01),
    ("SYN-P03", "Laurel Commons (synthetic)", "Charlotte-Concord-Gastonia, NC-SC", "Charlotte", "NC", 40, 1400, 0.03),
    ("SYN-P04", "Olentangy Flats (synthetic)", "Columbus, OH", "Columbus", "OH", 56, 1150, 0.04),
    ("SYN-P05", "Bayshore Court (synthetic)", "Tampa-St. Petersburg-Clearwater, FL", "Tampa", "FL", 72, 1600, 0.02),
    ("SYN-P06", "Front Range Lofts (synthetic)", "Denver-Aurora-Centennial, CO", "Aurora", "CO", 32, 1550, 0.00),
    ("SYN-P07", "Riverbend Place (synthetic)", "Nashville-Davidson--Murfreesboro--Franklin, TN", "Nashville", "TN", 36, 1500, 0.03),
    ("SYN-P08", "Oak Hollow (synthetic)", "Raleigh-Cary, NC", "Raleigh", "NC", 52, 1380, 0.035),
]


def rng(offset):
    return random.Random(SEED + offset)


def write(name, header, rows):
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{name}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"{path.name}: {len(rows)} rows")


def properties():
    r = rng(1)
    rows = []
    for pid, name, metro, city, state, units, _, _ in PROPERTIES:
        rows.append([pid, name, metro, city, state, units, r.randint(1978, 2019), "true"])
    write("synthetic_properties",
          ["property_id", "property_name", "metro_label", "city", "state", "unit_count", "year_built", "is_synthetic"],
          rows)


# Unit mix: bedrooms -> (share, rent factor vs 1-bed, typical square feet). All invented.
UNIT_MIX = {0: (0.10, 0.85, 500), 1: (0.45, 1.00, 720), 2: (0.35, 1.30, 1020), 3: (0.10, 1.55, 1280)}


def build_units():
    """Return unit rows: [unit_id, property_id, unit_number, bedrooms, square_feet, market_rent_oct2024]."""
    r = rng(2)
    beds = list(UNIT_MIX)
    shares = [UNIT_MIX[b][0] for b in beds]
    rows = []
    for pid, _, _, _, _, units, base_rent, _ in PROPERTIES:
        for i in range(units):
            b = r.choices(beds, shares)[0]
            _, factor, sqft = UNIT_MIX[b]
            unit_number = str((i // 12 + 1) * 100 + i % 12 + 1)  # 12 units a floor: 101-112, 201-212, ...
            rent = round(base_rent * factor * r.uniform(0.94, 1.06) / 5) * 5
            rows.append([f"{pid}-U{unit_number}", pid, unit_number, b, round(sqft * r.uniform(0.92, 1.08)), rent])
    return rows


def units():
    write("synthetic_units",
          ["unit_id", "property_id", "unit_number", "bedrooms", "square_feet", "market_rent_oct2024"],
          build_units())


START = date(2024, 10, 1)
MONTHS = 24  # Oct 2024 .. Sep 2026, month index 0..23


def month_start(m):
    """First day of month index m (0 = Oct 2024; negative = before the period)."""
    y, mo = divmod(START.year * 12 + START.month - 1 + m, 12)
    return date(y, mo + 1, 1)


def month_end(m):
    return month_start(m + 1) - timedelta(days=1)


def build_leases():
    """Simulate whole-month leases per unit: start on the 1st, end on a month's last day.

    In-place leases started up to 11 months before Oct 2024. At each lease end the tenant renews
    (rent up 2-5%) or leaves; a move-out leaves the unit empty 0-3 months and re-lets it at the
    unit's market rent, which moves by the property's invented yearly growth.
    """
    r = rng(3)
    growth = {p[0]: p[7] for p in PROPERTIES}
    renew_p = {p[0]: r.uniform(0.45, 0.65) for p in PROPERTIES}
    rows = []

    def market(rent0, g, m):
        return rent0 * (1 + g) ** (m / 12)

    for unit_id, pid, _, _, _, rent0 in build_units():
        g = growth[pid]
        if r.random() < 0.94:  # occupied on 1 Oct 2024 by a lease signed in the prior year
            start = -r.randint(0, 11)
            rent = round(market(rent0, g, start) * r.uniform(0.96, 1.0))
            kind, term = "in_place", 12
        else:
            start = r.randint(0, 2)
            rent = round(market(rent0, g, start) * r.uniform(0.97, 1.02))
            kind, term = "new", 12
        while start < MONTHS:
            end = start + term - 1
            rows.append([unit_id, month_start(start).isoformat(), month_end(end).isoformat(), term, rent, kind])
            term = r.choices([12, 6, 15], [0.8, 0.1, 0.1])[0]
            if r.random() < renew_p[pid]:
                start, kind = end + 1, "renewal"
                rent = round(rent * r.uniform(1.02, 1.05))
            else:
                start, kind = end + 1 + r.choices([0, 1, 2, 3], [0.2, 0.45, 0.25, 0.1])[0], "new"
                rent = round(market(rent0, g, start) * r.uniform(0.97, 1.02))
    return [[f"SYN-LS-{i:05d}"] + row for i, row in enumerate(rows, 1)]


def leases():
    write("synthetic_leases",
          ["lease_id", "unit_id", "start_date", "end_date", "term_months", "monthly_rent", "lease_type"],
          build_leases())


# Opex budget per unit per month for FY2025, all invented. FY2026 adds OPEX_INFLATION.
OPEX_PER_UNIT = {"repairs_maintenance": 85, "utilities": 60, "payroll": 110, "taxes_insurance": 140}
OPEX_INFLATION = 0.035
HOT_STATES = {"TX", "AZ", "FL", "NC", "TN"}  # utilities peak Jun-Sep; the rest peak Dec-Mar


def fiscal_year(m):
    return 2025 if m < 12 else 2026  # FY runs Oct-Sep, named for the year it ends


def build_budget():
    """Return one row per property per month: planned occupancy, average rent and 4 opex lines.

    Budget rent starts from the units' Oct 2024 asking rents (in-place leases run about 2% below
    asking) and assumes 3-4.5% yearly growth, set once per fiscal year as owners usually budget.
    """
    r = rng(4)
    asking = {}
    for _, pid, _, _, _, rent in build_units():
        asking.setdefault(pid, []).append(rent)
    rows = []
    for pid, _, _, _, state, units, _, _ in PROPERTIES:
        plan_growth = r.uniform(0.03, 0.045)
        rent_fy = {2025: sum(asking[pid]) / units * 0.98 * (1 + plan_growth / 2)}
        rent_fy[2026] = rent_fy[2025] * (1 + plan_growth)
        occ_fy = {fy: r.uniform(0.94, 0.96) for fy in (2025, 2026)}
        tax_ins = OPEX_PER_UNIT["taxes_insurance"] * (1.35 if state == "FL" else 1.0)
        for m in range(MONTHS):
            fy = fiscal_year(m)
            infl = 1 + OPEX_INFLATION * (fy - 2025)
            cal_month = month_start(m).month
            peak = cal_month in (6, 7, 8, 9) if state in HOT_STATES else cal_month in (12, 1, 2, 3)
            opex = {
                "repairs_maintenance": OPEX_PER_UNIT["repairs_maintenance"],
                "utilities": OPEX_PER_UNIT["utilities"] * (1.25 if peak else 0.92),
                "payroll": OPEX_PER_UNIT["payroll"],
                "taxes_insurance": tax_ins,
            }
            rows.append([pid, month_end(m).isoformat(), fy, round(units * occ_fy[fy]), round(rent_fy[fy], 2)]
                        + [round(v * units * infl) for v in opex.values()])
    return rows


def budget():
    write("synthetic_budget_monthly",
          ["property_id", "month_end", "fiscal_year", "budget_occupied_units", "budget_avg_rent"]
          + [f"budget_{k}" for k in OPEX_PER_UNIT],
          build_budget())


# Month-to-month spread of actual opex around budget, per category (low, high multipliers).
OPEX_NOISE = {"repairs_maintenance": (0.85, 1.20), "utilities": (0.90, 1.12),
              "payroll": (0.97, 1.04), "taxes_insurance": (0.99, 1.02)}
# Planted events, so the variance models have something to find. All invented.
# (property, category, month indexes, multiplier, extra dollars, note)
OPEX_EVENTS = [
    ("SYN-P02", "repairs_maintenance", [9], 1.0, 38000, "HVAC replacement (synthetic event)"),
    ("SYN-P05", "taxes_insurance", range(12, 24), 1.28, 0, "insurance renewal +28% (synthetic event)"),
    ("SYN-P06", "payroll", range(4, 8), 0.75, 0, "open maintenance position (synthetic event)"),
]


def build_actual_opex():
    """Return ledger-style rows: one per property, month and opex category, with an optional note."""
    r = rng(5)
    cats = list(OPEX_PER_UNIT)
    rows = []
    for m_idx, b in enumerate(build_budget()):
        pid, me = b[0], b[1]
        m = m_idx % MONTHS
        for cat, planned in zip(cats, b[5:]):
            amount, note = planned * r.uniform(*OPEX_NOISE[cat]), ""
            for e_pid, e_cat, e_months, mult, extra, e_note in OPEX_EVENTS:
                if (e_pid, e_cat) == (pid, cat) and m in e_months:
                    amount, note = amount * mult + extra, e_note
            rows.append([pid, me, cat, round(amount, 2), note])
    return rows


def actual_opex():
    write("synthetic_actual_opex", ["property_id", "month_end", "category", "amount", "note"], build_actual_opex())


if __name__ == "__main__":
    properties()
    units()
    leases()
    budget()
    actual_opex()
