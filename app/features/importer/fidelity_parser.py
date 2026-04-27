"""Fidelity CSV statement parser.

Converts a raw Fidelity account activity CSV export into a normalized list
of Transaction domain objects.

Supported Fidelity CSV columns:
    Run Date, Account, Action, Symbol, Security Description, Security Type,
    Quantity, Price ($), Commission ($), Fees ($), Accrued Interest ($),
    Amount ($), Settlement Date
"""

from __future__ import annotations

import hashlib
import io
import re
from datetime import date, datetime
from typing import List, Optional, Tuple

import pandas as pd

from app.core.logging_setup import get_logger
from app.domain.models.transaction import (
    ActionType,
    OptionDetails,
    SecurityType,
    Transaction,
)
from app.features.importer.normalizer import (
    compute_dte,
    extract_underlying_from_symbol,
    parse_occ_symbol,
    parse_option_description,
)

logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
# Column aliases — Fidelity occasionally changes column headers slightly
# --------------------------------------------------------------------------- #
_REQUIRED_COLS = {"Run Date", "Account", "Action", "Symbol", "Security Description"}

_ACTION_MAP: dict[str, ActionType] = {
    "you bought": ActionType.BUY_TO_OPEN,
    "you bought opening": ActionType.BUY_TO_OPEN,
    "you bought closing": ActionType.BUY_TO_CLOSE,
    "you sold": ActionType.SELL_TO_CLOSE,
    "you sold opening": ActionType.SELL_TO_OPEN,
    "you sold closing": ActionType.SELL_TO_CLOSE,
    "expired": ActionType.EXPIRED,
    "assigned": ActionType.ASSIGNED,
    "exercised": ActionType.EXERCISE,
    "you have bought": ActionType.BUY_TO_OPEN,
    "you have sold": ActionType.SELL_TO_CLOSE,
}


def parse_fidelity_csv(
    source: str | bytes | io.IOBase,
    import_batch_id: Optional[str] = None,
) -> Tuple[List[Transaction], Optional[str]]:
    """Parse a Fidelity account activity CSV into Transaction objects.

    Args:
        source: File path string, bytes content, or file-like object.
        import_batch_id: Optional identifier to tag all resulting transactions.

    Returns:
        (list_of_transactions, error_message | None)
        On success, error_message is None.
        On total failure, list is empty and error_message describes the problem.
    """
    try:
        df, err = _load_dataframe(source)
        if err:
            return [], err

        df = _normalize_columns(df)
        err = _validate_columns(df)
        if err:
            return [], err

        transactions: List[Transaction] = []
        skipped = 0

        for _, row in df.iterrows():
            txn, skip_reason = _parse_row(row, import_batch_id)
            if skip_reason:
                logger.debug("Skipped row: %s", skip_reason)
                skipped += 1
                continue
            if txn:
                transactions.append(txn)

        logger.info(
            "Parsed %d transactions, skipped %d rows",
            len(transactions),
            skipped,
        )
        return transactions, None

    except Exception as exc:
        logger.exception("Unexpected error parsing Fidelity CSV")
        return [], f"Unexpected error: {exc}"


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _load_dataframe(source) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load CSV source into a DataFrame, skipping Fidelity header boilerplate."""
    try:
        if isinstance(source, bytes):
            source = io.BytesIO(source)
        df = pd.read_csv(source, skiprows=_detect_header_row(source), thousands=",")
        return df, None
    except Exception as exc:
        return None, f"Could not read CSV: {exc}"


def _detect_header_row(source) -> int:
    """Return the number of rows to skip before the actual header."""
    if isinstance(source, (str,)):
        try:
            with open(source, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()
        except Exception:
            return 0
    elif isinstance(source, io.BytesIO):
        source.seek(0)
        lines = source.read().decode("utf-8-sig").splitlines()
        source.seek(0)
    else:
        return 0

    for i, line in enumerate(lines):
        if "Run Date" in line or "run date" in line.lower():
            return i
    return 0


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from column names."""
    df.columns = [c.strip() for c in df.columns]
    return df


