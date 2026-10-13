# Pilot (proof of concept)

Local run of the Q1 tracer and Q2 analyses on the full HI/LI Medium files, used to
check the plan before building on AWS. DuckDB stands in for Glue/Athena here.

```
pip install -r requirements.txt
python poc/build_db.py /path/to/data      # ~4 min; writes poc/aml.duckdb (gitignored)
python poc/q2_pilot.py                    # corridors, conversion blind spot, Basel test
python poc/q1_pilot.py                    # tracer vs Patterns.txt
```

`/path/to/data` holds `{HI,LI}-Medium_Trans.csv`, `{HI,LI}-Medium_accounts.csv` and
`{HI,LI}-Medium_Patterns.txt`.

`basel_2025.csv` holds Basel AML Index 2025 public-edition scores for the 32 countries
that appear in bank names (source: https://index.baselgovernance.org/ranking). Russia
is not in that edition and Crypto banks have no country, so both stay unscored.
