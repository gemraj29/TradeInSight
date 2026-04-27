"""Domain models for P&L summaries and metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SymbolPnL:
    """P&L breakdown for a single underlying symbol."""
    underlying: str
    total_pnl: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    expired_trades: int
    avg_win: float
    avg_loss: float
    largest_loss: float
    largest_win: float

    @property
    def win_rate(self) -> float:
        """Win rate as a percentage."""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100


@dataclass
class BehaviorPnL:
    """P&L impact attributed to a specific behavior pattern."""
    behavior_type: str
    behavior_label: str
    total_loss_impact: float
    journey_count: int
    avg_loss_per_journey: float
    pct_of_total_loss: float = 0.0


@dataclass
class PnLSummary:
    """Complete P&L summary across all journeys.

    Attributes:
        total_realized_pnl: Net P&L across all closed journeys.
        total_trades: Total number of completed journeys.
        winning_trades: Journeys with positive P&L.
        losing_trades: Journeys with negative P&L.
        breakeven_trades: Journeys within ±$1 of zero.
        win_rate: Percentage of winning trades.
        avg_win: Average dollar profit on winning trades.
        avg_loss: Average dollar loss on losing trades.
        largest_win: Best single trade P&L.
        largest_loss: Worst single trade P&L.
        profit_factor: Gross wins / gross losses (>1 is good).
        max_drawdown: Maximum peak-to-trough decline in cumulative P&L.
        by_symbol: P&L broken down per underlying symbol.
        by_behavior: P&L impact broken down per behavior type.
        by_strategy: P&L broken down by option strategy (long call, long put, etc.).
        cumulative_pnl_series: Date → cumulative P&L for charting.
        drawdown_series: Date → drawdown value for charting.
    """

    total_realized_pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    by_symbol: List[SymbolPnL] = field(default_factory=list)
    by_behavior: List[BehaviorPnL] = field(default_factory=list)
    by_strategy: Dict[str, float] = field(default_factory=dict)
    cumulative_pnl_series: Dict[str, float] = field(default_factory=dict)
    drawdown_series: Dict[str, float] = field(default_factory=dict)
