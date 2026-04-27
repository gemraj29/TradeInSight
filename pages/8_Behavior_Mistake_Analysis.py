"""Behavior Mistake Analysis — all detected behavioral flags in one view."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.domain.models.behavior_flag import BEHAVIOR_DESCRIPTIONS, BEHAVIOR_LABELS, BehaviorType
from app.core.database import get_session, init_db
from app.core.repository import fetch_all_journeys, fetch_behavior_flags
from app.ui.components import (
    BEHAVIOR_COLORS, COLOR_LOSS, COLOR_WIN, COLOR_WARNING,
    behavior_badge, format_pnl, metric_card, pnl_color,
)
from app.ui.state import init_state

st.set_page_config(page_title="Behavior Analysis | TradeInSight", layout="wide", page_icon="🧠")
init_db()
init_state()
st.markdown(
    "<style>.stApp{background:#0f172a} h1,h2,h3{color:#e2e8f0!important}</style>",
    unsafe_allow_html=True,
)

st.title("🧠 Behavior Mistake Analysis")
st.caption("Every behavioral flag, ranked by damage")
st.divider()

with get_session() as session:
    journeys = fetch_all_journeys(session)
    flag_dicts = fetch_behavior_flags(session)

if not flag_dicts:
    st.info("No behavior flags yet — import data first.")
    st.stop()

flag_df = pd.DataFrame(flag_dicts)
flag_df["behavior_label"] = flag_df["behavior_type"].apply(
    lambda t: BEHAVIOR_LABELS.get(next((b for b in BehaviorType if b.value == t), None), t)
)

# --------------------------------------------------------------------------- #
# Summary metrics
# --------------------------------------------------------------------------- #
non_disc = flag_df[flag_df["behavior_type"] != "disciplined"]
total_flags = len(non_disc)
total_impact = non_disc["estimated_loss_impact"].sum()
worst_behavior = non_disc.groupby("behavior_label")["estimated_loss_impact"].sum().idxmin() if not non_disc.empty else "N/A"

c1, c2, c3 = st.columns(3)
with c1:
    metric_card("Total Behavior Flags", str(total_flags), "mistakes detected")
with c2:
    metric_card("Total Estimated Impact", format_pnl(total_impact), color=COLOR_LOSS)
with c3:
    metric_card("Most Costly Pattern", worst_behavior, "needs most attention")

st.divider()

# --------------------------------------------------------------------------- #
# Behavior summary chart
# --------------------------------------------------------------------------- #
beh_agg = (
    non_disc.groupby(["behavior_type", "behavior_label"])
    .agg(
        total_impact=("estimated_loss_impact", "sum"),
        count=("journey_id", "count"),
        avg_severity=("severity", "mean"),
    )
    .reset_index()
    .sort_values("total_impact")
)

fig = go.Figure(go.Bar(
    x=beh_agg["total_impact"],
    y=beh_agg["behavior_label"],
    orientation="h",
    marker_color=[BEHAVIOR_COLORS.get(bt, COLOR_LOSS) for bt in beh_agg["behavior_type"]],
    text=[f"{format_pnl(v)} ({c} trades)" for v, c in zip(beh_agg["total_impact"], beh_agg["count"])],
    textposition="outside",
))
fig.update_layout(
    title="Estimated Loss Impact by Behavior",
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#e2e8f0"),
    height=max(300, len(beh_agg) * 50),
    xaxis=dict(gridcolor="#334155", tickprefix="$"),
    yaxis=dict(gridcolor="#334155"),
    margin=dict(l=10, r=120, t=45, b=10),
)
st.plotly_chart(fig, use_container_width=True)

# --------------------------------------------------------------------------- #
# Behavior cards
# --------------------------------------------------------------------------- #
st.markdown("### Behavior Detail Cards")

for _, row in beh_agg.iterrows():
    bt = row["behavior_type"]
    color = BEHAVIOR_COLORS.get(bt, COLOR_LOSS)
    desc = BEHAVIOR_DESCRIPTIONS.get(next((b for b in BehaviorType if b.value == bt), None), "")

    with st.expander(
        f"{row['behavior_label']} — {format_pnl(row['total_impact'])} across {row['count']} trades",
        expanded=False,
    ):
        col_info, col_trades = st.columns([1, 2])
        with col_info:
            st.markdown(f"<span style='color:{color}; font-size:1.2rem; font-weight:700'>{row['behavior_label']}</span>", unsafe_allow_html=True)
            st.markdown(desc)
            avg_sev = row["avg_severity"]
            sev_label = "Low" if avg_sev < 1.5 else "Medium" if avg_sev < 2.5 else "High"
            sev_color = COLOR_WIN if avg_sev < 1.5 else COLOR_WARNING if avg_sev < 2.5 else COLOR_LOSS
            st.markdown(f"**Avg Severity:** <span style='color:{sev_color}'>{sev_label}</span>", unsafe_allow_html=True)

        with col_trades:
            affected = flag_df[flag_df["behavior_type"] == bt][["journey_id", "severity", "estimated_loss_impact", "evidence", "detail"]]
            if not affected.empty:
                display = affected.copy()
                display["estimated_loss_impact"] = display["estimated_loss_impact"].apply(format_pnl)
                st.dataframe(
                    display.rename(columns={
                        "journey_id": "Journey", "severity": "Sev",
                        "estimated_loss_impact": "Impact", "evidence": "Evidence", "detail": "Detail",
                    }),
                    use_container_width=True, hide_index=True,
                )

# --------------------------------------------------------------------------- #
# Severity heatmap
# --------------------------------------------------------------------------- #
st.divider()
st.markdown("### Severity Distribution")

severity_counts = (
    non_disc.groupby(["behavior_label", "severity"])
    .size()
    .reset_index(name="count")
    .pivot(index="behavior_label", columns="severity", values="count")
    .fillna(0)
    .astype(int)
)
if not severity_counts.empty:
    fig_heat = go.Figure(go.Heatmap(
        z=severity_counts.values,
        x=[f"Severity {c}" for c in severity_counts.columns],
        y=severity_counts.index.tolist(),
        colorscale=[[0, "#1e293b"], [0.5, "#f59e0b"], [1.0, "#ef4444"]],
        text=severity_counts.values,
        texttemplate="%{text}",
        showscale=True,
    ))
    fig_heat.update_layout(
        title="Behavior Flag Severity Heatmap",
        paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#e2e8f0"),
        height=max(250, len(severity_counts) * 40),
        margin=dict(l=10, r=10, t=45, b=10),
    )
    st.plotly_chart(fig_heat, use_container_width=True)
