"""P&L Engine — calculates all trading metrics from a list of trade journeys.

Produces a PnLSummary with:
- Overall totals: realized P&L, win rate, avg win/loss, profit factor, max drawdown
- Per-symbol breakdown
- Per-behavior breakdown (estimated loss attributable to each behavior)
- Per-strategy breakdown (long call, long put, etc.)
- Time-series data for cumulative P&L and drawdown charts
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

import pandas as pd

from app.core.logging_setup import get_logger
from app.domain.models.behavior_flag import BehaviorFlag, BEHAVIOR_LABELS
from app.domain.models.pnl import BehaviorPnL, PnLSummary, SymbolPnL
from app.domain.models.trade_journey import JourneyOutcome, JourneyStatus, TradeJourney

logger = get_logger(__name__)


def calculate_pnl(
    journeys: List[TradeJourney],
    behavior_flags: Optional[List[BehaviorFlag]] = None,
) -> PnLSummary:
    """Compute a full PnLSummary from journeys and optional behavior flags.

    Args:
        journeys: All trade journeys for the account.
        behavior_flags: Detected behavior flags (used for per-behavior P&L).

    Returns:
        PnLSummary with all metrics populated.
    """
    closed = [j for j in journeys if j.status in (JourneyStatus.CLOSED, JourneyStatus.EXPIRED)]

    summary = PnLSummary()

    if not closed:
        logger.info("No closed journeys — P&L summary is empty")
        return summary

    summary.total_trades = len(closed)
    summary.winning_trades = sum(1 for j in closed if j.outcome == JourneyOutcome.WIN)
    summary.losing_trades = sum(1 for j in closed if j.outcome == JourneyOutcome.LOSS)
    summary.breakeven_trades = sum(1 for j in closed if j.outcome == JourneyOutcome.BREAKEVEN)

    summary.total_realized_pnl = sum(j.realized_pnl for j in closed)

    wins = [j.realized_pnl for j in closed if j.outcome == JourneyOutcome.WIN]
    losses = [j.realized_pnl for j in closed if j.outcome == JourneyOutcome.LOSS]

    summary.win_rate = (summary.winning_trades / summary.total_trades * 100) if summary.total_trades else 0.0
    summary.avg_win = (sum(wins) / len(wins)) if wins else 0.0
    summary.avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    summary.largest_win = max(wins) if wins else 0.0
    summary.largest_loss = min(losses) if losses else 0.0

    gross_wins = sum(wins)
    gross_losses = abs(sum(losses))
    summary.profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else float("inf")

    summary.by_symbol = _calc_by_symbol(closed)
    summary.by_strategy = _calc_by_strategy(closed)
    summary.cumulative_pnl_series, summary.drawdown_series = _calc_time_series(closed)
    summary.max_drawdown = min(summary.drawdown_series.values()) if summary.drawdown_series else 0.0

    if behavior_flags:
        summary.by_behavior = _calc_by_behavior(behavior_flags, gross_losses)

    logger.info(
        "P&L: total=%.2f  wins=%d  losses=%d  win_rate=%.1f%%  drawdown=%.2f",
        summary.total_realized_pnl,
        summary.winning_trades,
        summary.losing_trades,
        summary.win_rate,
        summary.max_drawdown,
    )
    return summary


# --------------------------------------------------------------------------- #
# Per-symbol breakdown
# --------------------------------------------------------------------------- #

def _calc_by_symbol(closed: List[TradeJourney]) -> List[SymbolPnL]:
    by_underlying: Dict[str, List[TradeJourney]] = defaultdict(list)
    for j in closed:
        by_underlying[j.underlying].append(j)

    result = []
    for underlying, journeys in by_underlying.items():
        wins = [j.realized_pnl for j in journeys if j.outcome == JourneyOutcome.WIN]
        losses = [j.realized_pnl for j in journeys if j.outcome == JourneyOutcome.LOSS]
        expired = sum(1 for j in journeys if j.status == JourneyStatus.EXPIRED)

        result.append(SymbolPnL(
            underlying=underlying,
            total_pnl=sum(j.realized_pnl for j in journeys),
            total_trades=len(journeys),
            winning_trades=len(wins),
            losing_trades=len(losses),
            expired_trades=expired,
            avg_win=sum(wins) / len(wins) if wins else 0.0,
            avg_loss=sum(losses) / len(losses) if losses else 0.0,
            largest_loss=min(losses) if losses else 0.0,
            largest_win=max(wins) if wins else 0.0,
        ))

    result.sort(key=lambda s: s.total_pnl)  # worst first
    return result


# --------------------------------------------------------------------------- #
# Per-strategy breakdown
# --------------------------------------------------------------------------- #

def _calc_by_strategy(closed: List[TradeJourney]) -> Dict[str, float]:
    by_strategy: Dict[str, float] = defaultdict(float)
    for j in closed:
        strategy = _infer_strategy(j)
        by_strategy[strategy] += j.realized_pnl
    return dict(by_strategy)


def _infer_strategy(journey: TradeJourney) -> str:
    """Infer strategy name from journey attributes."""
    opt = journey.option_details
    if not opt:
        return "Stock"
    # Check first transaction action for direction
    first_action = journey.transactions[0].action if journey.transactions else None
    from app.domain.models.transaction import ActionType, OptionType
    if first_action in (ActionType.BUY_TO_OPEN, ActionType.BUY):
        return f"Long {opt.option_type.value.title()}"
    elif first_action in (ActionType.SELL_TO_OPEN,):
        return f"Short {opt.option_type.value.title()}"
    return "Other"


# --------------------------------------------------------------------------- #
# Per-behavior breakdown
# --------------------------------------------------------------------------- #

def _calc_by_behavior(
    flags: List[BehaviorFlag], total_gross_loss: float
) -> List[BehaviorPnL]:
    from app.domain.models.behavior_flag import BehaviorType
    by_type: Dict[str, List[BehaviorFlag]] = defaultdict(list)
    for f in flags:
        if f.behavior_type != BehaviorType.DISCIPLINED:
            by_type[f.behavior_type.value].append(f)

    result = []
    for btype, type_flags in by_type.items():
        total_impact = sum(f.estimated_loss_impact for f in type_flags)
        count = len(type_flags)
        avg = total_impact / count if count else 0.0
        pct = (abs(total_impact) / total_gross_loss * 100) if total_gross_loss > 0 else 0.0
        label = BEHAVIOR_LABELS.get(
            next((b for b in __import__('app.domain.models.behavior_flag', fromlist=['BehaviorType']).BehaviorType if b.value == btype), None),
            btype
        )
        result.append(BehaviorPnL(
            behavior_type=btype,
            behavior_label=label,
            total_loss_impact=total_impact,
            journey_count=count,
            avg_loss_per_journey=avg,
            pct_of_total_loss=pct,
        ))

    result.sort(key=lambda b: b.total_loss_impact)  # worst first
    return result


# --------------------------------------------------------------------------- #
# Time-series (cumulative P&L + drawdown)
# --------------------------------------------------------------------------- #

def _calc_time_series(
    closed: List[TradeJourney],
) -> tuple[Dict[str, float], Dict[str, float]]:
    """Return (cumulative_pnl_by_date, drawdown_by_date) dicts."""
    # Use exit_date as the event date
    events = [
        (j.exit_date, j.realized_pnl)
        for j in closed
        if j.exit_date
    ]
    if not events:
        return {}, {}

    events.sort(key=lambda e: e[0])

    dates = []
    cum_pnl = []
    running = 0.0
    for dt, pnl in events:
        running += pnl
        dates.append(str(dt))
        cum_pnl.append(round(running, 2))

    # Drawdown
    peak = 0.0
    drawdowns = []
    for val in cum_pnl:
        if val > peak:
            peak = val
        dd = val - peak
        drawdowns.append(round(dd, 2))

    cum_series = dict(zip(dates, cum_pnl))
    dd_series = dict(zip(dates, drawdowns))

    return cum_series, dd_series
