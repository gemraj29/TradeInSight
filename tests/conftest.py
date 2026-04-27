"""Shared pytest fixtures for TradeInSight tests."""

import pytest
from datetime import date
from app.domain.models.transaction import (
    ActionType, OptionDetails, OptionType, SecurityType, Transaction,
)
from app.domain.models.trade_journey import TradeJourney, JourneyStatus, JourneyOutcome


def _make_txn(
    txn_id: str,
    run_date: date,
    symbol: str,
    underlying: str,
    action: ActionType,
    quantity: float,
    price: float,
    net_amount: float,
    opt_type: OptionType = OptionType.CALL,
    strike: float = 250.0,
    expiry: date = date(2024, 1, 19),
    raw_action: str = "",
) -> Transaction:
    opt = OptionDetails(
        underlying=underlying,
        option_type=opt_type,
        strike=strike,
        expiry=expiry,
        dte_at_entry=(expiry - run_date).days,
    )
    return Transaction(
        transaction_id=txn_id,
        run_date=run_date,
        account="Z99999999",
        action=action,
        symbol=symbol,
        underlying=underlying,
        description=f"{underlying} {expiry} {strike} {opt_type.value[0].upper()}",
        security_type=SecurityType.OPTION,
        quantity=quantity,
        price=price,
        commission=0.65,
        fees=0.10,
        net_amount=net_amount,
        settlement_date=None,
        option_details=opt,
        raw_action=raw_action or action.value,
    )


@pytest.fixture
def tsla_avg_down_transactions():
    """TSLA call: 3 buys averaging down, expires worthless."""
    sym = "TSLA240119C00250000"
    expiry = date(2024, 1, 19)
    return [
        _make_txn("t1", date(2024, 1, 5),  sym, "TSLA", ActionType.BUY_TO_OPEN, 10, 3.45, -3460.75, strike=250.0, expiry=expiry),
        _make_txn("t2", date(2024, 1, 12), sym, "TSLA", ActionType.BUY_TO_OPEN, 5,  2.10, -1053.38, strike=250.0, expiry=expiry),
        _make_txn("t3", date(2024, 1, 15), sym, "TSLA", ActionType.BUY_TO_OPEN, 5,  1.35, -678.38,  strike=250.0, expiry=expiry),
        _make_txn("t4", date(2024, 1, 19), sym, "TSLA", ActionType.EXPIRED,     -20, 0.0,  0.0,      strike=250.0, expiry=expiry),
    ]


@pytest.fixture
def nvda_winner_transactions():
    """NVDA call: single entry, profitable exit."""
    sym = "NVDA240920C00115000"
    expiry = date(2024, 9, 20)
    return [
        _make_txn("n1", date(2024, 8, 15), sym, "NVDA", ActionType.BUY_TO_OPEN,  15, 3.80, -5713.13, strike=115.0, expiry=expiry),
        _make_txn("n2", date(2024, 9, 10), sym, "NVDA", ActionType.SELL_TO_CLOSE, -25, 5.20, 12988.12, strike=115.0, expiry=expiry),
    ]


@pytest.fixture
def sample_csv_bytes():
    """Minimal valid Fidelity CSV bytes for parser tests."""
    content = (
        "Run Date,Account,Action,Symbol,Security Description,Security Type,"
        "Quantity,Price ($),Commission ($),Fees ($),Accrued Interest ($),Amount ($),Settlement Date\n"
        "01/05/2024,Z12345678,YOU BOUGHT,TSLA240119C00250000,"
        "TESLA INC 01/19/2024 250.00 C,Options,10,3.45,0.65,0.10,,\"-3460.75\",01/08/2024\n"
        "01/19/2024,Z12345678,EXPIRED,TSLA240119C00250000,"
        "TESLA INC 01/19/2024 250.00 C,Options,-10,0.00,0.00,0.00,,0.00,01/22/2024\n"
    )
    return content.encode("utf-8")
