"""Tests for the Trade Journey Engine."""

from datetime import date

import pytest

from app.domain.models.trade_journey import JourneyOutcome, JourneyStatus
from app.domain.models.transaction import ActionType, OptionType
from app.features.journey_engine.grouper import build_journeys
from tests.conftest import _make_txn


class TestBuildJourneys:
    def test_single_symbol_becomes_one_journey(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        tsla_journeys = [j for j in journeys if j.underlying == "TSLA"]
        assert len(tsla_journeys) == 1

    def test_expired_journey_has_correct_status(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        j = journeys[0]
        assert j.status == JourneyStatus.EXPIRED

    def test_expired_journey_is_a_loss(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        j = journeys[0]
        assert j.outcome == JourneyOutcome.LOSS
        assert j.realized_pnl < 0

    def test_total_cost_basis_correct(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        j = journeys[0]
        expected_cost = -3460.75 + -1053.38 + -678.38
        assert abs(j.total_cost_basis - expected_cost) < 1.0

    def test_num_adds_counted(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        j = journeys[0]
        assert j.num_adds == 2  # 2 additional buys after the initial

    def test_winner_journey(self, nvda_winner_transactions):
        journeys = build_journeys(nvda_winner_transactions)
        j = journeys[0]
        assert j.outcome == JourneyOutcome.WIN
        assert j.realized_pnl > 0

    def test_entry_date_set(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        j = journeys[0]
        assert j.entry_date == date(2024, 1, 5)

    def test_exit_date_set(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        j = journeys[0]
        assert j.exit_date == date(2024, 1, 19)

    def test_multiple_symbols_separate_journeys(self):
        sym_a = "TSLA240119C00250000"
        sym_b = "NVDA240216C00550000"
        expiry_a = date(2024, 1, 19)
        expiry_b = date(2024, 2, 16)
        txns = [
            _make_txn("a1", date(2024, 1, 5),  sym_a, "TSLA", ActionType.BUY_TO_OPEN,  10, 3.45, -3460.75, strike=250.0, expiry=expiry_a),
            _make_txn("a2", date(2024, 1, 19), sym_a, "TSLA", ActionType.EXPIRED,      -10, 0.0,   0.0,     strike=250.0, expiry=expiry_a),
            _make_txn("b1", date(2024, 2, 1),  sym_b, "NVDA", ActionType.BUY_TO_OPEN,  5,  8.20, -4126.38, strike=550.0, expiry=expiry_b),
            _make_txn("b2", date(2024, 2, 14), sym_b, "NVDA", ActionType.SELL_TO_CLOSE,-5,  2.15,  2139.25, strike=550.0, expiry=expiry_b),
        ]
        journeys = build_journeys(txns)
        assert len(journeys) == 2

    def test_max_position_size_tracked(self, tsla_avg_down_transactions):
        journeys = build_journeys(tsla_avg_down_transactions)
        j = journeys[0]
        assert j.max_position_size == 20.0  # 10 + 5 + 5

    def test_roll_detection(self):
        """A close + new open on same underlying different expiry = roll."""
        sym1 = "NVDA240315C00600000"
        sym2 = "NVDA240315C00650000"
        expiry1 = date(2024, 3, 15)
        expiry2 = date(2024, 3, 15)
        sym3 = "NVDA240419C00650000"
        expiry3 = date(2024, 4, 19)

        txns = [
            _make_txn("r1", date(2024, 2, 20), sym1, "NVDA", ActionType.BUY_TO_OPEN,   8, 6.50, -5204.60, strike=600.0, expiry=expiry1),
            _make_txn("r2", date(2024, 3, 5),  sym1, "NVDA", ActionType.SELL_TO_CLOSE, -8, 1.80, -1444.60, strike=600.0, expiry=expiry1),
            _make_txn("r3", date(2024, 3, 6),  sym3, "NVDA", ActionType.BUY_TO_OPEN,   8, 3.10,  2467.40, strike=650.0, expiry=expiry3),
        ]
        journeys = build_journeys(txns)
        rolled = [j for j in journeys if j.was_rolled]
        assert len(rolled) >= 1
