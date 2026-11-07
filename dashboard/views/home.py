import streamlit as st

from common import corridors, eval_summary, rate_table

st.title("AML Blind Spots")
st.markdown(
    "IBM's synthetic anti-money-laundering data: **31.9 million transfers** over 28 days, "
    "of which **35,230** are laundering. We asked two questions."
)

s = eval_summary().set_index("name")
lgb, rules, rnd = s.loc["LightGBM"], s.loc["Fixed rules"], s.loc["Random"]

df = corridors()
avg = 100 * df["laundering"].sum() / df["txns"].sum()
scope = rate_table(df, "scope").set_index("scope")
cb, dom = scope.loc["Cross-border"], scope.loc["Domestic"]

c1, c2 = st.columns(2, gap="large")
with c1:
    st.subheader("Q1 · Can we spot laundering accounts?")
    st.markdown(
        "We rank every account from most to least suspicious, using rule clues and "
        "graph clues, and check how many real launderers land near the top."
    )
    k = st.columns(2)
    k[0].metric("Launderers caught in the top 10%", f"{100 * lgb.recall_top_10pct:.0f}%",
                f"rules {100 * rules.recall_top_10pct:.0f}% · random {100 * rnd.recall_top_10pct:.0f}%",
                delta_color="off")
    k[1].metric("Real launderers in the top 100", f"{100 * lgb.precision_at_100:.0f}",
                f"rules {100 * rules.precision_at_100:.0f} · random {100 * rnd.precision_at_100:.0f}",
                delta_color="off")
    st.markdown(f"**Answer:** yes. LightGBM is **{lgb.x_random:.1f}× better than random** "
                f"and about twice as good as fixed rules.")
    st.page_link("views/q1.py", label="Open Q1", icon="➡️")

with c2:
    st.subheader("Q2 · Which money corridors are risky?")
    st.markdown(
        "A corridor is the sending bank's country → the receiving bank's country. "
        "We compare laundering rates and check them against the Basel AML Index."
    )
    k = st.columns(2)
    k[0].metric("Laundering per 10,000 transfers", f"{100 * cb.rate_pct:.1f}",
                f"cross-border · domestic {100 * dom.rate_pct:.1f}", delta_color="off")
    k[1].metric("Share of laundering that crosses a border",
                f"{cb.share_of_laundering_pct:.0f}%",
                f"{cb.txns / df['txns'].sum():.0%} of transfers", delta_color="off")
    st.markdown(f"**Answer:** cross-border transfers are **{cb.rate_pct / dom.rate_pct:.1f}× riskier** "
                "than domestic ones, but country risk ratings barely predict which corridors.")
    st.page_link("views/q2.py", label="Open Q2", icon="➡️")

st.divider()
st.caption(
    f"Q1 results are on the validation days (Sept 11–12): {int(lgb.rows):,} accounts, "
    f"{int(lgb.positives):,} illicit ({100 * lgb.pos_rate:.2f}%). The test days are kept for a "
    f"final run. Q2 covers all 28 days; average laundering rate {avg:.3f}%."
)
