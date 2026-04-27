# TradeInSight — Architecture Decision Records

Each ADR records a significant design choice: what we chose, what we considered, and why.

---

## ADR-001 — SQLite over DuckDB or Postgres

**Decision:** SQLite with WAL mode.

**Context:** The app is local-first. Data never leaves the machine. The dataset is one person's trade history — typically a few thousand rows, never millions.

**Considered:**
- **DuckDB** — excellent for analytical queries, columnar, very fast on large datasets. But it has no persistent server mode with simple file access, and its Python API adds complexity for a Streamlit app that needs to share a session across reruns. Also overkill for row counts under 10K.
- **PostgreSQL** — production-grade, but requires a running server, a connection string, and separate installation. Violates the "zero-setup" goal.
- **SQLite** — zero dependencies, single file, ships with Python, trivially gitignored, and WAL mode allows concurrent reads from multiple Streamlit page requests. For this data size the query performance difference vs. DuckDB is immeasurable.

**Outcome:** SQLite + WAL + FK pragmas. The `DATABASE_URL` env variable means migrating to Postgres later is a one-line change.

---

## ADR-002 — Streamlit over Dash or a Custom Flask App

**Decision:** Streamlit multi-page app.

**Context:** The primary user is a solo trader, not a developer. The UI needs to be usable without npm, webpack, or a React build step.

**Considered:**
- **Dash (Plotly)** — more control over layout, supports callbacks, but requires explicit callback wiring. Much more boilerplate for 10 pages.
- **Flask + Jinja2** — full control, but hand-writing templates for charts, filters, and tables is slow and fragile.
- **Streamlit** — Python top-to-bottom. The page/widget model matches the linear "load data → filter → display" pattern perfectly. Multi-page support is built-in (the `pages/` directory convention). The `st.rerun()` / session_state API is sufficient for our interactivity needs (filters, save buttons).

**Trade-offs accepted:** Streamlit's execution model re-runs the entire script on every widget interaction. This is fine at our data size. If the dataset grows to hundreds of thousands of rows, `@st.cache_data` decorators on the fetch functions would address it.

---

## ADR-003 — Feature-Based Package Structure

**Decision:** `app/features/<feature>/` vertical slices, not a horizontal `services/` + `models/` split.

**Context:** The app has five distinct processing steps (import → journey → behavior → P&L → recovery). Each step is independently testable and has a clear input/output contract.

**Considered:**
- **Horizontal layers** (`app/services/`, `app/repositories/`, `app/models/`) — common in Django-style apps. Makes sense when many services share many models. Here, each feature owns its logic end-to-end and doesn't bleed into others.
- **Vertical slices** — each feature folder contains everything it needs (its own logic + tests). Adding a new feature (e.g., a tax lot calculator) means adding one new folder, touching zero existing files.

**Outcome:** Feature-based. The domain models live in a shared `app/domain/` layer that features import; the core infrastructure (DB, config, repository) lives in `app/core/`. Features never import from each other — they only consume domain models and core services.

---

## ADR-004 — Deterministic Transaction IDs via SHA1 Hash

**Decision:** `transaction_id = SHA1(run_date + account + action + symbol + quantity + price)`.

**Context:** Fidelity's CSV export has no native unique ID column. The same CSV can be re-uploaded by the user.

**Considered:**
- **UUID on insert** — simple, but re-importing creates duplicate rows requiring a separate dedup step.
- **Composite natural key** — use all six fields as a composite PK in the DB. Works but makes JOINs awkward and SQLAlchemy ORM less clean.
- **SHA1 hash** — deterministic, short enough for a varchar PK, collision probability negligible for trade history sizes. Re-importing the same CSV is a true no-op: `session.get(TransactionORM, id)` finds the existing row and skips it.

**Outcome:** SHA1 hash. The `_make_transaction_id()` function in `fidelity_parser.py` is the single source of truth.

---

