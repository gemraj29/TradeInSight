# TradeInSight — Module Reference

Each section covers one module: what it does, its public interface, dependencies, and key constants or thresholds to know about.

---

## Domain Models  `app/domain/models/`

### `transaction.py`

Pure dataclass representing a single brokerage transaction row.

**Key types**

| Type | Values |
|---|---|
| `SecurityType` | `EQUITY`, `OPTION` |
| `ActionType` | `BUY_TO_OPEN`, `SELL_TO_CLOSE`, `BUY_TO_CLOSE`, `SELL_TO_OPEN`, `EXPIRED`, `ASSIGNED`, `DIVIDEND`, `OTHER` |
| `OptionType` | `CALL`, `PUT` |

`OptionDetails` — embedded dataclass holding `underlying`, `option_type`, `strike`, `expiry` (date), `dte_at_entry`.

`Transaction` — top-level dataclass. Key fields: `transaction_id` (str), `run_date` (date), `symbol` (full OCC string), `underlying` (e.g. "TSLA"), `action` (ActionType), `quantity`, `price`, `net_amount`, `option_details` (Optional), `manual_tag`, `notes`.

**Dependencies:** stdlib only.

---

### `trade_journey.py`

Represents the complete lifecycle of a position in one symbol.

**Key types**

| Type | Values |
|---|---|
| `JourneyStatus` | `OPEN`, `CLOSED`, `EXPIRED`, `PARTIAL` |
| `JourneyOutcome` | `WIN`, `LOSS`, `BREAKEVEN`, `OPEN` |

`TradeJourney` — key fields: `journey_id` (UUID str), `underlying`, `symbol`, `option_details`, `status`, `outcome`, `entry_date`, `exit_date`, `total_cost_basis`, `total_proceeds`, `realized_pnl`, `num_adds`, `was_rolled`, `roll_count`, `held_near_expiry`, `dte_at_first_entry`, `max_position_size`, `behavior_flags` (List[str], mutated by analyzer), `manual_tag`, `notes`.

**Dependencies:** stdlib only.

---

### `behavior_flag.py`

Defines the 8 behavioral mistake types and the flag record.

| BehaviorType | What it means |
|---|---|
| `AVERAGING_DOWN` | Added to a losing position ≥ `avg_down_threshold` times |
| `NEAR_EXPIRY_HOLD` | Held option within `near_expiry_dte` days of expiry |
| `ROLLING_LOSER` | Rolled a position that was already at a loss |
| `OVERSIZED_POSITION` | Position exceeded `oversize_pct`% of account |
| `FOMO_ENTRY` | Entered after underlying moved ≥ `fomo_move_pct`% |
| `LATE_EXIT` | Closed at > 20% of max unrealised loss (heuristic) |
| `REPEAT_LOSER` | Lost on same underlying 3+ times (cross-journey) |
| `DISCIPLINED` | Clean exit, no negative flags |

`BehaviorFlag` dataclass: `journey_id`, `behavior_type` (BehaviorType), `severity` (1-3), `estimated_loss_impact` (float, negative for losses), `detail` (str), `evidence` (str).

`BEHAVIOR_LABELS` — dict mapping BehaviorType → display label.
`BEHAVIOR_DESCRIPTIONS` — dict mapping BehaviorType → one-sentence explanation.

**Dependencies:** stdlib only.

---

### `pnl.py`

Result dataclasses returned by the P&L engine.

`SymbolPnL` — per-underlying summary: `underlying`, `total_pnl`, `trade_count`, `win_count`, `loss_count`.

`BehaviorPnL` — per-behavior summary: `behavior_type` (str), `total_loss_impact`, `trade_count`.

`PnLSummary` — top-level result:
- Scalars: `total_realized_pnl`, `total_trades`, `winning_trades`, `losing_trades`, `win_rate`, `avg_win`, `avg_loss`, `profit_factor`, `max_drawdown`
- Series: `cumulative_pnl_series` (dict[date, float]), `drawdown_series` (dict[date, float])
- Lists: `by_symbol` (List[SymbolPnL]), `by_behavior` (List[BehaviorPnL])

---

## Core Layer  `app/core/`

### `config.py`

`Settings` dataclass. Loaded once at import time via `python-dotenv`. All threshold values are here — edit `.env` to override without touching code.

```python
settings = Settings()   # singleton used everywhere
```

### `database.py`

```python
init_db()               # creates all tables (called on Home.py startup)
get_session() -> Session  # context manager, auto-rollback on exception
```

