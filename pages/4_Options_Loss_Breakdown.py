"""Options Loss Breakdown — loss by symbol, strategy, expiry month, and behavior."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.core.database import get_session, init_db
from app.core.repository import fetch_all_journeys, fetch_behavior_flags
from app.ui.components import (
    COLOR_LOSS, COLOR_WIN, COLOR_NEUTRAL, BEHAVIOR_COLORS,
    format_pnl, loss_by_behavior_chart, metric_card, pnl_color,
)
from app.ui.state import init_state

st.set_page_config(page_title="Options Loss Breakdown | TradeInSight", layout="wide", page_icon="💸")
init_db()
init_state()
st.markdown(
    "<style>.stApp{background:#0f172a} h1,h2,h3{color:#e2e8f0!important}</style>",
    unsafe_allow_html=True,
)

st.title("💸 Options Loss Breakdown")
st.caption("Where did the money go — broken down every possible way")
st.divider()

with get_session() as session:
    journeys = fetch_all_journeys(session)
    flag_dicts = fetch_behavior_flags(session)

if not journeys:
    st.info("No data yet — import statements first.")
    st.stop()

df = pd.DataFrame(journeys)
df["exit_date"] = pd.to_datetime(df["exit_date"], errors="coerce")
df["entry_date"] = pd.to_datetime(df["entry_date"], errors="coerce")
df_closed = df[df["status"].isin(["closed", "expired"])].copy()
df_options = df_closed[df_closed["opt_type"].notna()].copy()

if df_options.empty:
    st.warning("No closed options trades found.")
    st.stop()

total_loss = df_options[df_options["realized_pnl"] < 0]["realized_pnl"].sum()
total_gain = df_options[df_options["realized_pnl"] > 0]["realized_pnl"].sum()
total_expired_loss = df_options[
    (df_options["status"] == "expired") & (df_options["realized_pnl"] < 0)
]["realized_pnl"].sum()

c1, c2, c3, c4 = st.columns(4)
with c1:
    metric_card("Total Options Loss", format_pnl(total_loss), color=COLOR_LOSS)
with c2:
    metric_card("Total Options Gain", format_pnl(total_gain), color=COLOR_WIN)
with c3:
    metric_card("Net Options P&L", format_pnl(total_loss + total_gain),
                color=pnl_color(total_loss + total_gain))
with c4:
    metric_card("Loss from Expiry", format_pnl(total_expired_loss), "went to $0", color=COLOR_LOSS)

st.divider()

# --------------------------------------------------------------------------- #
# Loss by symbol
# --------------------------------------------------------------------------- #
tab1, tab2, tab3, tab4 = st.tabs(["By Symbol", "By Strategy", "By Expiry Month", "By Behavior"])

with tab1:
    sym_pnl = df_options.groupby("underlying")["realized_pnl"].sum().reset_index()
    sym_pnl = sym_pnl.sort_values("realized_pnl")
    colors = [COLOR_WIN if v >= 0 else COLOR_LOSS for v in sym_pnl["realized_pnl"]]
    fig = go.Figure(go.Bar(
        x=sym_pnl["realized_pnl"], y=sym_pnl["underlying"],
        orientation="h", marker_color=colors,
        text=[format_pnl(v) for v in sym_pnl["realized_pnl"]],
        textposition="outside",
    ))
    fig.update_layout(
        title="P&L by Underlying Symbol", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#e2e8f0"),
        height=max(300, len(sym_pnl) * 35), margin=dict(l=10, r=80, t=45, b=10),
        xaxis=dict(gridcolor="#334155", tickprefix="$"),
        yaxis=dict(gridcolor="#334155"),
    )
    st.plotly_chart(fig, use_container_width=True)

    sym_detail = (
        df_options.groupby("underlying")
        .agg(
            trades=("realized_pnl", "count"),
            total_pnl=("realized_pnl", "sum"),
            avg_pnl=("realized_pnl", "mean"),
            worst=("realized_pnl", "min"),
            best=("realized_pnl", "max"),
        )
        .sort_values("total_pnl")
        .reset_index()
    )
    for col in ["total_pnl", "avg_pnl", "worst", "best"]:
        sym_detail[col] = sym_detail[col].apply(lambda v: f"${v:,.2f}")
    st.dataframe(sym_detail, use_container_width=True, hide_index=True)

with tab2:
    df_options["strategy"] = df_options["opt_type"].apply(
        lambda t: f"Long {t.title()}" if t else "Other"
    )
    strat_pnl = df_options.groupby("strategy")["realized_pnl"].sum().reset_index()
    colors = [COLOR_WIN if v >= 0 else COLOR_LOSS for v in strat_pnl["realized_pnl"]]
    fig2 = go.Figure(go.Bar(
        x=strat_pnl["strategy"], y=strat_pnl["realized_pnl"],
        marker_color=colors,
        text=[format_pnl(v) for v in strat_pnl["realized_pnl"]],
        textposition="outside",
    ))
    fig2.update_layout(
        title="P&L by Strategy", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#e2e8f0"),
        height=320, margin=dict(l=10, r=10, t=45, b=10),
        xaxis=dict(gridcolor="#334155"),
        yaxis=dict(gridcolor="#334155", tickprefix="$"),
    )
    st.plotly_chart(fig2, use_container_width=True)

with tab3:
    df_options["expiry_month"] = pd.to_datetime(df_options["opt_expiry"], errors="coerce").dt.to_period("M").astype(str)
    expiry_pnl = df_options.groupby("expiry_month")["realized_pnl"].sum().reset_index().sort_values("expiry_month")
    colors = [COLOR_WIN if v >= 0 else COLOR_LOSS for v in expiry_pnl["realized_pnl"]]
    fig3 = go.Figure(go.Bar(
        x=expiry_pnl["expiry_month"], y=expiry_pnl["realized_pnl"],
        marker_color=colors,
        text=[format_pnl(v) for v in expiry_pnl["realized_pnl"]],
        textposition="outside",
    ))
    fig3.update_layout(
        title="P&L by Expiry Month", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#e2e8f0"),
        height=320, margin=dict(l=10, r=10, t=45, b=10),
        xaxis=dict(gridcolor="#334155"),
        yaxis=dict(gridcolor="#334155", tickprefix="$"),
    )
    st.plotly_chart(fig3, use_container_width=True)

with tab4:
    if flag_dicts:
        from app.domain.models.behavior_flag import BEHAVIOR_LABELS, BehaviorType
        beh_df = pd.DataFrame(flag_dicts)
        beh_agg = (
            beh_df.groupby("behavior_type")
            .agg(
                total_impact=("estimated_loss_impact", "sum"),
                count=("journey_id", "count"),
            )
            .reset_index()
        )
        beh_agg["behavior_label"] = beh_agg["behavior_type"].apply(
            lambda t: BEHAVIOR_LABELS.get(
                next((b for b in BehaviorType if b.value == t), None), t
            )
        )
        st.plotly_chart(
            loss_by_behavior_chart(beh_agg.rename(columns={"total_impact": "total_loss_impact"}).to_dict("records")),
            use_container_width=True,
        )
    else:
        st.info("No behavior flags detected yet.")
