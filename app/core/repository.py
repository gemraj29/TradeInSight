"""CRUD repository layer — thin wrappers around SQLAlchemy sessions.

All public functions follow the Result tuple pattern:
    (result | None, error_message | None)
"""

from __future__ import annotations

import json
from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.schema import (
    BehaviorFlagORM,
    ImportBatchORM,
    TradeJourneyORM,
    TransactionORM,
    TradingRuleORM,
)
from app.domain.models.behavior_flag import BehaviorFlag
from app.domain.models.trade_journey import TradeJourney, JourneyStatus, JourneyOutcome
from app.domain.models.transaction import (
    ActionType,
    OptionDetails,
    OptionType,
    SecurityType,
    Transaction,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _orm_to_transaction(row: TransactionORM) -> Transaction:
    opt = None
    if row.opt_expiry:
        opt = OptionDetails(
            underlying=row.opt_underlying or row.underlying,
            option_type=OptionType(row.opt_type) if row.opt_type else OptionType.CALL,
            strike=row.opt_strike or 0.0,
            expiry=row.opt_expiry,
            dte_at_entry=row.opt_dte_at_entry,
        )
    return Transaction(
        transaction_id=row.id,
        run_date=row.run_date,
        account=row.account,
        action=ActionType(row.action),
        symbol=row.symbol,
        underlying=row.underlying,
        description=row.description,
        security_type=SecurityType(row.security_type),
        quantity=row.quantity,
        price=row.price,
        commission=row.commission,
        fees=row.fees,
        net_amount=row.net_amount,
        settlement_date=row.settlement_date,
        option_details=opt,
        import_batch_id=row.import_batch_id,
        raw_action=row.raw_action,
        manual_tag=row.manual_tag,
        notes=row.notes,
    )


def _transaction_to_orm(t: Transaction) -> TransactionORM:
    row = TransactionORM(
        id=t.transaction_id,
        run_date=t.run_date,
        account=t.account,
        action=t.action.value,
        raw_action=t.raw_action,
        symbol=t.symbol,
        underlying=t.underlying,
        description=t.description,
        security_type=t.security_type.value,
        quantity=t.quantity,
        price=t.price,
        commission=t.commission,
        fees=t.fees,
        net_amount=t.net_amount,
        settlement_date=t.settlement_date,
        import_batch_id=t.import_batch_id,
        manual_tag=t.manual_tag,
        notes=t.notes,
    )
    if t.option_details:
        row.opt_underlying = t.option_details.underlying
        row.opt_type = t.option_details.option_type.value
        row.opt_strike = t.option_details.strike
        row.opt_expiry = t.option_details.expiry
        row.opt_dte_at_entry = t.option_details.dte_at_entry
    return row


# --------------------------------------------------------------------------- #
# Transaction repository
# --------------------------------------------------------------------------- #

def upsert_transactions(
    session: Session, transactions: List[Transaction]
) -> Tuple[int, Optional[str]]:
    """Insert or update a list of transactions.

    Returns:
        (count_upserted, error_message | None)
    """
    try:
        count = 0
        for t in transactions:
            existing = session.get(TransactionORM, t.transaction_id)
            if existing:
                continue  # skip duplicates — idempotent import
            session.add(_transaction_to_orm(t))
            count += 1
        session.flush()
        return count, None
    except Exception as exc:
        return 0, str(exc)


def fetch_all_transactions(session: Session) -> List[Transaction]:
    """Return all transactions ordered by run_date."""
    rows = session.query(TransactionORM).order_by(TransactionORM.run_date).all()
    return [_orm_to_transaction(r) for r in rows]


def update_transaction_tag(
    session: Session, transaction_id: str, tag: str, notes: str
) -> Optional[str]:
    """Update the manual_tag and notes fields for a transaction."""
    row = session.get(TransactionORM, transaction_id)
    if not row:
        return f"Transaction {transaction_id} not found"
    row.manual_tag = tag
    row.notes = notes
    return None


# --------------------------------------------------------------------------- #
# Trade Journey repository
# --------------------------------------------------------------------------- #

def upsert_journey(session: Session, journey: TradeJourney) -> Optional[str]:
    """Insert or replace a trade journey record."""
    try:
        existing = session.get(TradeJourneyORM, journey.journey_id)
        if existing:
            existing.status = journey.status.value
            existing.outcome = journey.outcome.value
            existing.entry_date = journey.entry_date
            existing.exit_date = journey.exit_date
            existing.total_contracts_opened = journey.total_contracts_opened
            existing.total_contracts_closed = journey.total_contracts_closed
            existing.total_cost_basis = journey.total_cost_basis
            existing.total_proceeds = journey.total_proceeds
            existing.realized_pnl = journey.realized_pnl
            existing.num_adds = journey.num_adds
            existing.was_rolled = journey.was_rolled
            existing.roll_count = journey.roll_count
            existing.held_near_expiry = journey.held_near_expiry
            existing.dte_at_first_entry = journey.dte_at_first_entry
            existing.max_position_size = journey.max_position_size
            existing.behavior_flags_json = json.dumps(journey.behavior_flags)
        else:
            opt = journey.option_details
            row = TradeJourneyORM(
                id=journey.journey_id,
                underlying=journey.underlying,
                symbol=journey.symbol,
                opt_type=opt.option_type.value if opt else None,
                opt_strike=opt.strike if opt else None,
                opt_expiry=opt.expiry if opt else None,
                status=journey.status.value,
                outcome=journey.outcome.value,
                entry_date=journey.entry_date,
                exit_date=journey.exit_date,
                total_contracts_opened=journey.total_contracts_opened,
                total_contracts_closed=journey.total_contracts_closed,
                total_cost_basis=journey.total_cost_basis,
                total_proceeds=journey.total_proceeds,
                realized_pnl=journey.realized_pnl,
                num_adds=journey.num_adds,
                was_rolled=journey.was_rolled,
                roll_count=journey.roll_count,
                held_near_expiry=journey.held_near_expiry,
                dte_at_first_entry=journey.dte_at_first_entry,
                max_position_size=journey.max_position_size,
                behavior_flags_json=json.dumps(journey.behavior_flags),
                manual_tag=journey.manual_tag,
                notes=journey.notes,
            )
            session.add(row)

        # Link transactions to this journey
        session.query(TransactionORM).filter(
            TransactionORM.symbol == journey.symbol
        ).update({"journey_id": journey.journey_id})

        return None
    except Exception as exc:
        return str(exc)


def fetch_all_journeys(session: Session) -> List[dict]:
    """Return all journey rows as dicts for display / analysis."""
    rows = session.query(TradeJourneyORM).order_by(TradeJourneyORM.entry_date).all()
    result = []
    for r in rows:
        result.append({
            "journey_id": r.id,
            "underlying": r.underlying,
            "symbol": r.symbol,
            "opt_type": r.opt_type,
            "opt_strike": r.opt_strike,
            "opt_expiry": r.opt_expiry,
            "status": r.status,
            "outcome": r.outcome,
            "entry_date": r.entry_date,
            "exit_date": r.exit_date,
            "realized_pnl": r.realized_pnl,
            "num_adds": r.num_adds,
            "was_rolled": r.was_rolled,
            "held_near_expiry": r.held_near_expiry,
            "behavior_flags": json.loads(r.behavior_flags_json or "[]"),
            "manual_tag": r.manual_tag,
            "notes": r.notes,
        })
    return result


def update_journey_tag(
    session: Session, journey_id: str, tag: str, notes: str
) -> Optional[str]:
    """Update the manual_tag and notes fields for a journey."""
    row = session.get(TradeJourneyORM, journey_id)
    if not row:
        return f"Journey {journey_id} not found"
    row.manual_tag = tag
    row.notes = notes
    return None


# --------------------------------------------------------------------------- #
# Behavior flag repository
# --------------------------------------------------------------------------- #

def upsert_behavior_flags(
    session: Session, flags: List[BehaviorFlag]
) -> Optional[str]:
    """Replace all behavior flags for the affected journeys."""
    try:
        if not flags:
            return None
        # Flush pending journey inserts so FK constraints pass
        session.flush()
        journey_ids = {f.journey_id for f in flags}
        session.query(BehaviorFlagORM).filter(
            BehaviorFlagORM.journey_id.in_(journey_ids)
        ).delete(synchronize_session="fetch")
        for f in flags:
            session.add(BehaviorFlagORM(
                journey_id=f.journey_id,
                behavior_type=f.behavior_type.value,
                severity=f.severity,
                estimated_loss_impact=f.estimated_loss_impact,
                detail=f.detail,
                evidence=f.evidence,
            ))
        return None
    except Exception as exc:
        return str(exc)


def fetch_behavior_flags(session: Session) -> List[dict]:
    """Return all behavior flags as dicts."""
    rows = session.query(BehaviorFlagORM).all()
    return [
        {
            "journey_id": r.journey_id,
            "behavior_type": r.behavior_type,
            "severity": r.severity,
            "estimated_loss_impact": r.estimated_loss_impact,
            "detail": r.detail,
            "evidence": r.evidence,
        }
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# Trading rules repository
# --------------------------------------------------------------------------- #

def fetch_rules(session: Session) -> List[dict]:
    """Return all active trading rules."""
    rows = session.query(TradingRuleORM).filter(TradingRuleORM.is_active == True).all()
    return [{"id": r.id, "rule_text": r.rule_text, "category": r.category} for r in rows]


def save_rule(session: Session, rule_text: str, category: str = "general") -> Optional[str]:
    """Insert a new trading rule."""
    try:
        session.add(TradingRuleORM(rule_text=rule_text, category=category))
        return None
    except Exception as exc:
        return str(exc)


def delete_rule(session: Session, rule_id: int) -> Optional[str]:
    """Soft-delete a trading rule."""
    row = session.get(TradingRuleORM, rule_id)
    if not row:
        return f"Rule {rule_id} not found"
    row.is_active = False
    return None


# --------------------------------------------------------------------------- #
# Import batch repository
# --------------------------------------------------------------------------- #

def save_import_batch(
    session: Session, batch_id: str, filename: str, count: int
) -> Optional[str]:
    """Record a completed import batch."""
    try:
        session.add(ImportBatchORM(id=batch_id, filename=filename, transaction_count=count))
        return None
    except Exception as exc:
        return str(exc)


def fetch_import_batches(session: Session) -> List[dict]:
    """Return all import batch records."""
    rows = session.query(ImportBatchORM).order_by(ImportBatchORM.imported_at.desc()).all()
    return [
        {"id": r.id, "filename": r.filename, "imported_at": r.imported_at,
         "transaction_count": r.transaction_count, "status": r.status}
        for r in rows
    ]
