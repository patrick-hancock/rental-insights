# Synthetic property portfolio (MADE-UP DATA)

**Everything in this folder and in `models/synthetic` is synthetic: made up for a demo.** No row describes a real property, unit, lease, tenant, budget or expense. The metro names (for example "Columbus, OH") are labels for context only; no number comes from Zillow, HUD, Census or any real portfolio. Every table name starts with `synthetic_` and the properties table carries `is_synthetic = true`.

## Why it exists
The rest of rental-insights uses real public rent data, which has no budgets. This dataset shows budget-vs-actual analysis in dbt (rent revenue split into rate and occupancy effects, plus operating-expense variance) on a portfolio that looks like an owner-operator's books. Design decision: U-005 in `docs/DECISIONS.md`.

## What it contains
| Table | One row per | Built by |
|---|---|---|
| `synthetic_properties` | property (8) | seed from `generate.py` |
| `synthetic_units` | apartment unit (400) | seed from `generate.py` |
| `synthetic_leases` | lease (about 1,100) | seed from `generate.py` |
| `synthetic_budget_monthly` | property per month (192) | seed from `generate.py` |
| `synthetic_actual_opex` | property, month and expense category (768) | seed from `generate.py` |
| `synthetic_actual_monthly` | property per month (192) | dbt model: rent revenue from leases, opex pivoted, net operating income |
| `synthetic_variance_monthly` | property per month (192) | dbt model: budget vs actual for rent, each opex line and net operating income |

Period: October 2024 to September 2026 (two fiscal years, October to September).

## How the variance reads
- A positive variance is favorable: more revenue, or less expense, than budget.
- Rent variance splits exactly into an **occupancy effect** ((actual units − budget units) × budget rent) and a **rate effect** ((actual rent − budget rent) × actual units). The check `tests/synthetic/assert_synthetic_variance_adds_up.sql` fails if the pieces stop adding up.
- Leases run whole months, so a lease covering the month end earned that month's full rent. There is no proration, bad debt or concession line.

## What the made-up data is built to show
Budgets assume 3 to 4.5% yearly rent growth, while each property's invented market moves between −2% and +4%. So rate effects are mostly unfavorable, and most so at SYN-P01 (market −2%). Three expense events are planted and marked in `synthetic_actual_opex.note`:
- SYN-P02: HVAC replacement, July 2025 (about $38,000 over on repairs).
- SYN-P05: insurance renewal +28% for fiscal 2026 (about $48,000 over on taxes and insurance).
- SYN-P06: open maintenance position, February to May 2025 (payroll under budget).

## Checks
Column tests live in `synthetic/seeds/synthetic/schema.yml` and `models/synthetic/schema.yml`. Cross-row checks are in `tests/synthetic/`: no overlapping leases on a unit, a complete budget, budget and actual opex lined up 1 to 1, occupancy within unit count, and variance pieces that add up.

## Rebuild
```
python synthetic/generate.py          # writes synthetic/seeds/synthetic/*.csv (fixed seed 20261013)
dbt seed --select synthetic
dbt build --select synthetic
dbt test --select synthetic
```
Tables land in the BigQuery dataset `synthetic`. Drop that dataset to remove them.