Engine is created with two pragmas applied on every connection via `@event.listens_for`:
- `PRAGMA journal_mode=WAL` — allows concurrent readers
- `PRAGMA foreign_keys=ON` — enforces FK constraints

### `schema.py`

Five `DeclarativeBase` ORM classes mapping 1:1 to DB tables. No business logic here — purely structural. See Architecture doc for column inventory.

### `repository.py`

All public functions follow one of two signatures:
- `(session, ...) -> Optional[str]` — returns error string or None
- `(session, ...) -> Tuple[value, Optional[str]]` — returns (result, error)

Key functions:

| Function | Purpose |
|---|---|
| `upsert_transactions(session, txns)` | Skip-on-duplicate import |
| `fetch_all_transactions(session)` | All rows, ordered by date |
| `upsert_journey(session, journey)` | Insert or update journey + link transactions |
| `fetch_all_journeys(session)` | All journeys as dicts (for Streamlit pages) |
| `update_journey_tag(session, id, tag, notes)` | Save manual tag/notes |
| `upsert_behavior_flags(session, flags)` | Replace all flags for affected journeys |
| `fetch_behavior_flags(session)` | All flags as dicts |
| `save_rule / fetch_rules / delete_rule` | Trading rules CRUD |
| `save_import_batch / fetch_import_batches` | Import history |

**Important:** `upsert_behavior_flags()` calls `session.flush()` first to satisfy FK constraints when journeys and flags are inserted in the same session.

---

## Feature Layer  `app/features/`

### `importer/normalizer.py`

Parsing utilities for Fidelity's CSV format.

```python
parse_occ_symbol(symbol: str) -> Optional[OptionDetails]
  # "TSLA240119C00250000" → OptionDetails(underlying="TSLA", type=CALL, strike=250.0, expiry=date(2024,1,19))

parse_option_description(description: str) -> Optional[OptionDetails]
  # Fallback for non-OCC symbols using the Description column

compute_dte(expiry: date, run_date: date) -> int

extract_underlying_from_symbol(symbol: str) -> str
  # Uses _UNDERLYING_MAP for multi-letter underlyings (SPY, QQQ, etc.)
```

`_UNDERLYING_MAP` — dict of known symbols that require special handling (e.g. `SPXW` → `SPX`).

### `importer/fidelity_parser.py`

```python
parse_fidelity_csv(csv_bytes: bytes) -> Tuple[List[Transaction], Optional[str]]
```

Reads raw Fidelity export bytes. Handles the two-header-row format, maps action strings via `_ACTION_MAP`, calls normalizer for option details, generates deterministic `transaction_id` via SHA1.

**Dependencies:** `normalizer`, `domain/models/transaction`, `pandas`.

---

### `journey_engine/grouper.py`

```python
build_journeys(transactions: List[Transaction]) -> List[TradeJourney]
```

Groups transactions by `symbol`. Within each group:
1. Sorts by date
2. Calls `_detect_rolls()` — if a SELL_TO_CLOSE is followed within `ROLL_WINDOW_DAYS=5` by a BUY_TO_OPEN of the same underlying, marks `was_rolled=True`
3. Computes `total_cost_basis`, `total_proceeds`, `realized_pnl`
4. Sets `status` based on remaining open contracts and EXPIRED actions
5. Sets `outcome` (WIN / LOSS / BREAKEVEN) based on realized_pnl sign (±$5 breakeven band)
6. Tracks `num_adds`, `dte_at_first_entry`, `max_position_size`

**Dependencies:** `domain/models/*`.

---

### `behavior_analyzer/analyzer.py`

```python
analyze_journeys(journeys: List[TradeJourney]) -> List[BehaviorFlag]
```

Runs 7 detectors. Each per-journey detector receives a single `TradeJourney`; the cross-journey detector receives the full list.

| Detector | Threshold |
|---|---|
| `_detect_averaging_down` | `num_adds >= settings.avg_down_threshold` |
| `_detect_near_expiry_hold` | `held_near_expiry == True` (set by grouper when DTE ≤ 7 at last transaction) |
| `_detect_late_exit` | `realized_pnl < cost_basis * LATE_EXIT_THRESHOLD` where threshold = 0.20 |
| `_detect_oversized_position` | `max_position_size > settings.max_account_size * oversize_pct / 100` |
| `_detect_fomo_entry` | heuristic on entry timing vs. underlying move |
| `_detect_rolled_loser` | `was_rolled == True` and journey is a loss |
| `_detect_repeat_losers` | groups losses by `underlying`, flags if ≥ 3 losses on same symbol |

Side effect: mutates `journey.behavior_flags` list in place.

**Dependencies:** `domain/models/*`, `core/config`.

