"""Shared data loading, colours and small helpers for the dashboard pages."""
from pathlib import Path

import pandas as pd
import streamlit as st

DATA = Path(__file__).parent / "data"

# One colour per model, used on every Q1 chart.
MODEL_NAMES = {
    "m1_lgbm_no_taint": "LightGBM",
    "m1_lgbm_with_taint": "LightGBM + taint",
    "m2_rules": "Fixed rules",
    "m3_random": "Random",
}
MODEL_COLORS = {
    "LightGBM": "#2F5BB7",
    "LightGBM + taint": "#8FA9E0",
    "Fixed rules": "#E08A2F",
    "Random": "#9AA0A6",
}
BLUE, RED, TEAL = "#2F5BB7", "#D1495B", "#3C9D9B"


@st.cache_data
def eval_summary() -> pd.DataFrame:
    df = pd.read_csv(DATA / "eval_summary.csv")
    df["name"] = df["model"].map(MODEL_NAMES)
    return df


@st.cache_data
def eval_deciles() -> pd.DataFrame:
    df = pd.read_csv(DATA / "eval_deciles.csv")
    df["name"] = df["model"].map(MODEL_NAMES)
    return df


@st.cache_data
def top_accounts() -> pd.DataFrame:
    return pd.read_csv(DATA / "q1_top_accounts.csv", dtype={"acct": str})


@st.cache_data
def shapes() -> pd.DataFrame:
    df = pd.read_csv(DATA / "q1_shapes_val.csv")
    df["illicit_pct"] = 100 * df["illicit"] / df["accounts"]
    return df


@st.cache_data
def corridors() -> pd.DataFrame:
    df = pd.read_csv(DATA / "q2_corridors.csv")
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


def rate_table(df: pd.DataFrame, by: str) -> pd.DataFrame:
    g = df.groupby(by, as_index=False)[["txns", "laundering"]].sum()
    g["rate_pct"] = 100 * g["laundering"] / g["txns"]
    g["share_of_laundering_pct"] = 100 * g["laundering"] / df["laundering"].sum()
    return g


def footer(text: str) -> None:
    st.divider()
    st.caption(text)
