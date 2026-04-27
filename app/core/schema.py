"""SQLAlchemy ORM table definitions.

Imported by database.init_db() to register models with Base.metadata.
"""

import json
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey,
    Integer, String, Text, func,
)

from app.core.database import Base


class TransactionORM(Base):
    """Persisted transaction record."""
    __tablename__ = "transactions"

    id = Column(String, primary_key=True)
    run_date = Column(Date, nullable=False, index=True)
    account = Column(String, nullable=False)
    action = Column(String, nullable=False)
    raw_action = Column(String, nullable=False, default="")
    symbol = Column(String, nullable=False, index=True)
    underlying = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=False)
    security_type = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False, default=0.0)
    commission = Column(Float, nullable=False, default=0.0)
    fees = Column(Float, nullable=False, default=0.0)
    net_amount = Column(Float, nullable=False)
    settlement_date = Column(Date, nullable=True)

    # Option-specific fields (null for stocks/ETFs)
    opt_underlying = Column(String, nullable=True)
    opt_type = Column(String, nullable=True)
    opt_strike = Column(Float, nullable=True)
    opt_expiry = Column(Date, nullable=True)
    opt_dte_at_entry = Column(Integer, nullable=True)

    journey_id = Column(String, ForeignKey("trade_journeys.id"), nullable=True, index=True)
    import_batch_id = Column(String, nullable=True, index=True)
    manual_tag = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class TradeJourneyORM(Base):
    """Persisted trade journey record."""
    __tablename__ = "trade_journeys"

    id = Column(String, primary_key=True)
    underlying = Column(String, nullable=False, index=True)
    symbol = Column(String, nullable=False)
    opt_type = Column(String, nullable=True)
    opt_strike = Column(Float, nullable=True)
    opt_expiry = Column(Date, nullable=True)
    status = Column(String, nullable=False, default="open")
    outcome = Column(String, nullable=False, default="open")
    entry_date = Column(Date, nullable=True)
    exit_date = Column(Date, nullable=True)
    total_contracts_opened = Column(Float, default=0.0)
    total_contracts_closed = Column(Float, default=0.0)
    total_cost_basis = Column(Float, default=0.0)
    total_proceeds = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    num_adds = Column(Integer, default=0)
    was_rolled = Column(Boolean, default=False)
    roll_count = Column(Integer, default=0)
    held_near_expiry = Column(Boolean, default=False)
    dte_at_first_entry = Column(Integer, nullable=True)
    max_position_size = Column(Float, default=0.0)
    behavior_flags_json = Column(Text, default="[]")
    manual_tag = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def get_behavior_flags(self) -> list:
        """Deserialize behavior flags from JSON column."""
        return json.loads(self.behavior_flags_json or "[]")

    def set_behavior_flags(self, flags: list) -> None:
        """Serialize behavior flags to JSON column."""
        self.behavior_flags_json = json.dumps(flags)


class BehaviorFlagORM(Base):
    """Persisted behavior detection result."""
    __tablename__ = "behavior_flags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    journey_id = Column(String, ForeignKey("trade_journeys.id"), nullable=False, index=True)
    behavior_type = Column(String, nullable=False, index=True)
    severity = Column(Integer, nullable=False)
    estimated_loss_impact = Column(Float, default=0.0)
    detail = Column(Text, default="")
    evidence = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now())


class TradingRuleORM(Base):
    """User-defined trading rule stored in settings."""
    __tablename__ = "trading_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_text = Column(Text, nullable=False)
    category = Column(String, nullable=False, default="general")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class ImportBatchORM(Base):
    """Record of each CSV import session."""
    __tablename__ = "import_batches"

    id = Column(String, primary_key=True)
    filename = Column(String, nullable=False)
    imported_at = Column(DateTime, server_default=func.now())
    transaction_count = Column(Integer, default=0)
    status = Column(String, default="completed")
    notes = Column(Text, nullable=True)
