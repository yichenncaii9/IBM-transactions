import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from common import MODEL_COLORS, RED, TEAL, eval_deciles, eval_summary, footer, shapes, top_accounts

st.title("Q1 · Can we spot laundering accounts?")
st.caption(
    "Each model ranks the same validation accounts (Sept 11–12) from most to least "
    "suspicious. We check how many real launderers end up near the top of each list."
)

s = eval_summary()
order = ["LightGBM", "LightGBM + taint", "Fixed rules", "Random"]
s["name"] = pd.Categorical(s["name"], order, ordered=True)
s = s.sort_values("name")
lgb = s.set_index("name").loc["LightGBM"]

k = st.columns(4)
k[0].metric("Validation accounts", f"{int(lgb.rows):,}")
k[1].metric("Really illicit", f"{int(lgb.positives):,}", f"{100 * lgb.pos_rate:.2f}% of accounts",
            delta_color="off")
k[2].metric("LightGBM: caught in top 10%", f"{100 * lgb.recall_top_10pct:.1f}%")
k[3].metric("LightGBM vs random", f"{lgb.x_random:.1f}×", "average precision", delta_color="off")

tab1, tab2, tab3, tab4 = st.tabs(
    ["Model comparison", "Working down the list", "Top accounts", "What the graph clues show"]
)

# ---------------------------------------------------------------- tab 1
with tab1:
    metric = st.radio(
        "Measure",
        ["Launderers caught in the top 10%", "Real launderers in the top 100",
         "Average precision (× random)"],
        horizontal=True,
    )
    if metric.startswith("Launderers caught"):
        y, fmt, label = 100 * s["recall_top_10pct"], "{:.1f}%", "% of all launderers caught"
    elif metric.startswith("Real launderers"):
        y, fmt, label = 100 * s["precision_at_100"], "{:.0f}", "Real launderers in the top 100"
    else:
        y, fmt, label = s["x_random"], "{:.1f}×", "Average precision ÷ random"
    fig = px.bar(s, x="name", y=y, color="name", color_discrete_map=MODEL_COLORS,
                 text=[fmt.format(v) for v in y], labels={"name": "", "y": label})
    fig.update_layout(height=420, showlegend=False, yaxis_title=label)
    c1, c2 = st.columns([3, 2])
    c1.plotly_chart(fig, use_container_width=True)
    table = s[["name", "ap", "x_random", "recall_top_10pct", "precision_at_100", "precision_at_1000"]]
    c2.dataframe(
        table.rename(columns={"name": "Model", "ap": "Avg precision", "x_random": "× random",
                              "recall_top_10pct": "Caught in top 10%",
                              "precision_at_100": "Precision @100",
                              "precision_at_1000": "Precision @1000"})
        .style.format({"Avg precision": "{:.4f}", "× random": "{:.1f}", "Caught in top 10%": "{:.1%}",
                       "Precision @100": "{:.0%}", "Precision @1000": "{:.1%}"}),
        hide_index=True, use_container_width=True)
    c2.markdown(
        "**Takeaway:** LightGBM beats both baselines on every measure. Adding taint "
        "(closeness to suspicious money) did not help."
    )
    c2.caption("Accuracy is not used: calling every account innocent would already be "
               f"{100 * (1 - lgb.pos_rate):.2f}% accurate and catch nobody.")

# ---------------------------------------------------------------- tab 2
with tab2:
    d = eval_deciles()
    d = d[d["name"].isin(order)]
    first = d.assign(decile=0, cum_recall=0.0).drop_duplicates("name")
    d2 = pd.concat([first, d]).sort_values(["name", "decile"])
    d2["checked"] = d2["decile"] * 10
    c1, c2 = st.columns(2)
    fig = px.line(d2, x="checked", y=d2["cum_recall"] * 100, color="name", markers=True,
                  color_discrete_map=MODEL_COLORS, category_orders={"name": order},
                  labels={"checked": "% of accounts checked, most suspicious first",
                          "y": "% of launderers caught", "name": ""})
    fig.update_layout(height=420, yaxis_title="% of launderers caught", legend_title_text="")
    c1.markdown("**Launderers caught as investigators work down the list**")
    c1.plotly_chart(fig, use_container_width=True)

    fig2 = px.bar(d, x="decile", y="lift", color="name", barmode="group",
                  color_discrete_map=MODEL_COLORS, category_orders={"name": order},
                  labels={"decile": "Tenth of the list (1 = most suspicious)",
                          "lift": "Times the average rate", "name": ""})
    fig2.add_hline(y=1, line_dash="dash", annotation_text="random")
    fig2.update_layout(height=420, legend_title_text="")
    fig2.update_xaxes(dtick=1)
    c2.markdown("**How concentrated launderers are in each tenth**")
    c2.plotly_chart(fig2, use_container_width=True)
    top1 = d[(d["name"] == "LightGBM") & (d["decile"] == 1)].iloc[0]
    st.markdown(
        f"**Takeaway:** LightGBM's first tenth has **{top1.lift:.1f}×** the average share of "
        f"launderers. A straight line would mean the model learned nothing."
    )

