"""Streamlit session state manager.

Provides a single place to initialize and access all session-level state,
ensuring consistent keys across all pages.
"""

from __future__ import annotations

import streamlit as st


def init_state() -> None:
    """Initialize all session state keys with default values if not set."""
    defaults = {
        "db_initialized": False,
        "last_import_batch": None,
        "journey_filter_underlying": "All",
        "journey_filter_status": "All",
        "journey_filter_outcome": "All",
        "selected_journey_id": None,
        "rules_dirty": False,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def mark_db_ready() -> None:
    """Mark the database as initialized."""
    st.session_state["db_initialized"] = True


def is_db_ready() -> bool:
    """Return True if the database has been initialized."""
    return st.session_state.get("db_initialized", False)
