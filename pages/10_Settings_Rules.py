"""Settings / Rules — manage trading rules, thresholds, and LLM configuration."""

import streamlit as st

from app.core.config import settings
from app.core.database import get_session, init_db
from app.core.repository import delete_rule, fetch_rules, save_rule
from app.features.recovery_plan.generator import BEHAVIOR_RULES
from app.ui.components import COLOR_PRIMARY, COLOR_WIN, COLOR_LOSS, COLOR_WARNING
from app.ui.state import init_state

st.set_page_config(page_title="Settings | TradeInSight", layout="wide", page_icon="⚙️")
init_db()
init_state()
st.markdown(
    "<style>.stApp{background:#0f172a} h1,h2,h3{color:#e2e8f0!important}</style>",
    unsafe_allow_html=True,
)

st.title("⚙️ Settings / Rules")
st.divider()

tab_rules, tab_thresholds, tab_llm, tab_data = st.tabs([
    "📋 Trading Rules",
    "🎚️ Detection Thresholds",
    "🤖 LLM Settings",
    "🗃️ Data Management",
])

# --------------------------------------------------------------------------- #
# Tab 1: Trading Rules
# --------------------------------------------------------------------------- #
with tab_rules:
    st.markdown("### Your Trading Rules")
    st.caption("Rules you commit to following. Review these before every trade.")

    with get_session() as session:
        existing_rules = fetch_rules(session)

    if existing_rules:
        for rule in existing_rules:
            col_rule, col_del = st.columns([5, 1])
            with col_rule:
                category_color = {
                    "general": COLOR_PRIMARY,
                    "entry": COLOR_WIN,
                    "exit": COLOR_WARNING,
                    "sizing": "#8b5cf6",
                    "behavior": COLOR_LOSS,
                }.get(rule.get("category", "general"), COLOR_PRIMARY)
                st.markdown(
                    f'<div style="background:#1e293b; border-radius:8px; padding:0.7rem 1rem; '
                    f'border-left:3px solid {category_color}; color:#e2e8f0; margin-bottom:6px">'
                    f'<span style="font-size:0.7rem; color:{category_color}; text-transform:uppercase; '
                    f'letter-spacing:0.05em">{rule.get("category","general")}</span><br>'
                    f'{rule["rule_text"]}</div>',
                    unsafe_allow_html=True,
                )
            with col_del:
                if st.button("🗑️", key=f"del_{rule['id']}", help="Delete this rule"):
                    with get_session() as session:
                        err = delete_rule(session, rule["id"])
                    if err:
                        st.error(err)
                    else:
                        st.rerun()
    else:
        st.info("No rules yet. Add your first rule below or import from the Recovery Plan defaults.")

    st.divider()
    st.markdown("#### Add a New Rule")
    col_input, col_cat = st.columns([3, 1])
    with col_input:
        new_rule_text = st.text_input(
            "Rule text",
            placeholder="e.g. Never add to a losing long-option position.",
        )
    with col_cat:
        new_rule_cat = st.selectbox(
            "Category",
            ["general", "entry", "exit", "sizing", "behavior"],
        )

    if st.button("➕ Add Rule", type="primary"):
        if new_rule_text.strip():
            with get_session() as session:
                err = save_rule(session, new_rule_text.strip(), new_rule_cat)
            if err:
                st.error(err)
            else:
                st.success("Rule saved!")
                st.rerun()
        else:
            st.warning("Please enter a rule first.")

    st.divider()
    st.markdown("#### Import Recovery Plan Defaults")
    st.caption("These rules are generated from your trading data — click any to add.")
    for bt_value, rule_text in BEHAVIOR_RULES.items():
        if st.button(f"➕ {rule_text[:80]}...", key=f"import_{bt_value}"):
            with get_session() as session:
                save_rule(session, rule_text, "behavior")
            st.success("Rule added!")
            st.rerun()

