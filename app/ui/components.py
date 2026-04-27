"""Shared Streamlit UI component library.

All chart and display helpers live here to keep pages thin.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# --------------------------------------------------------------------------- #
# Color palette
# --------------------------------------------------------------------------- #
COLOR_WIN = "#22c55e"
COLOR_LOSS = "#ef4444"
COLOR_NEUTRAL = "#6b7280"
COLOR_PRIMARY = "#3b82f6"
COLOR_WARNING = "#f59e0b"

BEHAVIOR_COLORS = {
    "averaging_down": "#ef4444",
    "rolling_loser": "#f97316",
    "near_expiry_hold": "#f59e0b",
    "oversized_position": "#8b5cf6",
    "fomo_entry": "#ec4899",
    "late_exit": "#06b6d4",
    "repeat_loser": "#dc2626",
    "disciplined": "#22c55e",
}


# --------------------------------------------------------------------------- #
# KPI metric cards
# --------------------------------------------------------------------------- #

def metric_card(label: str, value: str, delta: Optional[str] = None, color: Optional[str] = None) -> None:
    """Render a styled metric card.

    Args:
        label: Card title.
        value: Primary displayed value.
        delta: Optional delta/subtitle text.
        color: Optional CSS color override for the value text.
    """
    color_style = f"color: {color};" if color else ""
    delta_html = f'<p style="font-size:0.8rem; color:#6b7280; margin:0">{delta}</p>' if delta else ""
    st.markdown(
        f"""
        <div style="background:#1e293b; border-radius:10px; padding:1rem 1.2rem;
                    border:1px solid #334155; margin-bottom:0.5rem;">
          <p style="font-size:0.75rem; color:#94a3b8; margin:0 0 0.25rem 0;
                    text-transform:uppercase; letter-spacing:0.05em">{label}</p>
          <p style="font-size:1.6rem; font-weight:700; margin:0; {color_style}">{value}</p>
          {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def pnl_color(value: float) -> str:
    """Return the appropriate color string for a P&L value."""
    return COLOR_WIN if value >= 0 else COLOR_LOSS


def format_pnl(value: float) -> str:
    """Format a P&L value as a colored dollar string."""
    sign = "+" if value >= 0 else ""
    return f"{sign}${value:,.2f}"


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #

def cumulative_pnl_chart(cum_series: Dict[str, float]) -> go.Figure:
    """Render a cumulative P&L line chart.

    Args:
        cum_series: Date string → cumulative P&L value dict.

    Returns:
        Plotly Figure.
    """
    if not cum_series:
        return _empty_chart("No closed trades yet")

    df = pd.DataFrame(list(cum_series.items()), columns=["date", "cumulative_pnl"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=df["cumulative_pnl"],
        mode="lines+markers",
        name="Cumulative P&L",
        line=dict(color=COLOR_PRIMARY, width=2),
        marker=dict(size=5),
        fill="tozeroy",
        fillcolor="rgba(59,130,246,0.1)",
    ))
    fig.add_hline(y=0, line_dash="dot", line_color=COLOR_NEUTRAL, line_width=1)
    fig.update_layout(**_chart_layout("Cumulative Realized P&L"))
    fig.update_yaxes(tickprefix="$")
    return fig


def drawdown_chart(dd_series: Dict[str, float]) -> go.Figure:
    """Render a drawdown chart.

    Args:
        dd_series: Date string → drawdown value dict.

    Returns:
        Plotly Figure.
    """
    if not dd_series:
        return _empty_chart("No drawdown data")

    df = pd.DataFrame(list(dd_series.items()), columns=["date", "drawdown"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=df["drawdown"],
        mode="lines",
        name="Drawdown",
        line=dict(color=COLOR_LOSS, width=2),
        fill="tozeroy",
        fillcolor="rgba(239,68,68,0.15)",
    ))
    fig.update_layout(**_chart_layout("Drawdown from Peak"))
    fig.update_yaxes(tickprefix="$")
    return fig


def pnl_by_symbol_chart(by_symbol_data: List[dict]) -> go.Figure:
    """Render a horizontal bar chart of P&L per underlying.

    Args:
        by_symbol_data: List of dicts with 'underlying' and 'total_pnl' keys.

    Returns:
        Plotly Figure.
    """
    if not by_symbol_data:
        return _empty_chart("No data")

    df = pd.DataFrame(by_symbol_data).sort_values("total_pnl")
    colors = [COLOR_WIN if v >= 0 else COLOR_LOSS for v in df["total_pnl"]]

    fig = go.Figure(go.Bar(
        x=df["total_pnl"],
        y=df["underlying"],
        orientation="h",
        marker_color=colors,
        text=[format_pnl(v) for v in df["total_pnl"]],
        textposition="outside",
    ))
    fig.update_layout(**_chart_layout("P&L by Symbol"))
    fig.update_xaxes(tickprefix="$")
    return fig


def loss_by_behavior_chart(by_behavior_data: List[dict]) -> go.Figure:
    """Render a bar chart of estimated loss impact per behavior type.

    Args:
        by_behavior_data: List of dicts with 'behavior_label' and 'total_loss_impact'.

    Returns:
        Plotly Figure.
    """
    if not by_behavior_data:
        return _empty_chart("No behavior data")

    df = pd.DataFrame(by_behavior_data)
    df = df[df["total_loss_impact"] < 0].sort_values("total_loss_impact")

    if df.empty:
        return _empty_chart("No loss-causing behaviors detected")

    fig = go.Figure(go.Bar(
        x=df["total_loss_impact"],
        y=df["behavior_label"],
        orientation="h",
        marker_color=[
            BEHAVIOR_COLORS.get(bt, COLOR_LOSS)
            for bt in df.get("behavior_type", df["behavior_label"])
        ],
        text=[f"${abs(v):,.0f}" for v in df["total_loss_impact"]],
        textposition="outside",
    ))
    fig.update_layout(**_chart_layout("Estimated Loss by Behavior"))
    fig.update_xaxes(tickprefix="$")
    return fig


def win_rate_gauge(win_rate: float) -> go.Figure:
    """Render a gauge chart showing win rate.

    Args:
        win_rate: Win rate percentage (0–100).

    Returns:
        Plotly Figure.
    """
    color = COLOR_WIN if win_rate >= 50 else COLOR_LOSS
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=win_rate,
        number={"suffix": "%", "font": {"size": 28}},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 40], "color": "rgba(239,68,68,0.15)"},
                {"range": [40, 60], "color": "rgba(245,158,11,0.15)"},
                {"range": [60, 100], "color": "rgba(34,197,94,0.15)"},
            ],
            "threshold": {"line": {"color": COLOR_NEUTRAL, "width": 2}, "value": 50},
        },
        title={"text": "Win Rate"},
    ))
    fig.update_layout(height=200, margin=dict(l=20, r=20, t=40, b=10), paper_bgcolor="rgba(0,0,0,0)")
    return fig


