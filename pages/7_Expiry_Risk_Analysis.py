"""Expiry Risk Analysis — DTE at entry vs P&L, near-expiry hold flags."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.core.config import settings
from app.core.database import get_session, init_db
from app.core.repository import fetch_all_journeys, fetch_behavior_flags
from app.ui.components import (
    COLOR_LOSS, COLOR_WIN, COLOR_WARNING,
    expiry_risk_chart, format_pnl, metric_card, pnl_color,
)
from app.ui.state import init_state

st.set_page_config(page_title="Expiry Risk | TradeInSight", layout="wide", page_icon="⏰")
init_db()
init_state()
st.markdown(
    "<style>.stApp{background:#0f172a} h1,h2,h3{color:#e2e8f0!important}</style>",
    unsafe_allow_html=True,
)

st.title("⏰ Expiry Risk Analysis")
st.caption(f"How DTE at entry and exit relates to your P&L (near-expiry threshold: {settings.near_expiry_dte} DTE)")
st.divider()

with get_session() as session:
    journeys = fetch_all_journeys(session)
    flag_dicts = fetch_behavior_flags(session)

if not journeys:
    st.info("No data yet.")
    st.stop()

near_exp_ids = {f["journey_id"] for f in flag_dicts if f["behavior_type"] == "near_expiry_hold"}
df = pd.DataFrame(journeys)
df_closed = df[df["status"].isin(["closed", "expired"])].copy()
df_options = df_closed[df_closed["opt_type"].notna()].copy()

near_exp_df = df_options[df_options["journey_id"].isin(near_exp_ids)]
near_exp_pnl = near_exp_df["realized_pnl"].sum()
expired_worthless = df_options[df_options["status"] == "expired"]

c1, c2, c3, c4 = st.columns(4)
with c1:
    metric_card("Near-Expiry Holds", str(len(near_exp_df)), "flagged journeys")
with c2:
    metric_card("Loss from Near-Expiry", format_pnl(near_exp_pnl), color=COLOR_LOSS)
with c3:
    metric_card("Expired Worthless", str(len(expired_worthless)), "went to $0")
with c4:
    exp_loss = expired_worthless["realized_pnl"].sum()
    metric_card("Expiry Loss Total", format_pnl(exp_loss), color=COLOR_LOSS)

st.divider()

# --------------------------------------------------------------------------- #
# DTE scatter chart
# --------------------------------------------------------------------------- #
st.markdown("### P&L vs DTE at Entry")
st.caption("Each dot = one closed journey. Lower-left = bought too close to expiry and lost.")
st.plotly_chart(expiry_risk_chart(df_options), use_container_width=True)

# --------------------------------------------------------------------------- #
# DTE bucket analysis
# --------------------------------------------------------------------------- #
st.markdown("### P&L by DTE Bucket")

def dte_bucket(dte):
    if pd.isna(dte): return "Unknown"
    if dte <= 7: return "0-7 DTE (danger zone)"
    if dte <= 14: return "8-14 DTE"
    if dte <= 21: return "15-21 DTE"
    if dte <= 45: return "22-45 DTE"
    return "45+ DTE"

df_options["dte_bucket"] = df_options["dte_at_first_entry"].apply(dte_bucket)
bucket_agg = (
    df_options.groupby("dte_bucket")
    .agg(
        trades=("realized_pnl", "count"),
        total_pnl=("realized_pnl", "sum"),
        avg_pnl=("realized_pnl", "mean"),
        win_rate=("realized_pnl", lambda x: (x > 0).mean() * 100),
    )
    .reset_index()
)
bucket_order = ["0-7 DTE (danger zone)", "8-14 DTE", "15-21 DTE", "22-45 DTE", "45+ DTE", "Unknown"]
bucket_agg["sort_key"] = bucket_agg["dte_bucket"].apply(
    lambda b: bucket_order.index(b) if b in bucket_order else 99
)
bucket_agg = bucket_agg.sort_values("sort_key")

colors = [COLOR_LOSS if v < 0 else COLOR_WIN for v in bucket_agg["total_pnl"]]
fig_bucket = go.Figure(go.Bar(
    x=bucket_agg["dte_bucket"], y=bucket_agg["total_pnl"],
    marker_color=colors,
    text=[f"{format_pnl(v)}\n{r:.0f}% WR" for v, r in zip(bucket_agg["total_pnl"], bucket_agg["win_rate"])],
    textposition="outside",
))
fig_bucket.update_layout(
    title="Total P&L by DTE Bucket at Entry",
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#e2e8f0"), height=340,
    xaxis=dict(gridcolor="#334155"), yaxis=dict(gridcolor="#334155", tickprefix="$"),
    margin=dict(l=10, r=10, t=45, b=10),
)
st.plotly_chart(fig_bucket, use_container_width=True)

# Bucket table
display = bucket_agg[["dte_bucket", "trades", "total_pnl", "avg_pnl", "win_rate"]].copy()
for col in ["total_pnl", "avg_pnl"]:
    display[col] = display[col].apply(lambda v: f"${v:,.2f}")
display["win_rate"] = display["win_rate"].apply(lambda v: f"{v:.0f}%")
st.dataframe(display.rename(columns={
    "dte_bucket": "DTE Bucket", "trades": "Trades",
    "total_pnl": "Total P&L", "avg_pnl": "Avg P&L", "win_rate": "Win Rate"
}), use_container_width=True, hide_index=True)

st.divider()
st.info(
    f"📌 Rule: Close or roll any long option before it reaches **{settings.near_expiry_dte} DTE**. "
    f"Theta decay accelerates sharply in the final week — the option loses value fastest precisely "
    f"when you need recovery the most."
)
