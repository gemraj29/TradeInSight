"""Options description normalizer.

Parses Fidelity's verbose option security descriptions into structured fields.

Example inputs:
  "TESLA INC 01/19/2024 250.00 C"
  "NVIDIA CORP 02/16/2024 550.00 C"
  "SPDR S&P 500 ETF TRUST 05/31/2024 515.00 C"
  "APPLE INC 04/19/2024 170.00 P"
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, Tuple

from app.domain.models.transaction import OptionDetails, OptionType


# Regex: captures (name, mm/dd/yyyy, strike, C|P)
_OPTION_DESC_RE = re.compile(
    r"^(.+?)\s+(\d{2}/\d{2}/\d{4})\s+([\d.]+)\s+([CP])$",
    re.IGNORECASE,
)

# Fidelity OCC-style option symbol: ROOT + YYMMDD + C/P + 8-digit strike
_OCC_SYMBOL_RE = re.compile(
    r"^([A-Z]{1,6})(\d{6})([CP])(\d{8})$",
    re.IGNORECASE,
)

# Map of description name fragments → ticker (add more as needed)
_UNDERLYING_MAP: dict[str, str] = {
    "TESLA": "TSLA",
    "NVIDIA": "NVDA",
    "APPLE": "AAPL",
    "MICROSOFT": "MSFT",
    "AMAZON": "AMZN",
    "META PLATFORMS": "META",
    "SPDR S&P 500": "SPY",
    "ALPHABET": "GOOGL",
    "BERKSHIRE": "BRK",
    "JPMORGAN": "JPM",
    "ALPHABET CLASS A": "GOOGL",
}


def parse_option_description(
    description: str,
) -> Optional[OptionDetails]:
    """Parse a Fidelity option security description into OptionDetails.

    Args:
        description: Raw security description string from Fidelity CSV.

    Returns:
        OptionDetails if the description matches the options pattern, else None.
    """
    if not description:
        return None

    desc = description.strip()
    m = _OPTION_DESC_RE.match(desc)
    if not m:
        return None

    company_name = m.group(1).strip().upper()
    expiry_str = m.group(2)
    strike_str = m.group(3)
    opt_char = m.group(4).upper()

    try:
        expiry = datetime.strptime(expiry_str, "%m/%d/%Y").date()
        strike = float(strike_str)
    except ValueError:
        return None

    opt_type = OptionType.CALL if opt_char == "C" else OptionType.PUT
    underlying = _infer_underlying(company_name)

    return OptionDetails(
        underlying=underlying,
        option_type=opt_type,
        strike=strike,
        expiry=expiry,
    )


def parse_occ_symbol(symbol: str) -> Optional[OptionDetails]:
    """Parse a standard OCC option symbol (e.g. TSLA240119C00250000).

    Args:
        symbol: OCC-format option ticker.

    Returns:
        OptionDetails if parseable, else None.
    """
    m = _OCC_SYMBOL_RE.match(symbol.strip().upper())
    if not m:
        return None

    underlying = m.group(1)
    date_str = m.group(2)  # YYMMDD
    opt_char = m.group(3)
    strike_raw = m.group(4)  # 8 digits, last 3 are decimal

    try:
        expiry = datetime.strptime(date_str, "%y%m%d").date()
        strike = int(strike_raw) / 1000.0
    except ValueError:
        return None

    opt_type = OptionType.CALL if opt_char == "C" else OptionType.PUT

    return OptionDetails(
        underlying=underlying,
        option_type=opt_type,
        strike=strike,
        expiry=expiry,
    )


def extract_underlying_from_symbol(symbol: str) -> str:
    """Return the root ticker from an OCC symbol or a plain ticker.

    Args:
        symbol: OCC option symbol or plain stock ticker.

    Returns:
        Root underlying ticker string.
    """
    m = _OCC_SYMBOL_RE.match(symbol.strip().upper())
    if m:
        return m.group(1)
    # Fallback: strip digits and special chars from the end
    root = re.sub(r"[\d/]+.*$", "", symbol.strip().upper()).strip()
    return root if root else symbol.strip().upper()


def compute_dte(expiry: date, as_of: date) -> int:
    """Return days to expiry (can be negative if already expired).

    Args:
        expiry: Option expiry date.
        as_of: Reference date (typically the transaction run_date).

    Returns:
        Integer days remaining.
    """
    return (expiry - as_of).days


def _infer_underlying(company_name: str) -> str:
    """Map a company name fragment to a ticker symbol.

    Args:
        company_name: Uppercased company name from description.

    Returns:
        Best-match ticker or the first word of the company name as fallback.
    """
    for fragment, ticker in _UNDERLYING_MAP.items():
        if fragment in company_name:
            return ticker
    # Last-resort fallback: first word
    return company_name.split()[0] if company_name else "UNKNOWN"