# ---------------------------------------------------------------- tab 3
with tab3:
    t = top_accounts()
    n = st.select_slider("Show LightGBM's top", [25, 50, 100, 250, 500], value=100)
    view = t.head(n)
    hits = int(view["label"].sum())
    c1, c2 = st.columns([1, 3])
    c1.metric(f"Real launderers in the top {n}", f"{hits}", f"{hits / n:.0%} precision",
              delta_color="off")
    c1.metric("Of these, rules ranked outside their top 1,000",
              f"{int(((view['label'] == 1) & (view['rules_rank'] > 1000)).sum())}")
    c1.caption("Rules miss many accounts LightGBM puts at the top.")
    strip = view.assign(colour=view["label"].map({1: "Illicit", 0: "Not illicit"}))
    fig = go.Figure(go.Bar(
        x=strip["rank"], y=strip["score"],
        marker_color=[RED if v == 1 else "#C9CED6" for v in strip["label"]],
        hovertext=strip["acct"], hovertemplate="Rank %{x}<br>Score %{y:.3f}<br>%{hovertext}<extra></extra>",
    ))
    fig.update_layout(height=300, xaxis_title="Rank (1 = most suspicious)", yaxis_title="LightGBM score",
                      bargap=0.05, margin=dict(t=10))
    c2.plotly_chart(fig, use_container_width=True)
    c2.caption("Red = really illicit in the validation period.")
    st.dataframe(
        view.rename(columns={"rank": "Rank", "acct": "Account (bank|account)", "score": "Score",
                             "label": "Illicit", "rules_rank": "Rank under fixed rules"})
        .style.format({"Score": "{:.3f}", "Rank under fixed rules": "{:,.0f}"}),
        hide_index=True, use_container_width=True, height=360)

# ---------------------------------------------------------------- tab 4
with tab4:
    sh = shapes()
    base = 100 * sh["illicit"].sum() / sh["accounts"].sum()
    shape_order = ["In a 3-account loop", "Two-way partner", "Receives from 10+ accounts",
                   "Sends to 10+ accounts", "None of these"]
    sh["shape"] = pd.Categorical(sh["shape"], shape_order, ordered=True)
    sh = sh.sort_values("shape")
    fig = px.bar(sh, x="illicit_pct", y="shape", orientation="h",
                 text=sh["illicit_pct"].map("{:.1f}%".format),
                 hover_data={"accounts": ":,", "illicit": ":,"},
                 labels={"illicit_pct": "% of these accounts that are illicit", "shape": ""})
    fig.add_vline(x=base, line_dash="dash", annotation_text=f"all accounts {base:.2f}%")
    fig.update_traces(marker_color=TEAL)
    fig.update_layout(height=360, yaxis={"autorange": "reversed"})
    c1, c2 = st.columns([3, 2])
    c1.plotly_chart(fig, use_container_width=True)
    c2.dataframe(
        sh[["shape", "accounts", "illicit", "illicit_pct"]]
        .rename(columns={"shape": "Graph shape", "accounts": "Accounts", "illicit": "Illicit",
                         "illicit_pct": "Illicit %"})
        .style.format({"Accounts": "{:,}", "Illicit": "{:,}", "Illicit %": "{:.1f}"}),
        hide_index=True, use_container_width=True)
    c2.markdown(
        "**Takeaway:** accounts in a 3-account loop are illicit far more often than average. "
        "These shapes are the graph clues the model learns from. Each account is counted "
        "once, in its first matching shape from the top."
    )

footer("Sources: q1d-eval/run_models.py (eval_summary, eval_deciles, top accounts); "
       "Athena is459_aml.graph_motifs joined to gbm_account_labels (graph shapes), validation period.")
