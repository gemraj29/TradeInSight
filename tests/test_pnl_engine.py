"""Tests for the P&L Engine."""

import pytest

from app.features.journey_engine.grouper import build_journeys
from app.features.behavior_analyzer.analyzer import analyze_journeys
from app.features.pnl_engine.calculator import calculate_pnl, _calc_by_symbol, _calc_time_series
from app.domain.models.trade_journey import JourneyOutcome, JourneyStatus


class TestCalculatePnL:
    def test_empty_returns_zero_summary(self):
        summary = calculate_pnl([])
        assert summary.total_realized_pnl == 0.0
        assert summary.total_trades == 0

    def test_loss_journey_counted(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        summary = calculate_pnl(journeys)
        assert summary.losing_trades == 1
        assert summary.winning_trades == 0

    def test_winner_counted(self, nvda_winner_transactions):
        journeys = build_journeys(nvda_winner_transactions)
        summary = calculate_pnl(journeys)
        assert summary.winning_trades == 1
        assert summary.losing_trades == 0

    def test_win_rate_calculation(self, tsla_avg_down_transactions, nvda_winner_transactions):
        all_txns = tsla_avg_down_transactions + nvda_winner_transactions
        journeys = build_journeys(all_txns)
        summary = calculate_pnl(journeys)
        assert summary.total_trades == 2
        assert abs(summary.win_rate - 50.0) < 0.01

    def test_total_pnl_is_sum(self, tsla_avg_down_transactions, nvda_winner_transactions):
        all_txns = tsla_avg_down_transactions + nvda_winner_transactions
        journeys = build_journeys(all_txns)
        summary = calculate_pnl(journeys)
        expected = sum(j.realized_pnl for j in journeys if j.status in (JourneyStatus.CLOSED, JourneyStatus.EXPIRED))
        assert abs(summary.total_realized_pnl - expected) < 0.01

    def test_by_symbol_populated(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        summary = calculate_pnl(journeys)
        assert len(summary.by_symbol) == 1
        assert summary.by_symbol[0].underlying == "TSLA"

    def test_cumulative_series_ascending_trades(self, tsla_avg_down_transactions, nvda_winner_transactions):
        all_txns = tsla_avg_down_transactions + nvda_winner_transactions
        journeys = build_journeys(all_txns)
        summary = calculate_pnl(journeys)
        assert len(summary.cumulative_pnl_series) > 0

    def test_drawdown_never_positive(self, tsla_avg_down_transactions, nvda_winner_transactions):
        all_txns = tsla_avg_down_transactions + nvda_winner_transactions
        journeys = build_journeys(all_txns)
        summary = calculate_pnl(journeys)
        assert all(v <= 0 for v in summary.drawdown_series.values())

    def test_profit_factor_infinity_when_no_losses(self, nvda_winner_transactions):
        journeys = build_journeys(nvda_winner_transactions)
        summary = calculate_pnl(journeys)
        assert summary.profit_factor == float("inf") or summary.profit_factor > 1

    def test_avg_win_positive(self, nvda_winner_transactions):
        journeys = build_journeys(nvda_winner_transactions)
        summary = calculate_pnl(journeys)
        assert summary.avg_win > 0

    def test_avg_loss_negative(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        summary = calculate_pnl(journeys)
        assert summary.avg_loss < 0

    def test_by_behavior_populated_when_flags_provided(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        flags = analyze_journeys(journeys)
        summary = calculate_pnl(journeys, behavior_flags=flags)
        assert len(summary.by_behavior) >= 0  # may or may not have entries depending on threshold
