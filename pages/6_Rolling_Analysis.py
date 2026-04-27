"""Rolling Analysis — cost of rolling losing options to further expiries."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.core.database import get_session, init_db
from app.core.repository import fetch_all_journeys, fetch_behavior_flags
from app.ui.components import (
    COLOR_LOSS, COLOR_WIN, COLOR_WARNING,
    format_pnl, metric_card, pnl_color,
)
from app.ui.state import init_state

st.set_page_config(page_title="Rolling Analysis | TradeInSight", layout="wide", page_icon="🔄")
init_db()
init_state()
st.markdown(
    "<style>.stApp{background:#0f172a} h1,h2,h3{color:#e2e8f0!important}</style>",
    unsafe_allow_html=True,
)

st.title("🔄 Rolling Analysis")
st.caption("Did rolling losers to further expiries help or hurt?")
st.divider()

with get_session() as session:
    journeys = fetch_all_journeys(session)
    flag_dicts = fetch_behavior_flags(session)

if not journeys:
    st.info("No data yet.")
    st.stop()

rolled_journeys = [j for j in journeys if j.get("was_rolled")]
roll_flag_ids = {f["journey_id"] for f in flag_dicts if f["behavior_type"] == "rolling_loser"}
rolled_losers = [j for j in rolled_journeys if j["journey_id"] in roll_flag_ids]
rolled_total_pnl = sum(j["realized_pnl"] for j in rolled_journeys)

c1, c2, c3 = st.columns(3)
with c1:
    metric_card("Rolled Positions", str(len(rolled_journeys)), "total rolls detected")
with c2:
    metric_card("Rolled Loser Flags", str(len(rolled_losers)), "rolled while in loss")
with c3:
    metric_card("Total P&L (rolled)", format_pnl(rolled_total_pnl), color=pnl_color(rolled_total_pnl))

if not rolled_journeys:
    st.success("No rolling behavior detected.")
    st.stop()

st.divider()

# --------------------------------------------------------------------------- #
# Rolled trades table
# --------------------------------------------------------------------------- #
df_rolled = pd.DataFrame(rolled_journeys)
df_rolled["flagged"] = df_rolled["journey_id"].isin(roll_flag_ids)
df_rolled["P&L"] = df_rolled["realized_pnl"].apply(format_pnl)
display_cols = ["underlying", "opt_type", "opt_strike", "opt_expiry", "realized_pnl", "roll_count", "flagged"]
avail_cols = [c for c in display_cols if c in df_rolled.columns]

st.markdown("### Rolled Positions Detail")
st.dataframe(
    df_rolled[avail_cols].rename(columns={
        "underlying": "Symbol", "opt_type": "Type", "opt_strike": "Strike",
        "opt_expiry": "Expiry", "realized_pnl": "P&L", "roll_count": "Rolls", "flagged": "Loser Roll?"
    }),
    use_container_width=True, hide_index=True,
)

# --------------------------------------------------------------------------- #
# Roll outcome chart
# --------------------------------------------------------------------------- #
st.divider()
st.markdown("### Roll Outcome: Did it Help?")

win_after_roll = sum(1 for j in rolled_journeys if j["realized_pnl"] > 0)
loss_after_roll = len(rolled_journeys) - win_after_roll

col1, col2 = st.columns(2)
with col1:
    fig_pie = go.Figure(go.Pie(
        labels=["Still Lost", "Recovered to Win"],
        values=[loss_after_roll, win_after_roll],
        marker_colors=[COLOR_LOSS, COLOR_WIN],
        hole=0.5,
        textinfo="percent+label",
    ))
    fig_pie.update_layout(
        title="Outcome After Rolling",
        paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#e2e8f0"), height=280,
        margin=dict(l=10, r=10, t=45, b=10),
    )
    st.plotly_chart(fig_pie, use_container_width=True)

with col2:
    st.markdown("#### What Rolling Really Costs")
    st.markdown(
        """
        Rolling a losing option to a further expiry feels like "giving it more time" —
        but it typically:

        - **Locks in** the current loss as realized cost
        - **Increases max loss** with a new premium at risk
        - **Delays** the emotional acceptance of a failed trade
        - **Compounds** theta decay risk at a further date

        The data shows that rolling a loser to a win is rare.
        The better rule: **accept the loss, wait for a better setup.**
        """
    )
    st.info("Rule: Do not roll a position that is down more than 50% of its purchase price.")
