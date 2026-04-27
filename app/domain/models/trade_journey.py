"""Domain model for a complete trade journey.

A TradeJourney groups all transactions for a single option series
(same underlying + expiry + strike + type) across its lifetime.
Pure dataclass — zero framework imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional

from app.domain.models.transaction import OptionDetails, Transaction


class JourneyStatus(str, Enum):
    """Current lifecycle state of the journey."""
    OPEN = "open"
    CLOSED = "closed"
    EXPIRED = "expired"
    PARTIAL = "partial"


class JourneyOutcome(str, Enum):
    """Final P&L outcome."""
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"
    OPEN = "open"


@dataclass
class TradeJourney:
    """A complete trade journey from first entry to final exit or expiry.

    Attributes:
        journey_id: Unique identifier (underlying + expiry + strike + type).
        underlying: Root ticker symbol.
        symbol: Full option contract symbol used as primary key.
        option_details: Parsed option attributes.
        transactions: Ordered list of all related transactions.
        status: open | closed | expired | partial.
        outcome: win | loss | breakeven | open.
        entry_date: Date of first buy/sell-to-open.
        exit_date: Date of final close/expiry.
        total_contracts_opened: Sum of all opening quantities.
        total_contracts_closed: Sum of all closing quantities.
        total_cost_basis: Total cash paid to open all positions (negative = debit).
        total_proceeds: Total cash received from closes/sales (positive = credit).
        realized_pnl: Net profit or loss (proceeds + cost_basis).
        num_adds: Number of times the position was added to after initial entry.
        was_rolled: True if a close+reopen in a further expiry was detected.
        roll_count: Number of rolls detected.
        held_near_expiry: True if the final close was within near_expiry_dte days.
        dte_at_first_entry: DTE when the first contract was bought.
        max_position_size: Maximum number of contracts held at one time.
        manual_tag: User-assigned tag (FOMO, averaged_down, disciplined, etc.).
        notes: User notes.
        behavior_flags: List of flag names detected by the behavior analyzer.
    """

    journey_id: str
    underlying: str
    symbol: str
    option_details: Optional[OptionDetails]
    transactions: List[Transaction] = field(default_factory=list)
    status: JourneyStatus = JourneyStatus.OPEN
    outcome: JourneyOutcome = JourneyOutcome.OPEN
    entry_date: Optional[date] = None
    exit_date: Optional[date] = None
    total_contracts_opened: float = 0.0
    total_contracts_closed: float = 0.0
    total_cost_basis: float = 0.0
    total_proceeds: float = 0.0
    realized_pnl: float = 0.0
    num_adds: int = 0
    was_rolled: bool = False
    roll_count: int = 0
    held_near_expiry: bool = False
    dte_at_first_entry: Optional[int] = None
    max_position_size: float = 0.0
    manual_tag: Optional[str] = None
    notes: Optional[str] = None
    behavior_flags: List[str] = field(default_factory=list)

    @property
    def is_winner(self) -> bool:
        """Return True if the journey closed with a profit."""
        return self.realized_pnl > 0

    @property
    def is_loser(self) -> bool:
        """Return True if the journey closed at a loss."""
        return self.realized_pnl < 0

    @property
    def duration_days(self) -> Optional[int]:
        """Return calendar days from entry to exit."""
        if self.entry_date and self.exit_date:
            return (self.exit_date - self.entry_date).days
        return None

    @property
    def avg_entry_price(self) -> float:
        """Average price paid per contract across all opening transactions."""
        if self.total_contracts_opened == 0:
            return 0.0
        opening_cost = sum(
            abs(t.net_amount)
            for t in self.transactions
            if t.is_opening and t.quantity > 0
        )
        return opening_cost / self.total_contracts_opened if self.total_contracts_opened else 0.0
