"""Domain model for a single brokerage transaction.

Pure dataclass — zero imports from SQLAlchemy, Streamlit, or Pandas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class SecurityType(str, Enum):
    """Broad category of the security traded."""
    OPTION = "option"
    STOCK = "stock"
    ETF = "etf"
    OTHER = "other"


class OptionType(str, Enum):
    """Call or put."""
    CALL = "call"
    PUT = "put"


class ActionType(str, Enum):
    """Normalized trade action."""
    BUY_TO_OPEN = "buy_to_open"
    BUY_TO_CLOSE = "buy_to_close"
    SELL_TO_OPEN = "sell_to_open"
    SELL_TO_CLOSE = "sell_to_close"
    BUY = "buy"
    SELL = "sell"
    EXPIRED = "expired"
    ASSIGNED = "assigned"
    EXERCISE = "exercise"
    OTHER = "other"


@dataclass
class OptionDetails:
    """Parsed option contract details extracted from the security description."""
    underlying: str
    option_type: OptionType
    strike: float
    expiry: date
    dte_at_entry: Optional[int] = None  # days to expiry when bought/sold


@dataclass
class Transaction:
    """A single normalized transaction from a Fidelity statement.

    Attributes:
        transaction_id: Unique deterministic hash (run_date + symbol + action + qty).
        run_date: Date the transaction was executed.
        account: Fidelity account identifier.
        action: Normalized action type.
        symbol: Full option symbol or stock ticker.
        underlying: Root ticker (e.g. TSLA for TSLA240119C00250000).
        description: Original security description string.
        security_type: Option, stock, ETF, or other.
        quantity: Signed quantity (positive = bought, negative = sold/expired).
        price: Per-share/contract price in dollars.
        commission: Commission charged.
        fees: Other fees.
        net_amount: Net cash effect (negative = cash out, positive = cash in).
        settlement_date: Settlement date.
        option_details: Parsed option attributes if security_type == OPTION.
        import_batch_id: ID of the import session that created this record.
        raw_action: Original action string from the CSV, for audit purposes.
    """

    transaction_id: str
    run_date: date
    account: str
    action: ActionType
    symbol: str
    underlying: str
    description: str
    security_type: SecurityType
    quantity: float
    price: float
    commission: float
    fees: float
    net_amount: float
    settlement_date: Optional[date]
    option_details: Optional[OptionDetails] = None
    import_batch_id: Optional[str] = None
    raw_action: str = ""
    manual_tag: Optional[str] = None
    notes: Optional[str] = None

    @property
    def is_opening(self) -> bool:
        """Return True if this transaction opens a new position."""
        return self.action in (
            ActionType.BUY_TO_OPEN,
            ActionType.SELL_TO_OPEN,
            ActionType.BUY,
        )

    @property
    def is_closing(self) -> bool:
        """Return True if this transaction closes an existing position."""
        return self.action in (
            ActionType.BUY_TO_CLOSE,
            ActionType.SELL_TO_CLOSE,
            ActionType.SELL,
            ActionType.EXPIRED,
            ActionType.ASSIGNED,
            ActionType.EXERCISE,
        )

    @property
    def is_option(self) -> bool:
        """Return True if this is an options transaction."""
        return self.security_type == SecurityType.OPTION