## ADR-005 — Behavior Detection as In-Memory Analyzers, Not SQL Queries

**Decision:** Load all journeys into Python, run detectors as pure functions, write results back.

**Context:** Behavior detection involves nuanced logic (rolling window comparisons, cross-journey aggregates, severity scaling) that would be painful to express in SQL.

**Considered:**
- **SQL window functions** — possible for repeat-loser detection, but averaging-down detection (which needs to inspect the sequence and cost of individual transactions within a journey) requires row-by-row logic that is awkward in SQL.
- **Pandas** — could work, but adds a dependency layer between raw data and results, and the dataframe manipulation would obscure the behavioral logic.
- **Pure Python** — each detector is a small, focused function. The logic is readable, unit-testable in isolation, and fast enough (microseconds per journey at this data size).

**Outcome:** Pure Python analyzers. The `analyze_journeys()` function is a pipeline of detector calls. Adding a new behavior type means adding one `_detect_*` function and appending it to the pipeline.

---

## ADR-006 — Behavior Flags Mutate TradeJourney In-Place

**Decision:** `analyze_journeys()` appends to `journey.behavior_flags` as a side effect.

**Context:** The P&L engine needs flag information to compute per-behavior P&L breakdowns. There are two options: (a) pass flags separately to the P&L engine, or (b) embed flags on the journey object.

**Considered:**
- **Pass flags separately** — cleaner functional design, but requires the P&L engine to do a join (journey_id lookup) on every journey. Also means callers always need two parallel lists.
- **Embed on journey** — the journey object becomes the single unit of analysis. One call to `analyze_journeys()` enriches the list in place; one call to `calculate_pnl()` reads the enriched list. The Streamlit pages only need to manage one list.

**Trade-off accepted:** Mutation makes the function impure. This is documented clearly in the docstring and is safe in practice because journeys are rebuilt fresh from the DB on every page load.

---

## ADR-007 — Optional LLM Narrative via Claude API

**Decision:** Recovery plan narrative is opt-in, gated on `ANTHROPIC_API_KEY` in `.env`.

**Context:** An LLM-generated plain-English narrative ("Here's what these patterns cost you and how to change") adds value but is not core functionality. The app must work fully without an API key.

**Considered:**
- **Always require API key** — simplifies code (no conditional), but creates a hard dependency on a paid service for a local-first tool.
- **Use a local model (Ollama)** — would truly eliminate the cloud dependency, but adds significant setup complexity (model download, RAM requirements).
- **Opt-in cloud API** — `settings.has_llm` property returns True only when the key is set. The `_generate_llm_narrative()` function returns `None` gracefully when it isn't. The Recovery Plan page renders the narrative section only when the narrative is not None.

**Outcome:** Opt-in Claude API. Uses `claude-3-haiku` (fast, cheap) for the narrative call. Cost is a few cents per plan generation.

---

## ADR-008 — Roll Detection by Time Window, Not By Symbol Chain

**Decision:** A roll is detected when a SELL_TO_CLOSE on a symbol is followed within `ROLL_WINDOW_DAYS=5` by a BUY_TO_OPEN on the same **underlying** (different expiry).

**Context:** Fidelity exports do not mark rolls explicitly. A roll is two separate transactions on different option symbols.

**Considered:**
- **Exact symbol chaining** — detect only when the new BTO has a later expiry than the STC. This is more precise but fails when the new expiry is on the same date (same-strike, same-expiry roll, rare but possible).
- **Description-column parsing** — Fidelity sometimes includes "ROLL" in the description. Unreliable and not always present.
- **Time window heuristic** — 5-day window is consistent with how options traders actually roll (usually same-day or next-day). Fast to compute, no description parsing needed.

**Outcome:** 5-day window heuristic. The constant `ROLL_WINDOW_DAYS` in `grouper.py` is easy to tune. The window was chosen to catch same-day and weekend-bridging rolls while not conflating unrelated trades on the same underlying.
