# TradeInSight

A local-first trading analysis dashboard that helps you understand *where*, *why*, and *how* you lost money trading options — and what behavioral patterns caused the most damage.

## What It Does

- Imports Fidelity CSV statement exports (stocks + options)
- Groups transactions into complete trade journeys (entry → adds → exits → rolls → expiry)
- Detects behavioral mistakes: averaging down, rolling losers, holding near expiry, FOMO entries, oversized positions
- Calculates P&L by symbol, strategy, behavior, and time period
- Provides a Recovery Plan with "what-if" simulations and personalized trading rules
- Lets you manually tag and annotate trades for deeper review

## Quick Start

### 1. Clone / copy the project

```bash
cd TradeInSight
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate      # macOS / Linux
.venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env — ANTHROPIC_API_KEY is optional (only for AI-powered recovery narratives)
```

### 5. Run the app

```bash
streamlit run Home.py
```

Open http://localhost:8501 in your browser.

## Importing Your Fidelity Data

1. Log in to Fidelity.com → Accounts & Trade → Activity & Orders
2. Select date range → Download → CSV
3. In TradeInSight, go to **Import Statements** → upload the CSV file
4. Preview the parsed trades, then click **Commit to Database**

A sample CSV is included at `data/sample/fidelity_sample.csv` to explore the app immediately.

## Project Structure

```
TradeInSight/
├── Home.py                          # Streamlit entry point
├── app/
│   ├── core/
│   │   ├── config.py                # Settings from .env
│   │   ├── database.py              # SQLite engine + session factory
│   │   └── logging_setup.py         # Structured logging
│   ├── domain/
│   │   └── models/
│   │       ├── transaction.py       # Raw transaction dataclass
│   │       ├── trade_journey.py     # Grouped journey dataclass
│   │       ├── behavior_flag.py     # Detected behavior flag
│   │       └── pnl.py              # P&L summary dataclass
│   ├── features/
│   │   ├── importer/
│   │   │   ├── fidelity_parser.py   # CSV → Transaction list
│   │   │   └── normalizer.py        # Options description parser
│   │   ├── journey_engine/
│   │   │   └── grouper.py           # Transactions → TradeJourneys
│   │   ├── behavior_analyzer/
│   │   │   └── analyzer.py          # Journey → BehaviorFlags
│   │   ├── pnl_engine/
│   │   │   └── calculator.py        # All P&L metrics
│   │   └── recovery_plan/
│   │       └── generator.py         # Rules + what-if simulation
│   └── ui/
│       ├── components.py            # Shared Streamlit widgets
│       └── state.py                 # Session state manager
├── pages/
│   ├── 1_Overview.py
│   ├── 2_Import_Statements.py
│   ├── 3_Trade_Journey_Viewer.py
│   ├── 4_Options_Loss_Breakdown.py
│   ├── 5_Averaging_Down_Analysis.py
│   ├── 6_Rolling_Analysis.py
│   ├── 7_Expiry_Risk_Analysis.py
│   ├── 8_Behavior_Mistake_Analysis.py
│   ├── 9_Recovery_Plan.py
│   └── 10_Settings_Rules.py
├── data/
│   └── sample/
│       └── fidelity_sample.csv      # Sample Fidelity export
├── tests/
│   ├── test_parser.py
│   ├── test_journey_engine.py
│   ├── test_behavior_analyzer.py
│   └── test_pnl_engine.py
├── requirements.txt
├── .env.example
└── .codedna/dna.json                # CodeDNA project identity
```

## Behavior Flags Detected

| Flag | Description |
|------|-------------|
| `averaging_down` | Bought more contracts as position moved against you (≥2 adds) |
| `rolling_loser` | Closed a losing option and opened a further-out replacement |
| `near_expiry_hold` | Held a position within 7 DTE without a clear exit plan |
| `oversized_position` | Position exceeded 10% of account (configurable) |
| `fomo_entry` | Entered after a large underlying move in the same direction |
| `late_exit` | Exited a long option below 20% of max value (let it bleed) |
| `repeat_loser` | Lost money on the same symbol 3+ times |

## Running Tests

```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=term-missing
```

## Extending to Other Brokers

Add a new parser in `app/features/importer/` that produces the same `Transaction` dataclass list. The rest of the pipeline (journey engine, behavior analyzer, P&L engine) is broker-agnostic.

Planned: Schwab, TD Ameritrade/thinkorswim, Robinhood, Interactive Brokers CSV formats.

## Optional AI-Powered Recovery Plan

Set `ANTHROPIC_API_KEY` in `.env` to enable Claude-generated narrative insights in the Recovery Plan page. Without the key, the app runs fully offline with rule-based analysis.

## License

MIT
