# Q2 dashboard: corridor risk vs Basel AML Index

1. In Athena (workgroup `is459`) run `SELECT * FROM is459_aml.q2_corridors;`
   and click **Download results**.
2. Save the CSV as `q2_corridors.csv` in this folder (or upload it in the app's sidebar).
3. `pip install -r requirements.txt`
4. `streamlit run app.py`

Tabs: cross-border vs domestic, riskiest corridors (x average), Basel score vs
laundering rate (with correlation and Basel bands), and a country heat map.
The sidebar slider sets the minimum corridor size (default 5,000 transactions).
Reads only the small corridor CSV, so it needs no AWS access and costs nothing.