# --------------------------------------------------------------------------- #
# Tab 2: Detection Thresholds
# --------------------------------------------------------------------------- #
with tab_thresholds:
    st.markdown("### Behavior Detection Thresholds")
    st.caption(
        "These values control when a behavior gets flagged. "
        "Changes take effect on your next import or re-analysis. "
        "Edit `.env` to persist these permanently."
    )

    st.markdown("#### Averaging Down")
    st.markdown(f"Current: flag when **{settings.avg_down_threshold}** or more adds to a losing position")
    st.code(f"AVG_DOWN_THRESHOLD={settings.avg_down_threshold}  # in .env", language="bash")

    st.markdown("#### Near-Expiry Hold")
    st.markdown(f"Current: flag when exiting within **{settings.near_expiry_dte} DTE**")
    st.code(f"NEAR_EXPIRY_DTE={settings.near_expiry_dte}  # in .env", language="bash")

    st.markdown("#### Oversized Position")
    st.markdown(f"Current: flag when position exceeds **{settings.oversize_pct}%** of account")
    st.code(f"OVERSIZE_PCT={settings.oversize_pct}  # in .env", language="bash")

    st.markdown("#### FOMO Entry")
    st.markdown(f"Current: flag when underlying moved **{settings.fomo_move_pct}%** before entry")
    st.code(f"FOMO_MOVE_PCT={settings.fomo_move_pct}  # in .env", language="bash")

    st.markdown("#### Account Size (for % calculations)")
    st.markdown(f"Current: **${settings.max_account_size:,.0f}**")
    st.code(f"MAX_ACCOUNT_SIZE={settings.max_account_size:.0f}  # in .env", language="bash")

    st.info(
        "To change thresholds: edit your `.env` file and restart the app. "
        "Then re-import your CSV to rerun detection with the new settings."
    )

# --------------------------------------------------------------------------- #
# Tab 3: LLM Settings
# --------------------------------------------------------------------------- #
with tab_llm:
    st.markdown("### LLM Configuration")

    if settings.has_llm:
        st.success("✅ Anthropic API key is configured — AI-powered Recovery Plan is enabled.")
        st.markdown(f"**Model:** `{settings.llm_model}`")
    else:
        st.warning("⚠️ No ANTHROPIC_API_KEY set — running in rule-based mode.")
        st.markdown(
            """
            To enable AI-powered coaching narratives in the Recovery Plan:

            1. Get an API key at [console.anthropic.com](https://console.anthropic.com)
            2. Add to your `.env` file:
            ```
            ANTHROPIC_API_KEY=sk-ant-...
            ```
            3. Restart the app

            The AI feature only runs when you explicitly visit the Recovery Plan page.
            No data is sent automatically.
            """
        )

    st.divider()
    st.markdown("#### Model")
    st.code(f"LLM_MODEL={settings.llm_model}  # in .env", language="bash")
    st.caption(
        "Supported models: `claude-3-5-sonnet-20241022`, `claude-3-haiku-20240307`. "
        "Sonnet gives better coaching quality; Haiku is faster and cheaper."
    )

# --------------------------------------------------------------------------- #
# Tab 4: Data Management
# --------------------------------------------------------------------------- #
with tab_data:
    st.markdown("### Data Management")
    st.caption(f"Database: `{settings.database_url}`")

    col_info, col_actions = st.columns(2)

    with col_info:
        st.markdown("#### Current Data")
        with get_session() as session:
            from app.core.schema import TransactionORM, TradeJourneyORM, BehaviorFlagORM, TradingRuleORM
            txn_count = session.query(TransactionORM).count()
            journey_count = session.query(TradeJourneyORM).count()
            flag_count = session.query(BehaviorFlagORM).count()
            rule_count = session.query(TradingRuleORM).filter(TradingRuleORM.is_active == True).count()

        st.metric("Transactions", txn_count)
        st.metric("Journeys", journey_count)
        st.metric("Behavior Flags", flag_count)
        st.metric("Active Rules", rule_count)

    with col_actions:
        st.markdown("#### Supported Brokers")
        brokers = {
            "✅ Fidelity": "Fully supported — CSV parser built",
            "🔜 Schwab": "Coming soon",
            "🔜 TD Ameritrade": "Coming soon",
            "🔜 Robinhood": "Coming soon",
            "🔜 Interactive Brokers": "Coming soon",
        }
        for broker, status in brokers.items():
            st.markdown(
                f'<div style="padding:6px 0; border-bottom:1px solid #1e293b; color:#94a3b8">'
                f'<strong style="color:#e2e8f0">{broker}</strong> — {status}</div>',
                unsafe_allow_html=True,
            )

    st.divider()
    st.markdown("#### Extending to Other Brokers")
    st.markdown(
        """
        To add a new broker, create a new parser in `app/features/importer/`:

        ```python
        # app/features/importer/schwab_parser.py
        def parse_schwab_csv(source) -> Tuple[List[Transaction], Optional[str]]:
            # Parse Schwab CSV → same Transaction dataclass list
            ...
        ```

        The rest of the pipeline (journey engine, behavior analyzer, P&L engine,
        all pages) works without any changes — it operates on the `Transaction`
        domain model, which is broker-agnostic.
        """
    )