def strategy_pnl_chart(by_strategy: Dict[str, float]) -> go.Figure:
    """Render a pie/bar chart of P&L by strategy.

    Args:
        by_strategy: Strategy name → total P&L dict.

    Returns:
        Plotly Figure.
    """
    if not by_strategy:
        return _empty_chart("No strategy data")

    df = pd.DataFrame(list(by_strategy.items()), columns=["strategy", "pnl"])
    df = df.sort_values("pnl")
    colors = [COLOR_WIN if v >= 0 else COLOR_LOSS for v in df["pnl"]]

    fig = go.Figure(go.Bar(
        x=df["strategy"],
        y=df["pnl"],
        marker_color=colors,
        text=[format_pnl(v) for v in df["pnl"]],
        textposition="outside",
    ))
    fig.update_layout(**_chart_layout("P&L by Strategy"))
    fig.update_yaxes(tickprefix="$")
    return fig


def expiry_risk_chart(journeys_df: pd.DataFrame) -> go.Figure:
    """Render a scatter chart showing DTE at entry vs realized P&L.

    Args:
        journeys_df: DataFrame with 'dte_at_first_entry' and 'realized_pnl' columns.

    Returns:
        Plotly Figure.
    """
    if journeys_df.empty:
        return _empty_chart("No DTE data available")

    df = journeys_df.dropna(subset=["dte_at_first_entry", "realized_pnl"]).copy()
    df["color"] = df["realized_pnl"].apply(lambda v: COLOR_WIN if v >= 0 else COLOR_LOSS)
    df["size"] = df["realized_pnl"].abs().clip(lower=100) / 100

    fig = px.scatter(
        df,
        x="dte_at_first_entry",
        y="realized_pnl",
        color="realized_pnl",
        color_continuous_scale=["#ef4444", "#6b7280", "#22c55e"],
        hover_data=["underlying", "realized_pnl", "dte_at_first_entry"],
        labels={"dte_at_first_entry": "DTE at Entry", "realized_pnl": "Realized P&L"},
    )
    fig.add_vline(x=21, line_dash="dot", line_color=COLOR_WARNING, annotation_text="21 DTE")
    fig.add_hline(y=0, line_dash="dot", line_color=COLOR_NEUTRAL)
    fig.update_layout(**_chart_layout("P&L vs Days-to-Expiry at Entry"))
    fig.update_yaxes(tickprefix="$")
    return fig


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _chart_layout(title: str) -> dict:
    """Return standard dark-theme Plotly layout kwargs."""
    return dict(
        title=dict(text=title, font=dict(size=14, color="#e2e8f0")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
        margin=dict(l=10, r=10, t=45, b=10),
        height=320,
        xaxis=dict(gridcolor="#334155", zerolinecolor="#475569"),
        yaxis=dict(gridcolor="#334155", zerolinecolor="#475569"),
    )


def _empty_chart(message: str) -> go.Figure:
    """Return a blank chart with a centered message."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=14, color="#94a3b8"),
    )
    fig.update_layout(**_chart_layout(""))
    return fig


def behavior_badge(behavior_type: str, label: str) -> str:
    """Return an HTML badge for a behavior type."""
    color = BEHAVIOR_COLORS.get(behavior_type, COLOR_NEUTRAL)
    return (
        f'<span style="background:{color}22; color:{color}; border:1px solid {color}55; '
        f'border-radius:4px; padding:2px 8px; font-size:0.75rem; '
        f'font-weight:600; margin-right:4px">{label}</span>'
    )
