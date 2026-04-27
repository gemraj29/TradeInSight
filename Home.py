"""TradeInSight — Home page and app entry point."""

import streamlit as st

from app.core.config import settings
from app.core.database import init_db
from app.core.logging_setup import setup_logging
from app.ui.state import init_state, mark_db_ready

# --------------------------------------------------------------------------- #
# One-time app initialization
# --------------------------------------------------------------------------- #
setup_logging()
init_db()
mark_db_ready()

st.set_page_config(
    page_title="TradeInSight",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_state()

# --------------------------------------------------------------------------- #
# Custom CSS — dark trading terminal aesthetic
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
    .stApp { background-color: #0f172a; }
    .stSidebar { background-color: #1e293b; }
    .stSidebar [data-testid="stSidebarNav"] a {
        color: #94a3b8;
        font-size: 0.9rem;
    }
    .stSidebar [data-testid="stSidebarNav"] a:hover { color: #e2e8f0; }
    .stSidebar [data-testid="stSidebarNav"] .active { color: #3b82f6 !important; }
    div[data-testid="metric-container"] {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 1rem;
    }
    .stDataFrame { background: #1e293b; }
    h1, h2, h3, h4 { color: #e2e8f0 !important; }
    p, li { color: #94a3b8; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Hero section
# --------------------------------------------------------------------------- #
st.title("📈 TradeInSight")
st.markdown(
    "**Understand your options losses. Identify behavioral mistakes. Build better rules.**"
)
st.divider()

col1, col2 = st.columns([2, 1])

with col1:
    st.markdown(
        """
        ### Welcome to TradeInSight

        This dashboard turns your raw Fidelity statement exports into an honest
        post-mortem of your options trading journey.

        It does not just show charts — it answers the hard questions:

        - **Where** did you lose the most money?
        - **Why** — which behavioral patterns cost you the most?
        - **How much** did averaging down, rolling losers, and holding near expiry really cost?
        - **What would have happened** if you had followed a simple rule?

        #### Getting started

        1. Go to **Import Statements** and upload your Fidelity CSV export
        2. Review parsed trades and commit to the database
        3. Check **Overview** for your overall P&L summary
        4. Deep-dive in **Behavior Mistake Analysis** to find patterns
        5. Visit **Recovery Plan** for actionable rules and a what-if simulation

        Use the **sample data** to explore the app immediately:
        load `data/sample/fidelity_sample.csv` from the Import page.
        """
    )

with col2:
    st.markdown("#### Quick Links")
    pages = [
        ("📊", "Overview", "Your P&L dashboard at a glance"),
        ("📥", "Import Statements", "Load Fidelity CSV files"),
        ("🗺️", "Trade Journey Viewer", "See every trade from entry to exit"),
        ("💸", "Options Loss Breakdown", "Loss by symbol, strategy, expiry"),
        ("📉", "Averaging Down Analysis", "Cost of adding to losers"),
        ("🔄", "Rolling Analysis", "Cost of rolling losing options"),
        ("⏰", "Expiry Risk Analysis", "DTE vs P&L patterns"),
        ("🧠", "Behavior Mistake Analysis", "All behavioral flags"),
        ("🛡️", "Recovery Plan", "Rules + what-if simulation"),
        ("⚙️", "Settings / Rules", "Configure thresholds and rules"),
    ]
    for icon, name, desc in pages:
        st.markdown(
            f'<div style="padding:6px 0; border-bottom:1px solid #1e293b">'
            f'<span style="font-size:1rem">{icon}</span> '
            f'<strong style="color:#e2e8f0">{name}</strong>'
            f'<br><span style="font-size:0.75rem; color:#64748b">{desc}</span></div>',
            unsafe_allow_html=True,
        )

st.divider()
st.caption(
    f"TradeInSight v0.1.0 · Local-first · Data stored in `{settings.database_url}` · "
    f"LLM: {'✅ Claude enabled' if settings.has_llm else '❌ Rule-based only (set ANTHROPIC_API_KEY to enable)'}"
)
