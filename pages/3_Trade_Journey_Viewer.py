"""Trade Journey Viewer — browse journeys, see transaction details, add manual tags."""

import pandas as pd
import streamlit as st

from app.core.database import get_session, init_db
from app.core.repository import fetch_all_journeys, fetch_all_transactions, update_journey_tag
from app.ui.components import (
    COLOR_LOSS, COLOR_WIN, COLOR_NEUTRAL, COLOR_WARNING,
    behavior_badge, format_pnl, pnl_color,
)
from app.ui.state import init_state

st.set_page_config(page_title="Trade Journey Viewer | TradeInSight", layout="wide", page_icon="🗺️")
init_db()
init_state()
st.markdown(
    "<style>.stApp{background:#0f172a} h1,h2,h3{color:#e2e8f0!important}</style>",
    unsafe_allow_html=True,
)

st.title("🗺️ Trade Journey Viewer")
st.caption("See every trade from entry to exit — add notes and manual tags")
st.divider()

# --------------------------------------------------------------------------- #
# Load data
# --------------------------------------------------------------------------- #
with get_session() as session:
    journeys = fetch_all_journeys(session)
    transactions = fetch_all_transactions(session)

if not journeys:
    st.info("No journeys yet — import data on the **Import Statements** page.")
    st.stop()

txn_by_symbol: dict = {}
for t in transactions:
    txn_by_symbol.setdefault(t.symbol, []).append(t)

# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #
col1, col2, col3, col4 = st.columns(4)
underlyings = ["All"] + sorted({j["underlying"] for j in journeys})
statuses = ["All", "closed", "expired", "open", "partial"]
outcomes = ["All", "loss", "win", "breakeven", "open"]

with col1:
    filter_underlying = st.selectbox("Underlying", underlyings)
with col2:
    filter_status = st.selectbox("Status", statuses)
with col3:
    filter_outcome = st.selectbox("Outcome", outcomes)
with col4:
    filter_flagged = st.checkbox("Only show flagged journeys", value=False)

filtered = journeys
if filter_underlying != "All":
    filtered = [j for j in filtered if j["underlying"] == filter_underlying]
if filter_status != "All":
    filtered = [j for j in filtered if j["status"] == filter_status]
if filter_outcome != "All":
    filtered = [j for j in filtered if j["outcome"] == filter_outcome]
if filter_flagged:
    filtered = [j for j in filtered if j["behavior_flags"]]

st.caption(f"Showing {len(filtered)} of {len(journeys)} journeys")
st.divider()

# --------------------------------------------------------------------------- #
# Journey list
# --------------------------------------------------------------------------- #
MANUAL_TAGS = ["", "FOMO", "Averaged Down", "Rolled", "Disciplined", "Mistake", "Research", "Other"]

for j in sorted(filtered, key=lambda x: x.get("entry_date") or "", reverse=True):
    pnl = j["realized_pnl"]
    color = pnl_color(pnl)
    flags = j["behavior_flags"]
    badge_html = " ".join(behavior_badge(f, f.replace("_", " ").title()) for f in flags)

    header_cols = st.columns([3, 1, 1, 1, 1])
    with header_cols[0]:
        opt_label = ""
        if j.get("opt_type"):
            opt_label = (
                f" · {j['opt_type'].upper()} ${j['opt_strike']:g} "
                f"exp {j['opt_expiry']}"
            )
        st.markdown(
            f"<strong style='color:#e2e8f0; font-size:1rem'>{j['underlying']}{opt_label}</strong>",
            unsafe_allow_html=True,
        )
        if badge_html:
            st.markdown(badge_html, unsafe_allow_html=True)
    with header_cols[1]:
        st.markdown(f"<span style='color:{color}; font-weight:700'>{format_pnl(pnl)}</span>",
                    unsafe_allow_html=True)
    with header_cols[2]:
        status_colors = {"closed": COLOR_WIN, "expired": COLOR_WARNING, "open": COLOR_NEUTRAL, "partial": COLOR_NEUTRAL}
        sc = status_colors.get(j["status"], COLOR_NEUTRAL)
        st.markdown(f"<span style='color:{sc}'>{j['status'].upper()}</span>", unsafe_allow_html=True)
    with header_cols[3]:
        entry = str(j.get("entry_date", ""))[:10]
        exit_ = str(j.get("exit_date", ""))[:10]
        st.caption(f"{entry} → {exit_}")
    with header_cols[4]:
        adds = j.get("num_adds", 0)
        rolled = "🔄" if j.get("was_rolled") else ""
        st.caption(f"Adds: {adds} {rolled}")

    with st.expander(f"Details — {j['journey_id'][:8]}", expanded=False):
        detail_cols = st.columns([2, 1])

        with detail_cols[0]:
            # Transaction table
            symbol_txns = txn_by_symbol.get(j["symbol"], [])
            if symbol_txns:
                txn_rows = [
                    {
                        "Date": t.run_date,
                        "Action": t.raw_action,
                        "Qty": t.quantity,
                        "Price": f"${t.price:.2f}",
                        "Net": f"${t.net_amount:,.2f}",
                        "Tag": t.manual_tag or "",
                    }
                    for t in sorted(symbol_txns, key=lambda x: x.run_date)
                ]
                st.dataframe(pd.DataFrame(txn_rows), use_container_width=True, hide_index=True)
            else:
                st.caption("No transactions found for this symbol.")

        with detail_cols[1]:
            st.markdown("**Manual Tag**")
            current_tag = j.get("manual_tag") or ""
            tag_idx = MANUAL_TAGS.index(current_tag) if current_tag in MANUAL_TAGS else 0
            new_tag = st.selectbox(
                "Tag this journey",
                MANUAL_TAGS,
                index=tag_idx,
                key=f"tag_{j['journey_id']}",
            )
            new_notes = st.text_area(
                "Notes",
                value=j.get("notes") or "",
                key=f"notes_{j['journey_id']}",
                height=100,
            )
            if st.button("Save", key=f"save_{j['journey_id']}"):
                with get_session() as session:
                    err = update_journey_tag(session, j["journey_id"], new_tag, new_notes)
                if err:
                    st.error(err)
                else:
                    st.success("Saved!")
                    st.rerun()

    st.divider()