---

### `pnl_engine/calculator.py`

```python
calculate_pnl(
    journeys: List[TradeJourney],
    behavior_flags: Optional[List[BehaviorFlag]] = None
) -> PnLSummary
```

Only counts CLOSED and EXPIRED journeys for realized metrics. OPEN journeys are excluded from win rate and averages.

`_calc_by_symbol()` — groups by `underlying`, sums pnl, counts wins/losses.

`_calc_time_series()` — sorts closed journeys by `exit_date`, builds cumulative sum and rolling max for drawdown calculation.

`profit_factor` = gross_wins / abs(gross_losses). Returns `inf` when there are no losses.

**Dependencies:** `domain/models/*`.

---

### `recovery_plan/generator.py`

```python
generate_recovery_plan(
    journeys: List[TradeJourney],
    flags: List[BehaviorFlag],
    rules: List[dict]
) -> dict
```

Returns a structured plan dict with keys: `total_recoverable`, `simulated_improvement`, `behavior_breakdown`, `rule_violations`, `narrative` (str or None).

`simulate_without_behavior(journeys, flags, behavior_type)` — recalculates P&L excluding journeys with the given flag, weighted by `AVOIDANCE_FACTOR[behavior_type]` (between 0.5 and 0.9).

`_generate_llm_narrative(plan_context)` — calls Claude API (`claude-3-haiku`) only when `settings.has_llm` is True. Returns None gracefully if API key absent.

`BEHAVIOR_RULES` — maps BehaviorType to the corresponding trading rule text.
`AVOIDANCE_FACTOR` — how much of the loss was preventable per behavior type.

**Dependencies:** `domain/models/*`, `core/config`, `anthropic` (optional).

---

## UI Layer  `app/ui/`

### `components.py`

All reusable Streamlit components and Plotly chart factories.

| Function | Returns |
|---|---|
| `metric_card(label, value, delta, color)` | `st.markdown` HTML card |
| `behavior_badge(flag_type, label)` | Inline HTML badge string |
| `format_pnl(value)` | `"+$1,234.56"` or `"-$1,234.56"` |
| `pnl_color(value)` | `COLOR_WIN`, `COLOR_LOSS`, or `COLOR_NEUTRAL` |
| `chart_cumulative_pnl(series)` | `go.Figure` line chart |
| `chart_drawdown(series)` | `go.Figure` area chart (filled red) |
| `chart_by_symbol(by_symbol)` | `go.Figure` horizontal bar chart |
| `chart_by_behavior(by_behavior)` | `go.Figure` bar chart |
| `chart_win_rate_gauge(win_rate)` | `go.Figure` gauge chart |
| `chart_expiry_risk_scatter(journeys)` | `go.Figure` scatter (DTE vs P&L) |

Color constants: `COLOR_WIN = "#10b981"`, `COLOR_LOSS = "#ef4444"`, `COLOR_NEUTRAL = "#94a3b8"`, `COLOR_WARNING = "#f59e0b"`.

### `state.py`

```python
init_state()   # called at top of every page to ensure st.session_state keys exist
```

---

## Pages  `pages/`

| File | Page | Purpose |
|---|---|---|
| `Home.py` | Home | Entry point, hero section, `init_db()` + `setup_logging()` |
| `1_Overview.py` | Overview | KPI metrics, cumulative P&L chart, drawdown |
| `2_Import_Statements.py` | Import Statements | CSV uploader, import history, duplicate detection |
| `3_Trade_Journey_Viewer.py` | Trade Journey Viewer | Browse all journeys, filter, add manual tags & notes |
| `4_Options_Loss_Breakdown.py` | Loss Breakdown | P&L by symbol bar chart, loss distribution |
| `5_Averaging_Down_Analysis.py` | Averaging Down | Flags with severity, loss impact per averaging-down journey |
| `6_Rolling_Analysis.py` | Rolling Analysis | Rolled positions, roll count, cost vs. proceeds |
| `7_Expiry_Risk_Analysis.py` | Expiry Risk | Scatter: DTE-at-entry vs. P&L, near-expiry holds |
| `8_Behavior_Mistake_Analysis.py` | Behavior Analysis | All 8 behavior types, P&L impact per flag |
| `9_Recovery_Plan.py` | Recovery Plan | What-if simulation, rule checklist, optional LLM narrative |
| `10_Settings_Rules.py` | Settings & Rules | Add/delete trading rules, view import history |

All pages call `init_db()` and `init_state()` at the top, use `get_session()` for DB access, and share the dark CSS theme (`background: #0f172a`).
