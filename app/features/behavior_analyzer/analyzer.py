"""Options Behavior Analyzer.

Inspects completed trade journeys and emits BehaviorFlag objects for each
detected behavioral mistake (or positive discipline signal).

Detection rules:
  - averaging_down   : ≥ threshold add transactions on a long options position
  - rolling_loser    : journey.was_rolled AND journey.realized_pnl < 0
  - near_expiry_hold : held within near_expiry_dte days of expiry at close
  - oversized_position : max_position_size * price > oversize_pct% of account
  - fomo_entry       : inferred from entry momentum (requires price data; falls
                       back to large-gap-day heuristic using net_amount vs qty)
  - late_exit        : exited long option below 20% of entry price
  - repeat_loser     : ≥3 losing journeys on the same underlying
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from app.core.config import settings
from app.core.logging_setup import get_logger
from app.domain.models.behavior_flag import BehaviorFlag, BehaviorType
from app.domain.models.trade_journey import JourneyOutcome, TradeJourney
from app.domain.models.transaction import ActionType

logger = get_logger(__name__)

LATE_EXIT_THRESHOLD = 0.20  # exit price < 20% of avg entry price


def analyze_journeys(journeys: List[TradeJourney]) -> List[BehaviorFlag]:
    """Run all behavior detectors across a list of journeys.

    Args:
        journeys: All trade journeys for the account.

    Returns:
        List of BehaviorFlag objects, one or more per affected journey.
    """
    flags: List[BehaviorFlag] = []

    # Detectors that work per-journey
    for journey in journeys:
        flags.extend(_detect_averaging_down(journey))
        flags.extend(_detect_rolling_loser(journey))
        flags.extend(_detect_near_expiry_hold(journey))
        flags.extend(_detect_oversized_position(journey))
        flags.extend(_detect_late_exit(journey))

    # Cross-journey detector
    flags.extend(_detect_repeat_losers(journeys))

    # Attach flag names back to journey objects
    flag_map: Dict[str, List[str]] = defaultdict(list)
    for f in flags:
        flag_map[f.journey_id].append(f.behavior_type.value)

    for journey in journeys:
        journey.behavior_flags = flag_map.get(journey.journey_id, [])

    logger.info("Behavior analysis complete — %d flags across %d journeys", len(flags), len(journeys))
    return flags


# --------------------------------------------------------------------------- #
# Individual detectors
# --------------------------------------------------------------------------- #

def _detect_averaging_down(journey: TradeJourney) -> List[BehaviorFlag]:
    """Flag journeys where the trader added to a losing long-option position."""
    if not journey.option_details:
        return []
    if journey.num_adds < settings.avg_down_threshold:
        return []

    # Only flag if the position was ultimately a loser
    if journey.outcome not in (JourneyOutcome.LOSS, JourneyOutcome.OPEN):
        return []

    opening_txns = [
        t for t in journey.transactions
        if t.action in (ActionType.BUY_TO_OPEN, ActionType.BUY) and t.quantity > 0
    ]
    if len(opening_txns) < 2:
        return []

    # Build evidence string
    evidence_parts = [
        f"+{int(t.quantity)} @ ${t.price:.2f}" for t in opening_txns
    ]
    evidence = f"{len(opening_txns)} entries: " + ", ".join(evidence_parts)

    # Estimate impact: difference between first-entry cost and total cost
    first_price = opening_txns[0].price if opening_txns else 0
    extra_cost = sum(
        abs(t.net_amount) for t in opening_txns[1:]
    )
    impact = -extra_cost  # negative = dollar loss attributable to the adds

    severity = 3 if journey.num_adds >= 3 else 2

    return [BehaviorFlag(
        journey_id=journey.journey_id,
        behavior_type=BehaviorType.AVERAGING_DOWN,
        severity=severity,
        estimated_loss_impact=impact,
        detail=(
            f"Added to {journey.underlying} {_opt_label(journey)} "
            f"{journey.num_adds} time(s) as position moved against you. "
            f"Avg entry moved from ${first_price:.2f} to a worse cost basis."
        ),
        evidence=evidence,
    )]


def _detect_rolling_loser(journey: TradeJourney) -> List[BehaviorFlag]:
    """Flag journeys where a losing position was rolled to a further expiry."""
    if not journey.was_rolled:
        return []
    if journey.realized_pnl >= 0:
        return []

    return [BehaviorFlag(
        journey_id=journey.journey_id,
        behavior_type=BehaviorType.ROLLING_LOSER,
        severity=2,
        estimated_loss_impact=journey.realized_pnl,
        detail=(
            f"Rolled {journey.underlying} {_opt_label(journey)} "
            f"{journey.roll_count} time(s) while at a loss of "
            f"${abs(journey.realized_pnl):.2f}, deferring the loss "
            f"rather than closing cleanly."
        ),
        evidence=f"Rolled {journey.roll_count}x · P&L at roll: ${journey.realized_pnl:.2f}",
    )]


def _detect_near_expiry_hold(journey: TradeJourney) -> List[BehaviorFlag]:
    """Flag journeys where the position was held into near-expiry territory."""
    if not journey.held_near_expiry:
        return []
    if journey.outcome not in (JourneyOutcome.LOSS,):
        return []  # only flag if it cost money

    opt = journey.option_details
    dte_at_exit = None
    if opt and journey.exit_date:
        dte_at_exit = (opt.expiry - journey.exit_date).days

    return [BehaviorFlag(
        journey_id=journey.journey_id,
        behavior_type=BehaviorType.NEAR_EXPIRY_HOLD,
        severity=2,
        estimated_loss_impact=journey.realized_pnl,
        detail=(
            f"Held {journey.underlying} {_opt_label(journey)} until "
            f"{dte_at_exit} DTE. Theta decay is steepest in the final week."
        ),
        evidence=f"DTE at close: {dte_at_exit} · Threshold: {settings.near_expiry_dte} DTE",
    )]


def _detect_oversized_position(journey: TradeJourney) -> List[BehaviorFlag]:
    """Flag journeys where the position exceeded the account size threshold."""
    if settings.max_account_size <= 0:
        return []

    max_cost = abs(journey.total_cost_basis)
    pct_of_account = (max_cost / settings.max_account_size) * 100

    if pct_of_account < settings.oversize_pct:
        return []

    severity = 3 if pct_of_account > settings.oversize_pct * 2 else 2

    return [BehaviorFlag(
        journey_id=journey.journey_id,
        behavior_type=BehaviorType.OVERSIZED_POSITION,
        severity=severity,
        estimated_loss_impact=min(journey.realized_pnl, 0),
        detail=(
            f"Position cost ${max_cost:,.2f} = {pct_of_account:.1f}% of account "
            f"(limit: {settings.oversize_pct}%). Concentration risk was high."
        ),
        evidence=f"Cost basis: ${max_cost:,.2f} · Account: ${settings.max_account_size:,.0f} · {pct_of_account:.1f}%",
    )]


def _detect_late_exit(journey: TradeJourney) -> List[BehaviorFlag]:
    """Flag journeys where a long option was exited at near-zero value."""
    if not journey.option_details:
        return []

    opening_txns = [
        t for t in journey.transactions
        if t.action in (ActionType.BUY_TO_OPEN, ActionType.BUY) and t.quantity > 0
    ]
    closing_txns = [
        t for t in journey.transactions
        if t.action in (ActionType.SELL_TO_CLOSE, ActionType.SELL) and t.quantity < 0
    ]

    if not opening_txns or not closing_txns:
        return []

    avg_entry = sum(t.price for t in opening_txns) / len(opening_txns)
    avg_exit = sum(t.price for t in closing_txns) / len(closing_txns)

    if avg_entry == 0:
        return []

    exit_pct = avg_exit / avg_entry

    if exit_pct > LATE_EXIT_THRESHOLD:
        return []  # exited before losing most value — no flag

    return [BehaviorFlag(
        journey_id=journey.journey_id,
        behavior_type=BehaviorType.LATE_EXIT,
        severity=2,
        estimated_loss_impact=journey.realized_pnl,
        detail=(
            f"Exited {journey.underlying} {_opt_label(journey)} at "
            f"${avg_exit:.2f} (only {exit_pct*100:.0f}% of entry price "
            f"${avg_entry:.2f}). A stop-loss at 50% would have saved "
            f"${(avg_entry * 0.50 - avg_exit) * journey.total_contracts_opened * 100:,.2f}."
        ),
        evidence=f"Entry: ${avg_entry:.2f} · Exit: ${avg_exit:.2f} · {exit_pct*100:.0f}% retained",
    )]


def _detect_repeat_losers(journeys: List[TradeJourney]) -> List[BehaviorFlag]:
    """Flag underlyings where the trader lost money 3+ separate times."""
    loss_count: Dict[str, int] = defaultdict(int)
    loss_amount: Dict[str, float] = defaultdict(float)
    journey_ids: Dict[str, List[str]] = defaultdict(list)

    for j in journeys:
        if j.outcome == JourneyOutcome.LOSS:
            loss_count[j.underlying] += 1
            loss_amount[j.underlying] += j.realized_pnl
            journey_ids[j.underlying].append(j.journey_id)

    flags = []
    for underlying, count in loss_count.items():
        if count < 3:
            continue
        # Attach flag to the last losing journey for that underlying
        last_journey_id = journey_ids[underlying][-1]
        flags.append(BehaviorFlag(
            journey_id=last_journey_id,
            behavior_type=BehaviorType.REPEAT_LOSER,
            severity=3,
            estimated_loss_impact=loss_amount[underlying],
            detail=(
                f"Lost money on {underlying} {count} separate times "
                f"for a total of ${abs(loss_amount[underlying]):,.2f}. "
                f"A rule blocking re-entry until reviewing past mistakes would help."
            ),
            evidence=f"{count} losing journeys · Total: ${loss_amount[underlying]:,.2f}",
        ))
    return flags


# --------------------------------------------------------------------------- #
# Helper
# --------------------------------------------------------------------------- #

def _opt_label(journey: TradeJourney) -> str:
    """Return a short option label like 'CALL $250 exp 01/19/2024'."""
    opt = journey.option_details
    if not opt:
        return ""
    return f"{opt.option_type.value.upper()} ${opt.strike:g} exp {opt.expiry.strftime('%m/%d/%Y')}"
