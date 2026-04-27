"""Import Statements page — upload Fidelity CSV, preview, and commit to database."""

import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from app.core.config import settings
from app.core.database import get_session, init_db
from app.core.repository import (
    fetch_import_batches,
    save_import_batch,
    upsert_behavior_flags,
    upsert_journey,
    upsert_transactions,
)
from app.features.behavior_analyzer.analyzer import analyze_journeys
from app.features.importer.fidelity_parser import parse_fidelity_csv
from app.features.journey_engine.grouper import build_journeys
from app.ui.state import init_state

st.set_page_config(page_title="Import Statements | TradeInSight", layout="wide", page_icon="📥")
init_db()
init_state()

st.markdown(
    "<style>.stApp{background:#0f172a} h1,h2,h3{color:#e2e8f0!important}</style>",
    unsafe_allow_html=True,
)

st.title("📥 Import Statements")
st.caption("Upload your Fidelity CSV export to load trades into TradeInSight")
st.divider()

# --------------------------------------------------------------------------- #
# Instructions
# --------------------------------------------------------------------------- #
with st.expander("How to export from Fidelity", expanded=False):
    st.markdown(
        """
        1. Log in to **Fidelity.com**
        2. Go to **Accounts & Trade → Activity & Orders**
        3. Select your account and date range
        4. Click **Download** → choose **CSV** format
        5. Upload the downloaded file below

        The CSV should contain columns like:
        `Run Date, Account, Action, Symbol, Security Description, Security Type,
        Quantity, Price ($), Commission ($), Fees ($), Amount ($), Settlement Date`
        """
    )

# --------------------------------------------------------------------------- #
# Upload widget
# --------------------------------------------------------------------------- #
tab_upload, tab_sample = st.tabs(["Upload your CSV", "Use sample data"])

with tab_upload:
    uploaded_file = st.file_uploader(
        "Choose a Fidelity CSV file",
        type=["csv", "txt"],
        help="Download from Fidelity → Activity & Orders → Download CSV",
    )
    csv_source = uploaded_file.read() if uploaded_file else None
    csv_name = uploaded_file.name if uploaded_file else None

with tab_sample:
    st.info(f"Sample data path: `{settings.sample_csv_path}`")
    if st.button("Load sample Fidelity data"):
        csv_source = settings.sample_csv_path.read_bytes()
        csv_name = "fidelity_sample.csv"
        st.success("Sample data loaded — scroll down to preview.")

# --------------------------------------------------------------------------- #
# Parse and preview
# --------------------------------------------------------------------------- #
if csv_source:
    batch_id = str(uuid.uuid4())[:8]

    with st.spinner("Parsing CSV..."):
        transactions, parse_error = parse_fidelity_csv(csv_source, import_batch_id=batch_id)

    if parse_error:
        st.error(f"Parse error: {parse_error}")
        st.stop()

    if not transactions:
        st.warning("No transactions found in the file. Check the format.")
        st.stop()

    st.success(f"✅ Parsed **{len(transactions)}** transactions")

    # Preview table
    st.markdown("#### Preview (first 50 rows)")
    preview_rows = [
        {
            "Date": t.run_date,
            "Symbol": t.symbol,
            "Underlying": t.underlying,
            "Action": t.raw_action,
            "Type": t.security_type.value,
            "Qty": t.quantity,
            "Price": f"${t.price:.2f}",
            "Net": f"${t.net_amount:,.2f}",
            "Expiry": t.option_details.expiry if t.option_details else "",
            "Strike": t.option_details.strike if t.option_details else "",
            "Opt Type": t.option_details.option_type.value if t.option_details else "",
        }
        for t in transactions[:50]
    ]
    st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

    options_count = sum(1 for t in transactions if t.is_option)
    stock_count = len(transactions) - options_count
    c1, c2, c3 = st.columns(3)
    c1.metric("Options transactions", options_count)
    c2.metric("Stock transactions", stock_count)
    c3.metric("Unique underlyings", len({t.underlying for t in transactions}))

    # --------------------------------------------------------------------------- #
    # Commit
    # --------------------------------------------------------------------------- #
    st.divider()
    if st.button("✅ Commit to Database", type="primary", use_container_width=True):
        with st.spinner("Saving transactions and building journeys..."):
            with get_session() as session:
                # 1. Save transactions
                count, err = upsert_transactions(session, transactions)
                if err:
                    st.error(f"Error saving transactions: {err}")
                    st.stop()

                # 2. Build journeys
                journeys = build_journeys(transactions)

                # 3. Detect behaviors
                flags = analyze_journeys(journeys)

                # 4. Persist journeys
                for journey in journeys:
                    err = upsert_journey(session, journey)
                    if err:
                        st.warning(f"Journey save warning: {err}")

                # 5. Persist flags
                err = upsert_behavior_flags(session, flags)
                if err:
                    st.warning(f"Behavior flag save warning: {err}")

                # 6. Record batch
                save_import_batch(session, batch_id, csv_name or "unknown.csv", count)
                st.session_state["last_import_batch"] = batch_id

        st.success(
            f"✅ Imported **{count}** transactions → "
            f"**{len(journeys)}** journeys → **{len(flags)}** behavior flags detected"
        )
        st.balloons()

# --------------------------------------------------------------------------- #
# Import history
# --------------------------------------------------------------------------- #
st.divider()
st.markdown("#### Import History")
with get_session() as session:
    batches = fetch_import_batches(session)

if batches:
    st.dataframe(pd.DataFrame(batches), use_container_width=True, hide_index=True)
else:
    st.caption("No imports yet.")
