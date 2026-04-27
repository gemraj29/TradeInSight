"""Overview page — KPI metrics, cumulative P&L, drawdown, and top-level charts."""

import pandas as pd
import streamlit as st

from app.core.database import get_session, init_db
from app.core.repository import fetch_all_journeys, fetch_behavior_flags
from app.domain.models.behavior_flag import BehaviorFlag, BehaviorType
from app.domain.models.trade_journey import JourneyOutcome, JourneyStatus, TradeJourney
from app.features.behavior_analyzer.analyzer import analyze_journeys
from app.features.journey_engine.grouper import build_journeys
from app.features.pnl_engine.calculator import calculate_pnl
from app.ui.components import (
    COLOR_LOSS, COLOR_WIN, COLOR_NEUTRAL,
    cumulative_pnl_chart, drawdown_chart,
    format_pnl, metric_card, pnl_by_symbol_chart,
    pnl_color, strategy_pnl_chart, win_rate_gauge,
)
from app.ui.state import init_state

st.set_page_config(page_title="Overview | TradeInSight", layout="wide", page_icon="📊")
init_db()
init_state()

st.markdown(
    "<style>.stApp{background:#0f172a} h1,h2,h3{color:#e2e8f0!important}</style>",
    unsafe_allow_html=True,
)

st.title("📊 Overview")
st.caption("Your complete trading P&L summary")
st.divider()

# --------------------------------------------------------------------------- #
# Load data
# --------------------------------------------------------------------------- #
with get_session() as session:
    journey_dicts = fetch_all_journeys(session)
    flag_dicts = fetch_behavior_flags(session)

if not journey_dicts:
    st.info("No trade data yet. Go to **Import Statements** to load your Fidelity CSV.")
    st.stop()

# Reconstruct lightweight summary from stored dicts
closed = [j for j in journey_dicts if j["status"] in ("closed", "expired")]
all_pnl = [j["realized_pnl"] for j in closed]
wins = [p for p in all_pnl if p > 1]
losses = [p for p in all_pnl if p < -1]
total_pnl = sum(all_pnl)
win_rate = (len(wins) / len(closed) * 100) if closed else 0.0
avg_win = sum(wins) / len(wins) if wins else 0.0
avg_loss = sum(losses) / len(losses) if losses else 0.0
largest_win = max(wins) if wins else 0.0
largest_loss = min(losses) if losses else 0.0
profit_factor = (sum(wins) / abs(sum(losses))) if losses else float("inf")

# --------------------------------------------------------------------------- #
# KPI row
# --------------------------------------------------------------------------- #
c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    metric_card("Total P&L", format_pnl(total_pnl), color=pnl_color(total_pnl))
with c2:
    metric_card("Win Rate", f"{win_rate:.1f}%", f"{len(wins)}W / {len(losses)}L",
                color=COLOR_WIN if win_rate >= 50 else COLOR_LOSS)
with c3:
    metric_card("Avg Win", f"${avg_win:,.2f}", "per trade", color=COLOR_WIN)
with c4:
    metric_card("Avg Loss", format_pnl(avg_loss), "per trade", color=COLOR_LOSS)
with c5:
    metric_card("Profit Factor", f"{profit_factor:.2f}" if profit_factor != float("inf") else "∞",
                ">1 is profitable", color=COLOR_WIN if profit_factor > 1 else COLOR_LOSS)
with c6:
    metric_card("Total Trades", str(len(closed)), f"{len(journey_dicts)} total journeys")

st.divider()

# --------------------------------------------------------------------------- #
# Charts row 1: cumulative P&L + drawdown
# --------------------------------------------------------------------------- #
df = pd.DataFrame(closed)
df["exit_date"] = pd.to_datetime(df["exit_date"], errors="coerce")
df = df.dropna(subset=["exit_date"]).sort_values("exit_date")

cum_series = {}
dd_series = {}
running = 0.0
peak = 0.0
for _, row in df.iterrows():
    running += row["realized_pnl"]
    cum_series[str(row["exit_date"].date())] = round(running, 2)
    if running > peak:
        peak = running
    dd_series[str(row["exit_date"].date())] = round(running - peak, 2)

col_a, col_b = st.columns(2)
with col_a:
    st.plotly_chart(cumulative_pnl_chart(cum_series), use_container_width=True)
with col_b:
    st.plotly_chart(drawdown_chart(dd_series), use_container_width=True)

# --------------------------------------------------------------------------- #
# Charts row 2: P&L by symbol + strategy
# --------------------------------------------------------------------------- #
symbol_agg = (
    df.groupby("underlying")["realized_pnl"].sum().reset_index()
    .rename(columns={"realized_pnl": "total_pnl"})
    .to_dict("records")
)

strategy_map = {}
for j in journey_dicts:
    strat = f"Long {j['opt_type'].title()}" if j.get("opt_type") else "Stock"
    strategy_map[strat] = strategy_map.get(strat, 0) + j["realized_pnl"]

col_c, col_d = st.columns(2)
with col_c:
    st.plotly_chart(pnl_by_symbol_chart(symbol_agg), use_container_width=True)
with col_d:
    st.plotly_chart(strategy_pnl_chart(strategy_map), use_container_width=True)

# --------------------------------------------------------------------------- #
# Win rate gauge + top losers table
# --------------------------------------------------------------------------- #
col_e, col_f = st.columns([1, 2])
with col_e:
    st.plotly_chart(win_rate_gauge(win_rate), use_container_width=True)
    max_dd = min(dd_series.values()) if dd_series else 0.0
    metric_card("Max Drawdown", format_pnl(max_dd), "peak-to-trough", color=COLOR_LOSS)

with col_f:
    st.markdown("#### Top Losing Trades")
    losers_df = (
        df[df["realized_pnl"] < 0]
        .sort_values("realized_pnl")
        .head(10)[["underlying", "opt_type", "opt_strike", "opt_expiry", "realized_pnl", "num_adds", "was_rolled"]]
        .rename(columns={
            "underlying": "Symbol", "opt_type": "Type", "opt_strike": "Strike",
            "opt_expiry": "Expiry", "realized_pnl": "P&L",
            "num_adds": "Adds", "was_rolled": "Rolled",
        })
    )
    if not losers_df.empty:
        losers_df["P&L"] = losers_df["P&L"].apply(lambda v: f"${v:,.2f}")
        st.dataframe(losers_df, use_container_width=True, hide_index=True)
    else:
        st.success("No losing trades found!")
