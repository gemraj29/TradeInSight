"""Recovery Plan — top behaviors, rules, what-if simulation, optional AI narrative."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.core.config import settings
from app.core.database import get_session, init_db
from app.core.repository import fetch_all_journeys, fetch_behavior_flags
from app.features.pnl_engine.calculator import calculate_pnl
from app.features.recovery_plan.generator import (
    generate_recovery_plan,
    simulate_without_behavior,
)
from app.domain.models.behavior_flag import BehaviorFlag, BehaviorType
from app.domain.models.trade_journey import TradeJourney, JourneyStatus, JourneyOutcome
from app.ui.components import (
    BEHAVIOR_COLORS, COLOR_LOSS, COLOR_WIN, COLOR_WARNING, COLOR_PRIMARY,
    format_pnl, metric_card, pnl_color,
)
from app.ui.state import init_state

st.set_page_config(page_title="Recovery Plan | TradeInSight", layout="wide", page_icon="🛡️")
init_db()
init_state()
st.markdown(
    "<style>.stApp{background:#0f172a} h1,h2,h3{color:#e2e8f0!important}</style>",
    unsafe_allow_html=True,
)

st.title("🛡️ Recovery Plan")
st.caption("Your personalized action plan — based on actual trading data, not guesses")
st.divider()

# --------------------------------------------------------------------------- #
# Load and reconstruct
# --------------------------------------------------------------------------- #
with get_session() as session:
    journey_dicts = fetch_all_journeys(session)
    flag_dicts = fetch_behavior_flags(session)

if not journey_dicts:
    st.info("No data yet — import statements first.")
    st.stop()

# Lightweight reconstruction for the generator
class _SimpleJourney:
    def __init__(self, d):
        self.journey_id = d["journey_id"]
        self.underlying = d["underlying"]
        self.realized_pnl = d["realized_pnl"]
        self.status = type("S", (), {"value": d["status"]})()
        self.outcome = type("O", (), {"value": d["outcome"]})()

class _SimplePnL:
    def __init__(self, journeys, flags):
        closed = [j for j in journeys if j["status"] in ("closed", "expired")]
        all_pnl = [j["realized_pnl"] for j in closed]
        wins = [p for p in all_pnl if p > 1]
        losses = [p for p in all_pnl if p < -1]
        self.total_realized_pnl = sum(all_pnl)
        self.total_trades = len(closed)
        self.winning_trades = len(wins)
        self.losing_trades = len(losses)
        self.win_rate = (len(wins) / len(closed) * 100) if closed else 0
        self.avg_win = sum(wins) / len(wins) if wins else 0
        self.avg_loss = sum(losses) / len(losses) if losses else 0
        self.by_behavior = []

# Build flags as objects
behavior_flags = []
for f in flag_dicts:
    try:
        bf = BehaviorFlag(
            journey_id=f["journey_id"],
            behavior_type=BehaviorType(f["behavior_type"]),
            severity=f["severity"],
            estimated_loss_impact=f["estimated_loss_impact"],
            detail=f.get("detail", ""),
            evidence=f.get("evidence", ""),
        )
        behavior_flags.append(bf)
    except Exception:
        pass

simple_journeys = [_SimpleJourney(d) for d in journey_dicts]
simple_pnl = _SimplePnL(journey_dicts, flag_dicts)

plan = generate_recovery_plan(simple_journeys, simple_pnl, behavior_flags)

# --------------------------------------------------------------------------- #
# Header metrics
# --------------------------------------------------------------------------- #
c1, c2, c3, c4 = st.columns(4)
with c1:
    metric_card("Total Loss", format_pnl(-plan.total_actual_loss), color=COLOR_LOSS)
with c2:
    metric_card("Avoidable Loss", format_pnl(-plan.total_avoidable_loss),
                f"~{plan.recovery_pct:.0f}% of losses", color=COLOR_WARNING)
with c3:
    metric_card("Behavior Patterns Found", str(len(plan.top_behaviors)), "causing damage")
with c4:
    metric_card("Rules Generated", str(len(plan.suggested_rules)), "to implement now")

st.divider()

# --------------------------------------------------------------------------- #
# AI narrative (if available)
# --------------------------------------------------------------------------- #
if plan.narrative:
    st.markdown("### 🤖 AI Coaching Insight")
    st.markdown(
        f'<div style="background:#1e3a5f; border-left:4px solid #3b82f6; '
        f'padding:1rem 1.2rem; border-radius:0 8px 8px 0; color:#e2e8f0">'
        f'{plan.narrative}</div>',
        unsafe_allow_html=True,
    )
    st.divider()
elif settings.has_llm is False:
    st.caption("💡 Set `ANTHROPIC_API_KEY` in `.env` to get a personalized AI coaching narrative here.")

# --------------------------------------------------------------------------- #
# Top behaviors
# --------------------------------------------------------------------------- #
st.markdown("### Top Loss-Causing Behaviors")

for i, insight in enumerate(plan.top_behaviors, 1):
    color = BEHAVIOR_COLORS.get(insight.behavior_type, COLOR_LOSS)
    with st.container():
        col_rank, col_info, col_nums = st.columns([0.5, 4, 2])
        with col_rank:
            st.markdown(
                f'<div style="background:{color}22; border:1px solid {color}55; '
                f'border-radius:50%; width:40px; height:40px; display:flex; '
                f'align-items:center; justify-content:center; '
                f'font-weight:700; color:{color}; font-size:1.2rem">#{i}</div>',
                unsafe_allow_html=True,
            )
        with col_info:
            st.markdown(
                f'<strong style="color:#e2e8f0; font-size:1rem">{insight.label}</strong>',
                unsafe_allow_html=True,
            )
            st.caption(
                f"{insight.journey_count} trades · "
                f"{insight.pct_of_total_loss:.1f}% of total losses"
            )
            st.markdown(
                f'<div style="background:#1e293b; border-radius:6px; padding:0.6rem 0.8rem; '
                f'border-left:3px solid {color}; color:#94a3b8; font-size:0.85rem; margin-top:4px">'
                f'📌 {insight.rule}</div>',
                unsafe_allow_html=True,
            )
        with col_nums:
            st.markdown(
                f'<div style="text-align:right">'
                f'<div style="color:{COLOR_LOSS}; font-size:1.3rem; font-weight:700">'
                f'{format_pnl(insight.total_loss)}</div>'
                f'<div style="color:#94a3b8; font-size:0.8rem">total impact</div>'
                f'<div style="color:{COLOR_WIN}; font-size:1rem; font-weight:600; margin-top:6px">'
                f'+{format_pnl(insight.what_if_savings)}</div>'
                f'<div style="color:#94a3b8; font-size:0.8rem">est. savings if avoided</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    st.markdown("<hr style='border-color:#1e293b; margin:0.5rem 0'>", unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# What-if simulation
# --------------------------------------------------------------------------- #
st.divider()
st.markdown("### 🔮 What-If Simulation")
st.caption("Select a behavior to see how your P&L would have looked if you had avoided it.")

behavior_options = {i.label: i.behavior_type for i in plan.top_behaviors}
if behavior_options:
    selected_label = st.selectbox("Simulate avoiding:", list(behavior_options.keys()))
    selected_bt = behavior_options[selected_label]

    sim_pnl, saved = simulate_without_behavior(simple_journeys, behavior_flags, selected_bt)
    actual_pnl = sum(j["realized_pnl"] for j in journey_dicts if j["status"] in ("closed", "expired"))

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        metric_card("Actual P&L", format_pnl(actual_pnl), color=pnl_color(actual_pnl))
    with col_b:
        metric_card("Simulated P&L", format_pnl(sim_pnl),
                    f"if no {selected_label}", color=pnl_color(sim_pnl))
    with col_c:
        metric_card("Estimated Savings", format_pnl(saved),
                    "approximate improvement", color=COLOR_WIN if saved > 0 else COLOR_LOSS)

    # Waterfall chart
    fig_wf = go.Figure(go.Waterfall(
        name="What-If", orientation="v",
        measure=["absolute", "relative", "total"],
        x=["Actual P&L", f"If no {selected_label}", "Simulated P&L"],
        y=[actual_pnl, saved, 0],
        connector=dict(line=dict(color="#475569")),
        increasing=dict(marker=dict(color=COLOR_WIN)),
        decreasing=dict(marker=dict(color=COLOR_LOSS)),
        totals=dict(marker=dict(color=COLOR_PRIMARY)),
        text=[format_pnl(actual_pnl), f"+{format_pnl(saved)}", format_pnl(sim_pnl)],
        textposition="outside",
    ))
    fig_wf.update_layout(
        title=f"P&L Impact of Avoiding '{selected_label}'",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"), height=320,
        yaxis=dict(gridcolor="#334155", tickprefix="$"),
        xaxis=dict(gridcolor="#334155"),
        margin=dict(l=10, r=10, t=45, b=10),
    )
    st.plotly_chart(fig_wf, use_container_width=True)

# --------------------------------------------------------------------------- #
# Suggested rules summary
# --------------------------------------------------------------------------- #
st.divider()
st.markdown("### 📋 Your Rule Set")
st.caption("These rules were generated from your actual trading data — not generic advice.")

for i, rule in enumerate(plan.suggested_rules, 1):
    st.markdown(
        f'<div style="background:#1e293b; border-radius:8px; padding:0.75rem 1rem; '
        f'border-left:3px solid {COLOR_PRIMARY}; color:#e2e8f0; margin-bottom:8px">'
        f'<strong style="color:{COLOR_PRIMARY}">Rule {i}:</strong> {rule}</div>',
        unsafe_allow_html=True,
    )

st.divider()
st.info(
    "💾 Go to **Settings / Rules** to save these rules permanently, "
    "add your own custom rules, and adjust detection thresholds."
)
