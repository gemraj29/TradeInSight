"""Averaging Down Analysis — visualize cost of adding to losing positions."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.core.database import get_session, init_db
from app.core.repository import fetch_all_journeys, fetch_all_transactions, fetch_behavior_flags
from app.ui.components import (
    COLOR_LOSS, COLOR_WIN, COLOR_WARNING, COLOR_NEUTRAL,
    format_pnl, metric_card, pnl_color,
)
from app.ui.state import init_state

st.set_page_config(page_title="Averaging Down | TradeInSight", layout="wide", page_icon="📉")
init_db()
init_state()
st.markdown(
    "<style>.stApp{background:#0f172a} h1,h2,h3{color:#e2e8f0!important}</style>",
    unsafe_allow_html=True,
)

st.title("📉 Averaging Down Analysis")
st.caption("How much did adding to losing positions cost you?")
st.divider()

with get_session() as session:
    journeys = fetch_all_journeys(session)
    transactions = fetch_all_transactions(session)
    flag_dicts = fetch_behavior_flags(session)

if not journeys:
    st.info("No data yet.")
    st.stop()

# Find avg-down journeys
avg_down_flags = {f["journey_id"] for f in flag_dicts if f["behavior_type"] == "averaging_down"}
avg_down_journeys = [j for j in journeys if j["journey_id"] in avg_down_flags]
other_journeys = [j for j in journeys if j["journey_id"] not in avg_down_flags and j["status"] in ("closed", "expired")]

avg_down_pnl = sum(j["realized_pnl"] for j in avg_down_journeys)
other_pnl = sum(j["realized_pnl"] for j in other_journeys)

c1, c2, c3, c4 = st.columns(4)
with c1:
    metric_card("Avg-Down Trades", str(len(avg_down_journeys)), "journeys flagged", color=COLOR_WARNING)
with c2:
    metric_card("Total P&L (avg-down)", format_pnl(avg_down_pnl), color=pnl_color(avg_down_pnl))
with c3:
    metric_card("Other Trades P&L", format_pnl(other_pnl), color=pnl_color(other_pnl))
with c4:
    avg_adds = sum(j["num_adds"] for j in avg_down_journeys) / max(len(avg_down_journeys), 1)
    metric_card("Avg Adds Per Trade", f"{avg_adds:.1f}", "times doubled down")

if not avg_down_journeys:
    st.success("No averaging-down behavior detected in your trades!")
    st.stop()

st.divider()

# --------------------------------------------------------------------------- #
# Per-journey detail
# --------------------------------------------------------------------------- #
st.markdown("### Averaging-Down Journey Details")

txn_by_symbol = {}
for t in transactions:
    txn_by_symbol.setdefault(t.symbol, []).append(t)

for j in sorted(avg_down_journeys, key=lambda x: x["realized_pnl"]):
    pnl = j["realized_pnl"]
    color = pnl_color(pnl)

    with st.expander(
        f"{j['underlying']} {j.get('opt_type','').upper()} ${j.get('opt_strike',''):g} "
        f"exp {j.get('opt_expiry','')} — P&L: {format_pnl(pnl)} | {j['num_adds']} adds",
        expanded=False,
    ):
        symbol_txns = sorted(txn_by_symbol.get(j["symbol"], []), key=lambda t: t.run_date)
        if not symbol_txns:
            st.caption("No transactions found.")
            continue

        buy_txns = [t for t in symbol_txns if t.quantity > 0]
        if len(buy_txns) < 2:
            continue

        # Entry waterfall chart
        labels = [f"Entry {i+1}\n{t.run_date}" for i, t in enumerate(buy_txns)]
        values = [abs(t.net_amount) for t in buy_txns]
        prices = [t.price for t in buy_txns]

        col_chart, col_table = st.columns([2, 1])
        with col_chart:
            fig = go.Figure()
            colors_bar = [COLOR_WIN] + [COLOR_LOSS] * (len(buy_txns) - 1)
            fig.add_trace(go.Bar(
                x=labels, y=values,
                marker_color=colors_bar,
                text=[f"${v:,.0f}" for v in values],
                textposition="outside",
                name="Cash Deployed",
            ))
            fig.add_trace(go.Scatter(
                x=labels, y=prices,
                mode="lines+markers+text",
                name="Entry Price",
                yaxis="y2",
                line=dict(color=COLOR_WARNING, width=2),
                text=[f"${p:.2f}" for p in prices],
                textposition="top center",
            ))
            fig.update_layout(
                title=f"{j['underlying']} — Cash deployed per entry",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e2e8f0"), height=300,
                yaxis=dict(title="Cash ($)", gridcolor="#334155", tickprefix="$"),
                yaxis2=dict(title="Price ($)", overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", y=-0.2),
                margin=dict(l=10, r=10, t=45, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_table:
            flag_detail = next((f for f in flag_dicts if f["journey_id"] == j["journey_id"]
                                and f["behavior_type"] == "averaging_down"), None)
            if flag_detail:
                st.markdown(f"**Evidence:** {flag_detail.get('evidence', '')}")
                st.markdown(f"**Impact:** {format_pnl(flag_detail.get('estimated_loss_impact', 0))}")
                st.markdown(flag_detail.get("detail", ""))

            st.markdown("**Rule to apply:**")
            st.info("Never add to a losing long-option position. If wrong, exit — do not double down.")

# --------------------------------------------------------------------------- #
# Summary comparison chart
# --------------------------------------------------------------------------- #
st.divider()
st.markdown("### Avg-Down Trades vs Clean Trades")

avg_wins = sum(1 for j in avg_down_journeys if j["realized_pnl"] > 0)
avg_losses = sum(1 for j in avg_down_journeys if j["realized_pnl"] < 0)
other_wins = sum(1 for j in other_journeys if j["realized_pnl"] > 0)
other_losses = sum(1 for j in other_journeys if j["realized_pnl"] < 0)

fig_compare = go.Figure(data=[
    go.Bar(name="Wins", x=["Avg-Down Trades", "Clean Trades"],
           y=[avg_wins, other_wins], marker_color=COLOR_WIN),
    go.Bar(name="Losses", x=["Avg-Down Trades", "Clean Trades"],
           y=[avg_losses, other_losses], marker_color=COLOR_LOSS),
])
fig_compare.update_layout(
    barmode="group", title="Win/Loss Count Comparison",
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#e2e8f0"), height=320,
    xaxis=dict(gridcolor="#334155"), yaxis=dict(gridcolor="#334155"),
    margin=dict(l=10, r=10, t=45, b=10),
)
st.plotly_chart(fig_compare, use_container_width=True)
