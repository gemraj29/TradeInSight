"""Trade Journey Engine — groups transactions into complete trade journeys.

A journey encompasses all transactions for the same option series:
initial entry → position adds → partial exits → rolls → final close or expiry.

Roll detection: a "close" followed within 5 days by a new open on the same
underlying but different expiry is classified as a roll.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging_setup import get_logger
from app.domain.models.trade_journey import (
    JourneyOutcome,
    JourneyStatus,
    TradeJourney,
)
from app.domain.models.transaction import ActionType, SecurityType, Transaction

logger = get_logger(__name__)

ROLL_WINDOW_DAYS = 5  # closes within this window followed by new open = roll


def build_journeys(transactions: List[Transaction]) -> List[TradeJourney]:
    """Group a list of transactions into complete trade journeys.

    Args:
        transactions: All transactions for a single account, in any order.

    Returns:
        List of TradeJourney objects, one per unique option series traded.
    """
    options_txns = [t for t in transactions if t.is_option]
    stock_txns = [t for t in transactions if not t.is_option]

    journeys: List[TradeJourney] = []
    journeys.extend(_group_option_journeys(options_txns))
    journeys.extend(_group_stock_journeys(stock_txns))

    logger.info("Built %d trade journeys from %d transactions", len(journeys), len(transactions))
    return journeys


# --------------------------------------------------------------------------- #
# Options journeys
# --------------------------------------------------------------------------- #

def _group_option_journeys(transactions: List[Transaction]) -> List[TradeJourney]:
    """Group options transactions by symbol (exact series = underlying+expiry+strike+type)."""
    by_symbol: Dict[str, List[Transaction]] = defaultdict(list)
    for t in transactions:
        by_symbol[t.symbol].append(t)

    journeys = []
    for symbol, txns in by_symbol.items():
        txns_sorted = sorted(txns, key=lambda t: t.run_date)
        journey = _build_option_journey(symbol, txns_sorted)
        journeys.append(journey)

    # Detect rolls: link journeys that are rolls of each other
    _detect_rolls(journeys)

    return journeys


def _build_option_journey(symbol: str, txns: List[Transaction]) -> TradeJourney:
    """Construct a TradeJourney from a list of same-symbol transactions."""
    opt = txns[0].option_details if txns else None
    underlying = txns[0].underlying if txns else symbol

    journey_id = _make_journey_id(symbol)
    journey = TradeJourney(
        journey_id=journey_id,
        underlying=underlying,
        symbol=symbol,
        option_details=opt,
        transactions=txns,
    )

    total_opened = 0.0
    total_closed = 0.0
    total_cost = 0.0
    total_proceeds = 0.0
    add_count = 0
    open_entries = 0  # number of opening transactions
    running_position = 0.0
    max_position = 0.0

    for i, txn in enumerate(txns):
        qty = txn.quantity

        if txn.action in (ActionType.BUY_TO_OPEN, ActionType.BUY):
            if i == 0:
                journey.entry_date = txn.run_date
                if opt:
                    journey.dte_at_first_entry = opt.dte_at_entry
            else:
                add_count += 1
            total_opened += qty
            total_cost += txn.net_amount  # negative (cash out)
            running_position += qty
            open_entries += 1

        elif txn.action in (ActionType.SELL_TO_OPEN,):
            if i == 0:
                journey.entry_date = txn.run_date
            total_opened += abs(qty)
            total_proceeds += txn.net_amount  # positive (cash in)
            running_position += abs(qty)
            open_entries += 1

        elif txn.action in (
            ActionType.SELL_TO_CLOSE,
            ActionType.SELL,
            ActionType.BUY_TO_CLOSE,
        ):
            total_closed += abs(qty)
            total_proceeds += txn.net_amount
            running_position -= abs(qty)
            journey.exit_date = txn.run_date

        elif txn.action in (ActionType.EXPIRED,):
            total_closed += abs(qty) if qty < 0 else total_opened - total_closed
            journey.exit_date = txn.run_date
            journey.status = JourneyStatus.EXPIRED

        elif txn.action in (ActionType.ASSIGNED, ActionType.EXERCISE):
            total_closed += abs(qty)
            journey.exit_date = txn.run_date

        max_position = max(max_position, running_position)

    journey.total_contracts_opened = total_opened
    journey.total_contracts_closed = total_closed
    journey.total_cost_basis = total_cost
    journey.total_proceeds = total_proceeds
    journey.realized_pnl = total_cost + total_proceeds
    journey.num_adds = add_count
    journey.max_position_size = max_position

    # Near-expiry check
    if opt and journey.exit_date:
        dte_at_exit = (opt.expiry - journey.exit_date).days
        journey.held_near_expiry = dte_at_exit <= settings.near_expiry_dte

    # Status
    if journey.status != JourneyStatus.EXPIRED:
        remaining = total_opened - total_closed
        if remaining <= 0:
            journey.status = JourneyStatus.CLOSED
        elif remaining > 0 and total_closed > 0:
            journey.status = JourneyStatus.PARTIAL
        else:
            journey.status = JourneyStatus.OPEN

    # Outcome
    if journey.status in (JourneyStatus.CLOSED, JourneyStatus.EXPIRED):
        if journey.realized_pnl > 1:
            journey.outcome = JourneyOutcome.WIN
        elif journey.realized_pnl < -1:
            journey.outcome = JourneyOutcome.LOSS
        else:
            journey.outcome = JourneyOutcome.BREAKEVEN
    else:
        journey.outcome = JourneyOutcome.OPEN

    return journey


def _detect_rolls(journeys: List[TradeJourney]) -> None:
    """Mutate journeys in-place to mark rolled positions.

    A roll is detected when:
    - Journey A closes (or partially closes) on date D
    - Journey B on the same underlying opens within ROLL_WINDOW_DAYS of D
    - Journey B has a later expiry than Journey A
    """
    closed_journeys = [j for j in journeys if j.exit_date and j.status != JourneyStatus.EXPIRED]
    open_journeys = [j for j in journeys if j.entry_date]

    for closed in closed_journeys:
        if not closed.option_details:
            continue
        window_end = closed.exit_date + timedelta(days=ROLL_WINDOW_DAYS)

        for candidate in open_journeys:
            if candidate is closed:
                continue
            if not candidate.option_details or not candidate.entry_date:
                continue
            if candidate.underlying != closed.underlying:
                continue
            if candidate.option_details.option_type != closed.option_details.option_type:
                continue
            if candidate.entry_date > window_end:
                continue
            if candidate.entry_date < closed.exit_date:
                continue
            if candidate.option_details.expiry <= closed.option_details.expiry:
                continue

            # It's a roll
            closed.was_rolled = True
            closed.roll_count = (closed.roll_count or 0) + 1
            candidate.was_rolled = True
            logger.debug(
                "Roll detected: %s → %s",
                closed.symbol,
                candidate.symbol,
            )


# --------------------------------------------------------------------------- #
# Stock journeys (simple grouping by underlying)
# --------------------------------------------------------------------------- #

def _group_stock_journeys(transactions: List[Transaction]) -> List[TradeJourney]:
    """Group stock transactions by underlying ticker into simple journeys."""
    by_underlying: Dict[str, List[Transaction]] = defaultdict(list)
    for t in transactions:
        by_underlying[t.underlying].append(t)

    journeys = []
    for underlying, txns in by_underlying.items():
        txns_sorted = sorted(txns, key=lambda t: t.run_date)
        journey_id = _make_journey_id(f"STOCK_{underlying}")
        journey = TradeJourney(
            journey_id=journey_id,
            underlying=underlying,
            symbol=underlying,
            option_details=None,
            transactions=txns_sorted,
        )
        total_cost = sum(t.net_amount for t in txns_sorted if t.quantity > 0)
        total_proceeds = sum(t.net_amount for t in txns_sorted if t.quantity < 0)
        journey.total_cost_basis = total_cost
        journey.total_proceeds = total_proceeds
        journey.realized_pnl = total_cost + total_proceeds
        journey.entry_date = txns_sorted[0].run_date
        journey.exit_date = txns_sorted[-1].run_date
        journey.status = JourneyStatus.CLOSED
        journey.outcome = (
            JourneyOutcome.WIN if journey.realized_pnl > 1
            else JourneyOutcome.LOSS if journey.realized_pnl < -1
            else JourneyOutcome.BREAKEVEN
        )
        journeys.append(journey)

    return journeys


def _make_journey_id(symbol: str) -> str:
    """Generate a short deterministic journey ID from the symbol."""
    return hashlib.sha1(symbol.encode()).hexdigest()[:16]
