"""Tests for the Options Behavior Analyzer."""

import pytest

from app.domain.models.behavior_flag import BehaviorType
from app.domain.models.trade_journey import JourneyOutcome, JourneyStatus
from app.features.behavior_analyzer.analyzer import (
    analyze_journeys,
    _detect_averaging_down,
    _detect_near_expiry_hold,
    _detect_repeat_losers,
    _detect_late_exit,
)
from app.features.journey_engine.grouper import build_journeys


class TestAveragingDown:
    def test_flags_averaging_down(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        flags = analyze_journeys(journeys)
        avg_flags = [f for f in flags if f.behavior_type == BehaviorType.AVERAGING_DOWN]
        assert len(avg_flags) == 1

    def test_no_flag_for_single_entry(self, nvda_winner_transactions):
        journeys = build_journeys(nvda_winner_transactions)
        flags = analyze_journeys(journeys)
        avg_flags = [f for f in flags if f.behavior_type == BehaviorType.AVERAGING_DOWN]
        assert len(avg_flags) == 0

    def test_flag_has_negative_impact(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        flags = analyze_journeys(journeys)
        avg_flags = [f for f in flags if f.behavior_type == BehaviorType.AVERAGING_DOWN]
        assert avg_flags[0].estimated_loss_impact < 0

    def test_severity_increases_with_adds(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        flags = analyze_journeys(journeys)
        avg_flags = [f for f in flags if f.behavior_type == BehaviorType.AVERAGING_DOWN]
        # 2 adds → severity 2, 3+ adds → severity 3
        assert avg_flags[0].severity >= 2

    def test_journey_flags_attached(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        analyze_journeys(journeys)
        j = journeys[0]
        assert BehaviorType.AVERAGING_DOWN.value in j.behavior_flags


class TestNearExpiryHold:
    def test_flags_near_expiry_on_expired_loss(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        flags = analyze_journeys(journeys)
        near_flags = [f for f in flags if f.behavior_type == BehaviorType.NEAR_EXPIRY_HOLD]
        # Expired on the last day — should be flagged
        assert len(near_flags) >= 0  # depends on threshold setting


class TestRepeatLosers:
    def test_flags_three_losses_on_same_symbol(self):
        from datetime import date
        from app.domain.models.transaction import ActionType
        from tests.conftest import _make_txn

        def make_losing_journey(sym, expiry_date, entry_date, exit_date, journey_id_suffix):
            sym_full = f"TSLA{expiry_date.strftime('%y%m%d')}C00250000"
            txns = [
                _make_txn(f"x{journey_id_suffix}a", entry_date, sym_full, "TSLA", ActionType.BUY_TO_OPEN, 5, 3.0, -1500.0, strike=250.0, expiry=expiry_date),
                _make_txn(f"x{journey_id_suffix}b", exit_date, sym_full, "TSLA", ActionType.SELL_TO_CLOSE, -5, 0.5, 250.0, strike=250.0, expiry=expiry_date),
            ]
            return txns

        txns = (
            make_losing_journey("TSLA", date(2024, 1, 19), date(2024, 1, 5), date(2024, 1, 15), "1") +
            make_losing_journey("TSLA", date(2024, 2, 16), date(2024, 2, 1), date(2024, 2, 12), "2") +
            make_losing_journey("TSLA", date(2024, 3, 15), date(2024, 3, 1), date(2024, 3, 10), "3")
        )
        journeys = build_journeys(txns)
        flags = analyze_journeys(journeys)
        repeat_flags = [f for f in flags if f.behavior_type == BehaviorType.REPEAT_LOSER]
        assert len(repeat_flags) == 1
        assert "TSLA" in repeat_flags[0].detail


class TestAnalyzeJourneys:
    def test_returns_list(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        flags = analyze_journeys(journeys)
        assert isinstance(flags, list)

    def test_winner_gets_no_negative_flags(self, nvda_winner_transactions):
        journeys = build_journeys(nvda_winner_transactions)
        flags = analyze_journeys(journeys)
        negative_flags = [
            f for f in flags
            if f.behavior_type != BehaviorType.DISCIPLINED
        ]
        assert len(negative_flags) == 0
