"""IS459 G2T8 AML Blind Spots: one Streamlit app for both research questions.

Run from the repo root:
    pip install -r dashboard/requirements.txt
    streamlit run dashboard/app.py

Pages: Overview (this file's home page), Q1 (spotting laundering accounts),
Q2 (risky money corridors). Data is read from dashboard/data/; see README.md
for where each file comes from.
"""
import streamlit as st

st.set_page_config(page_title="AML Blind Spots", page_icon="🔎", layout="wide")

pages = st.navigation([
    st.Page("views/home.py", title="Overview", default=True),
    st.Page("views/q1.py", title="Q1 · Spotting launderers"),
    st.Page("views/q2.py", title="Q2 · Risky corridors"),
])
st.sidebar.caption("IS459 G2T8 · IBM HI-Medium, 1–28 Sept 2022")
pages.run()