def _validate_columns(df: pd.DataFrame) -> Optional[str]:
    """Return an error string if required columns are missing."""
    missing = _REQUIRED_COLS - set(df.columns)
    if missing:
        return f"Missing required columns: {missing}. Found: {list(df.columns)}"
    return None


def _parse_row(
    row: pd.Series, import_batch_id: Optional[str]
) -> Tuple[Optional[Transaction], Optional[str]]:
    """Parse one CSV row into a Transaction.

    Returns:
        (Transaction, None) on success.
        (None, reason_string) if the row should be skipped.
    """
    # Skip blank / summary rows
    raw_action = str(row.get("Action", "")).strip()
    if not raw_action or raw_action.lower() in ("", "nan", "action"):
        return None, "empty or header row"

    run_date = _parse_date(str(row.get("Run Date", "")))
    if not run_date:
        return None, f"unparseable run_date: {row.get('Run Date')}"

    symbol = str(row.get("Symbol", "")).strip().upper()
    if not symbol or symbol == "NAN":
        return None, "missing symbol"

    description = str(row.get("Security Description", "")).strip()
    security_type_raw = str(row.get("Security Type", "")).strip().lower()
    action = _normalize_action(raw_action)

    quantity = _parse_float(row.get("Quantity", 0))
    price = _parse_float(row.get("Price ($)", 0))
    commission = _parse_float(row.get("Commission ($)", 0))
    fees = _parse_float(row.get("Fees ($)", 0))
    net_amount = _parse_float(row.get("Amount ($)", 0))
    settlement_date = _parse_date(str(row.get("Settlement Date", "")))

    # Determine security type
    if "option" in security_type_raw:
        sec_type = SecurityType.OPTION
    elif "etf" in security_type_raw or any(
        ticker in symbol for ticker in ("SPY", "QQQ", "IWM", "DIA", "EEM")
    ):
        sec_type = SecurityType.ETF
    elif security_type_raw in ("common stock", "stock", "equity", ""):
        sec_type = SecurityType.STOCK
    else:
        sec_type = SecurityType.OTHER

    # Parse option details
    opt_details: Optional[OptionDetails] = None
    underlying = extract_underlying_from_symbol(symbol)

    if sec_type == SecurityType.OPTION:
        opt_details = parse_occ_symbol(symbol)
        if not opt_details:
            opt_details = parse_option_description(description)
        if opt_details:
            underlying = opt_details.underlying
            opt_details.dte_at_entry = compute_dte(opt_details.expiry, run_date)

    # Unique deterministic ID
    txn_id = _make_transaction_id(run_date, symbol, raw_action, quantity, net_amount)

    txn = Transaction(
        transaction_id=txn_id,
        run_date=run_date,
        account=str(row.get("Account", "")).strip(),
        action=action,
        symbol=symbol,
        underlying=underlying,
        description=description,
        security_type=sec_type,
        quantity=quantity,
        price=price,
        commission=commission,
        fees=fees,
        net_amount=net_amount,
        settlement_date=settlement_date,
        option_details=opt_details,
        import_batch_id=import_batch_id,
        raw_action=raw_action,
    )
    return txn, None


def _normalize_action(raw: str) -> ActionType:
    """Map a raw Fidelity action string to an ActionType enum."""
    key = raw.strip().lower()
    for pattern, action_type in _ACTION_MAP.items():
        if key == pattern or key.startswith(pattern):
            return action_type
    if "buy" in key or "bought" in key:
        return ActionType.BUY
    if "sell" in key or "sold" in key:
        return ActionType.SELL
    if "expir" in key:
        return ActionType.EXPIRED
    return ActionType.OTHER


def _parse_date(value: str) -> Optional[date]:
    """Parse date strings in MM/DD/YYYY or YYYY-MM-DD format."""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _parse_float(value) -> float:
    """Safely parse a numeric value, stripping commas and dollar signs."""
    if pd.isna(value):
        return 0.0
    s = str(value).replace(",", "").replace("$", "").replace("(", "-").replace(")", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _make_transaction_id(
    run_date: date,
    symbol: str,
    action: str,
    quantity: float,
    net_amount: float,
) -> str:
    """Generate a deterministic ID from key transaction fields."""
    key = f"{run_date}|{symbol}|{action}|{quantity}|{net_amount}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]
