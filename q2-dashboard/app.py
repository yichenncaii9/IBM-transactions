"""
IS459 G2T8 - Q2 dashboard: which money corridors are risky,
and does the Basel AML Index predict that risk?

Data: one CSV exported from Athena:
    SELECT * FROM is459_aml.q2_corridors;
Save it next to this file as q2_corridors.csv (or upload it in the sidebar).

Run:
    pip install -r requirements.txt
    streamlit run app.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Q2 Corridor Risk", layout="wide")

DATA_FILE = Path(__file__).parent / "q2_corridors.csv"
BAND_CUTS = (4.0, 5.0)  # Basel score: < 4 low, 4-5 medium, >= 5 high


# ---------------------------------------------------------------- data
@st.cache_data
def load(src) -> pd.DataFrame:
    df = pd.read_csv(src)
    df.columns = [c.strip().lower() for c in df.columns]
    for c in ["txns", "laundering", "flagged", "caught"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    for c in ["from_basel_score", "to_basel_score"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["from_country"] = df["from_country"].fillna("No country (crypto)")
    df["to_country"] = df["to_country"].fillna("No country (crypto)")

    def scope(r):
        names = f"{r.from_country} {r.to_country}".lower()
        if "crypto" in names or "bitcoin" in names:
            return "Crypto"
        return "Domestic" if r.from_country == r.to_country else "Cross-border"

    df["scope"] = df.apply(scope, axis=1)
    df["corridor"] = df["from_country"] + " → " + df["to_country"]
    df["rate"] = df["laundering"] / df["txns"].where(df["txns"] > 0)
    return df


def band(score):
    if pd.isna(score):
        return "No score"
    if score < BAND_CUTS[0]:
        return "Low (< 4)"
    return "Medium (4–5)" if score < BAND_CUTS[1] else "High (≥ 5)"


def rate_table(df, by):
    g = df.groupby(by, as_index=False)[["txns", "laundering"]].sum()
    g["rate_pct"] = 100 * g["laundering"] / g["txns"]
    g["share_of_laundering_pct"] = 100 * g["laundering"] / df["laundering"].sum()
    return g


st.sidebar.header("Data")
upload = st.sidebar.file_uploader("q2_corridors.csv (Athena export)", type="csv")
if upload is not None:
    df = load(upload)
elif DATA_FILE.exists():
    df = load(DATA_FILE)
else:
    st.title("Q2: Corridor risk")
    st.info(
        "No data yet. In Athena run `SELECT * FROM is459_aml.q2_corridors;`, "
        "click **Download results**, then upload the CSV in the sidebar "
        "(or save it as `q2_corridors.csv` next to app.py)."
    )
    st.stop()

min_txns = st.sidebar.slider(
    "Ignore corridors with fewer transactions than", 0, 50_000, 5_000, step=1_000,
    help="Small corridors have noisy rates. 5,000 is the cut-off used in the report.",
)
st.sidebar.caption(
    "Countries come from bank names. Banks named after a city were assumed "
    "to be US (35% of banks), so 'United States' really means that bank group."
)

total_txns = df["txns"].sum()
total_laundering = df["laundering"].sum()
avg_rate = total_laundering / total_txns
big = df[df["txns"] >= min_txns].copy()

# ---------------------------------------------------------------- header
st.title("Q2: Which money corridors are risky?")
st.caption(
    "IBM HI-Medium, 1–28 Sept 2022. A corridor is the sending bank's country → "
    "the receiving bank's country. Labels are used here because Q2 describes "
    "risk; it does not detect it."
)

scope_t = rate_table(df, "scope").set_index("scope")
k = st.columns(4)
k[0].metric("Transactions", f"{total_txns:,.0f}")
k[1].metric("Average laundering rate", f"{100 * avg_rate:.3f}%")
if "Cross-border" in scope_t.index:
    cb = scope_t.loc["Cross-border"]
    k[2].metric("Cross-border rate", f"{cb.rate_pct:.3f}%",
                f"{cb.rate_pct / (100 * avg_rate):.1f}× average", delta_color="off")
    k[3].metric("Share of laundering that crosses a border",
                f"{cb.share_of_laundering_pct:.0f}%")

tab1, tab2, tab3, tab4 = st.tabs(
    ["Cross-border vs domestic", "Riskiest corridors", "Does Basel predict risk?", "Country heat map"]
)

# ---------------------------------------------------------------- tab 1
with tab1:
    t = rate_table(df, "scope").sort_values("rate_pct", ascending=False)
    fig = px.bar(t, x="scope", y="rate_pct", text=t["rate_pct"].map("{:.3f}%".format),
                 labels={"scope": "", "rate_pct": "Laundering rate (%)"})
    fig.add_hline(y=100 * avg_rate, line_dash="dash",
                  annotation_text=f"average {100 * avg_rate:.3f}%")
    fig.update_traces(marker_color="#4C78A8")
    fig.update_layout(height=420)
    c1, c2 = st.columns([3, 2])
    c1.plotly_chart(fig, use_container_width=True)
    c2.dataframe(
        t.rename(columns={"scope": "Scope", "txns": "Transactions", "laundering": "Laundering",
                          "rate_pct": "Rate %", "share_of_laundering_pct": "Share of laundering %"})
         .style.format({"Transactions": "{:,.0f}", "Laundering": "{:,.0f}",
                        "Rate %": "{:.3f}", "Share of laundering %": "{:.1f}"}),
        hide_index=True, use_container_width=True)
    c2.markdown("**Takeaway:** money crossing a border is laundered far more often "
                "than money that stays in one country.")

# ---------------------------------------------------------------- tab 2
with tab2:
    n = st.slider("How many corridors", 5, 30, 10)
    top = big.sort_values("rate", ascending=False).head(n).copy()
    top["x_avg"] = top["rate"] / avg_rate
    fig = px.bar(top.iloc[::-1], x="x_avg", y="corridor", orientation="h",
                 text=top.iloc[::-1]["x_avg"].map("{:.0f}×".format),
                 hover_data={"txns": ":,", "laundering": ":,", "rate": ":.3%"},
                 labels={"x_avg": "Times the average laundering rate", "corridor": ""})
    fig.add_vline(x=1, line_dash="dash", annotation_text="average")
    fig.update_traces(marker_color="#E45756")
    fig.update_layout(height=max(380, 32 * n))
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"Only corridors with at least {min_txns:,} transactions "
               f"({len(big):,} of {len(df):,} corridors).")
    st.dataframe(
        top[["corridor", "txns", "laundering", "rate", "x_avg",
             "from_basel_score", "to_basel_score"]]
        .rename(columns={"corridor": "Corridor", "txns": "Transactions", "laundering": "Laundering",
                         "rate": "Rate", "x_avg": "× average",
                         "from_basel_score": "Basel (from)", "to_basel_score": "Basel (to)"})
        .style.format({"Transactions": "{:,.0f}", "Laundering": "{:,.0f}", "Rate": "{:.3%}",
                       "× average": "{:.1f}", "Basel (from)": "{:.2f}", "Basel (to)": "{:.2f}"}),
        hide_index=True, use_container_width=True)

# ---------------------------------------------------------------- tab 3
with tab3:
    side = st.radio("Basel score of the", ["receiving country", "sending country"], horizontal=True)
    col = "to_basel_score" if side == "receiving country" else "from_basel_score"
    s = big.dropna(subset=[col, "rate"])
    r = np.corrcoef(s[col], s["rate"])[0, 1] if len(s) > 2 else float("nan")

    c1, c2 = st.columns([3, 2])
    fig = px.scatter(s, x=col, y=s["rate"] * 100, size="txns", hover_name="corridor",
                     labels={col: f"Basel AML score ({side}), higher = riskier",
                             "y": "Laundering rate (%)"},
                     opacity=0.6, size_max=40)
    fig.update_traces(marker_color="#4C78A8")
    fig.update_layout(height=460, yaxis_title="Laundering rate (%)")
    c1.plotly_chart(fig, use_container_width=True)

    c2.metric("Correlation (r)", f"{r:.2f}", help="1 = perfect match, 0 = no relationship")
    c2.caption(f"{len(s):,} corridors with at least {min_txns:,} transactions")
    bands = big.assign(band=big[col].map(band))
    bt = rate_table(bands, "band")
    order = ["Low (< 4)", "Medium (4–5)", "High (≥ 5)", "No score"]
    bt["band"] = pd.Categorical(bt["band"], order, ordered=True)
    bt = bt.sort_values("band")
    fig2 = px.bar(bt, x="band", y="rate_pct", text=bt["rate_pct"].map("{:.3f}%".format),
                  labels={"band": "Basel band", "rate_pct": "Laundering rate (%)"})
    fig2.update_traces(marker_color="#72B7B2")
    fig2.update_layout(height=300)
    c2.plotly_chart(fig2, use_container_width=True)
    c2.markdown("**Takeaway:** if Basel predicted risk, the dots would rise to the right "
                "and the bars would climb. An r near 0 means country ratings alone "
                "would miss the risky corridors.")

# ---------------------------------------------------------------- tab 4
with tab4:
    top_n = st.slider("Countries shown (by transaction volume)", 5, 30, 15)
    vol = (pd.concat([df.groupby("from_country")["txns"].sum(),
                      df.groupby("to_country")["txns"].sum()])
             .groupby(level=0).sum().sort_values(ascending=False))
    keep = vol.head(top_n).index
    h = big[big["from_country"].isin(keep) & big["to_country"].isin(keep)]
    grid = (h.pivot_table(index="from_country", columns="to_country", values="rate", aggfunc="sum")
              .reindex(index=keep, columns=keep) * 100)
    fig = px.imshow(grid, color_continuous_scale="Reds", aspect="auto",
                    labels={"x": "To country", "y": "From country", "color": "Rate (%)"})
    fig.update_layout(height=max(450, 32 * top_n))
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"Blank cells: no corridor, or fewer than {min_txns:,} transactions.")
