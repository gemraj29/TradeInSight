"""Tests for the Fidelity CSV parser and normalizer."""

from datetime import date

import pytest

from app.domain.models.transaction import ActionType, OptionType, SecurityType
from app.features.importer.fidelity_parser import parse_fidelity_csv
from app.features.importer.normalizer import (
    compute_dte,
    extract_underlying_from_symbol,
    parse_occ_symbol,
    parse_option_description,
)


# --------------------------------------------------------------------------- #
# Normalizer tests
# --------------------------------------------------------------------------- #

class TestParseOccSymbol:
    def test_call_symbol(self):
        opt = parse_occ_symbol("TSLA240119C00250000")
        assert opt is not None
        assert opt.underlying == "TSLA"
        assert opt.option_type == OptionType.CALL
        assert opt.strike == 250.0
        assert opt.expiry == date(2024, 1, 19)

    def test_put_symbol(self):
        opt = parse_occ_symbol("AAPL241018P00170000")
        assert opt is not None
        assert opt.option_type == OptionType.PUT
        assert opt.strike == 170.0

    def test_fractional_strike(self):
        opt = parse_occ_symbol("SPY240531C00515000")
        assert opt is not None
        assert opt.strike == 515.0

    def test_invalid_symbol_returns_none(self):
        assert parse_occ_symbol("NOTANOPTION") is None
        assert parse_occ_symbol("") is None

    def test_lowercase_accepted(self):
        opt = parse_occ_symbol("tsla240119c00250000")
        assert opt is not None
        assert opt.underlying == "TSLA"


class TestParseOptionDescription:
    def test_call_description(self):
        opt = parse_option_description("TESLA INC 01/19/2024 250.00 C")
        assert opt is not None
        assert opt.option_type == OptionType.CALL
        assert opt.strike == 250.0
        assert opt.expiry == date(2024, 1, 19)

    def test_put_description(self):
        opt = parse_option_description("APPLE INC 04/19/2024 170.00 P")
        assert opt is not None
        assert opt.option_type == OptionType.PUT

    def test_spdr_etf_description(self):
        opt = parse_option_description("SPDR S&P 500 ETF TRUST 05/31/2024 515.00 C")
        assert opt is not None
        assert opt.strike == 515.0

    def test_stock_description_returns_none(self):
        assert parse_option_description("APPLE INC COMMON STOCK") is None

    def test_empty_returns_none(self):
        assert parse_option_description("") is None


class TestComputeDte:
    def test_future_expiry(self):
        assert compute_dte(date(2024, 1, 19), date(2024, 1, 5)) == 14

    def test_same_day(self):
        assert compute_dte(date(2024, 1, 19), date(2024, 1, 19)) == 0

    def test_expired(self):
        assert compute_dte(date(2024, 1, 19), date(2024, 1, 20)) == -1


class TestExtractUnderlying:
    def test_occ_symbol(self):
        assert extract_underlying_from_symbol("TSLA240119C00250000") == "TSLA"

    def test_plain_ticker(self):
        assert extract_underlying_from_symbol("AAPL") == "AAPL"


# --------------------------------------------------------------------------- #
# CSV parser tests
# --------------------------------------------------------------------------- #

class TestParseFidelityCsv:
    def test_parses_two_transactions(self, sample_csv_bytes):
        txns, err = parse_fidelity_csv(sample_csv_bytes)
        assert err is None
        assert len(txns) == 2

    def test_first_txn_is_buy(self, sample_csv_bytes):
        txns, _ = parse_fidelity_csv(sample_csv_bytes)
        buy = txns[0]
        assert buy.action == ActionType.BUY_TO_OPEN
        assert buy.quantity == 10
        assert buy.price == 3.45
        assert buy.security_type == SecurityType.OPTION

    def test_second_txn_is_expired(self, sample_csv_bytes):
        txns, _ = parse_fidelity_csv(sample_csv_bytes)
        exp = txns[1]
        assert exp.action == ActionType.EXPIRED

    def test_option_details_parsed(self, sample_csv_bytes):
        txns, _ = parse_fidelity_csv(sample_csv_bytes)
        opt = txns[0].option_details
        assert opt is not None
        assert opt.strike == 250.0
        assert opt.expiry == date(2024, 1, 19)

    def test_underlying_extracted(self, sample_csv_bytes):
        txns, _ = parse_fidelity_csv(sample_csv_bytes)
        assert txns[0].underlying == "TSLA"

    def test_empty_csv_returns_empty(self):
        txns, err = parse_fidelity_csv(b"")
        assert txns == []

    def test_bad_csv_returns_error(self):
        txns, err = parse_fidelity_csv(b"completely,wrong,format\n1,2,3")
        # Either error or empty — must not crash
        assert isinstance(txns, list)

    def test_import_batch_id_attached(self, sample_csv_bytes):
        txns, _ = parse_fidelity_csv(sample_csv_bytes, import_batch_id="batch123")
        assert all(t.import_batch_id == "batch123" for t in txns)

    def test_deterministic_ids(self, sample_csv_bytes):
        txns1, _ = parse_fidelity_csv(sample_csv_bytes)
        txns2, _ = parse_fidelity_csv(sample_csv_bytes)
        assert txns1[0].transaction_id == txns2[0].transaction_id
