# TradeInSight — Architecture

## Overview

TradeInSight is a **local-first** options trading analysis dashboard. All data lives in a SQLite file on your machine — no cloud, no API keys required for core functionality. The stack is Python 3.11 + Streamlit (UI), SQLAlchemy (ORM), and Plotly (charts), with an optional Claude API integration for narrative recovery plan generation.

---

## Layer Diagram

```
┌──────────────────────────────────────────────────────────────┐
│  Streamlit Pages  (Home.py + pages/1_*.py … pages/10_*.py)   │
│  ─ dark terminal theme, per-page layout, rerun on save       │
└────────────────────────┬─────────────────────────────────────┘
                         │ calls
┌────────────────────────▼─────────────────────────────────────┐
│  UI Layer  (app/ui/)                                          │
│  components.py — metric_card, behavior_badge, all charts     │
│  state.py      — st.session_state initialisation helpers     │
└────────────────────────┬─────────────────────────────────────┘
                         │ calls
┌────────────────────────▼─────────────────────────────────────┐
│  Feature Layer  (app/features/)                               │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐   │
│  │  importer   │  │journey_engine│  │behavior_analyzer  │   │
│  │  normalizer │  │  grouper     │  │  analyzer         │   │
│  │  fidelity   │  └──────────────┘  └───────────────────┘   │
│  │  _parser    │  ┌──────────────┐  ┌───────────────────┐   │
│  └─────────────┘  │  pnl_engine  │  │  recovery_plan    │   │
│                   │  calculator  │  │  generator        │   │
│                   └──────────────┘  └───────────────────┘   │
└────────────────────────┬─────────────────────────────────────┘
                         │ reads / writes via
┌────────────────────────▼─────────────────────────────────────┐
│  Core Layer  (app/core/)                                      │
│  repository.py — CRUD wrappers (upsert / fetch / update)     │
│  schema.py     — SQLAlchemy ORM table definitions            │
│  database.py   — engine init, get_session() context manager  │
│  config.py     — Settings dataclass (thresholds, env vars)   │
│  logging_setup.py — rotating file handler                    │
└────────────────────────┬─────────────────────────────────────┘
                         │ pure Python types
┌────────────────────────▼─────────────────────────────────────┐
│  Domain Layer  (app/domain/models/)                           │
│  transaction.py    — Transaction, ActionType, OptionDetails  │
│  trade_journey.py  — TradeJourney, JourneyStatus/Outcome     │
│  behavior_flag.py  — BehaviorFlag, BehaviorType (8 types)    │
│  pnl.py            — PnLSummary, SymbolPnL, BehaviorPnL      │
└──────────────────────────────────────────────────────────────┘
                         │ persisted in
                    ┌────▼────┐
                    │ SQLite  │  data/tradein_sight.db
                    │  (WAL)  │  (gitignored)
                    └─────────┘
```

---

## Data Flow

```
CSV Upload (Fidelity format)
        │
        ▼
fidelity_parser.parse_fidelity_csv()
  └─ normalizer.parse_occ_symbol()  →  OptionDetails per row
  └─ _make_transaction_id()         →  SHA1 hash (idempotent re-import)
        │
        ▼  List[Transaction]
upsert_transactions()               →  TransactionORM rows (skip duplicates)
        │
        ▼
journey_engine.build_journeys()
  └─ group by symbol
  └─ _detect_rolls() (5-day window)
  └─ sum cost_basis / proceeds
  └─ resolve status (open/closed/expired/partial)
        │
        ▼  List[TradeJourney]
upsert_journey() × N                →  TradeJourneyORM rows
        │
        ▼
behavior_analyzer.analyze_journeys()
  └─ _detect_averaging_down()
  └─ _detect_near_expiry_hold()
  └─ _detect_late_exit()
  └─ _detect_oversized_position()
  └─ _detect_fomo_entry()
  └─ _detect_rolled_loser()
  └─ _detect_repeat_losers()        ←  cross-journey (same underlying ≥ 3 losses)
        │
        ▼  List[BehaviorFlag]  + mutates journey.behavior_flags
upsert_behavior_flags()             →  BehaviorFlagORM rows
session.flush() guards FK constraints
        │
        ▼
pnl_engine.calculate_pnl()
  └─ totals, win rate, avg win/loss, profit factor
  └─ _calc_by_symbol()
  └─ _calc_time_series()  →  cumulative P&L + drawdown series
        │
        ▼  PnLSummary
Streamlit pages render charts + metrics
```

---

## Database Schema

| Table | Primary Key | Notable Columns |
|---|---|---|
| `transactions` | `id` (SHA1 hash) | `run_date`, `symbol`, `underlying`, `action`, `security_type`, `net_amount`, `opt_*` fields, `journey_id` (FK), `manual_tag`, `notes` |
| `trade_journeys` | `id` (UUID) | `underlying`, `symbol`, `opt_type/strike/expiry`, `status`, `outcome`, `realized_pnl`, `behavior_flags_json` (TEXT), `manual_tag`, `notes` |
| `behavior_flags` | auto-int | `journey_id` (FK), `behavior_type`, `severity`, `estimated_loss_impact`, `detail`, `evidence` |
| `trading_rules` | auto-int | `rule_text`, `category`, `is_active` |
| `import_batches` | UUID | `filename`, `imported_at`, `transaction_count`, `status` |

SQLite is opened with `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON`. Sessions auto-rollback on error via the `get_session()` context manager.

---

## Key Design Principles

**Idempotent imports** — `_make_transaction_id()` is a SHA1 over `(run_date, account, action, symbol, quantity, price)`. Re-importing the same CSV is a no-op.

**Domain objects are pure dataclasses** — no SQLAlchemy in the domain layer. Features receive and return plain Python objects. The repository layer translates ORM ↔ domain.

**Result tuple error pattern** — every repository function returns `(value, error | None)` or just `error | None`. Pages handle errors via `st.error()` without crashing.

**Behavior flags mutate journeys in-memory** — `analyze_journeys()` writes back to `journey.behavior_flags` (a list) as a side effect, so the journey list is ready for P&L calculation that needs flag context without a second DB round-trip.

---

## Configuration

`app/core/config.py` — `Settings` dataclass loaded from `.env` at startup:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/tradein_sight.db` | SQLite path |
| `AVG_DOWN_THRESHOLD` | `2` | Adds before flagging averaging-down |
| `NEAR_EXPIRY_DTE` | `7` | DTE threshold for expiry-risk flag |
| `OVERSIZE_PCT` | `10` | % of account triggering oversize flag |
| `FOMO_MOVE_PCT` | `5` | % underlying move for FOMO flag |
| `MAX_ACCOUNT_SIZE` | `100000` | Reference account size |
| `ANTHROPIC_API_KEY` | *(unset)* | Enables LLM narrative on Recovery Plan |

---

## Testing

56 tests across 4 test files, all passing. Fixtures live in `tests/conftest.py`.

```
tests/
  conftest.py              # _make_txn(), tsla_avg_down_transactions, nvda_winner_transactions
  test_parser.py           # OCC symbol parsing, CSV ingestion, dedup
  test_journey_engine.py   # grouping, roll detection, status resolution
  test_behavior_analyzer.py# all 7 detectors + edge cases
  test_pnl_engine.py       # metrics, time series, drawdown
```

Run with: `pytest tests/ -v`
