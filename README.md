# Stocktopus

AI-assisted trading research and execution system for SPY (and later QQQ).

> **Research system first, trading bot second.** The LLM acts as a research director
> assessing market regime, sentiment, and risk — not a price oracle.

## ⚠️ Disclaimer

This software is for educational and research purposes only. It does **not** constitute
financial or investment advice. Trading involves significant risk of loss. See
`docs/tax.md` for tax considerations. Always consult qualified professionals before
risking real capital.

## Architecture

```
Frontend (TanStack Start)
         ↓ REST / WS
   FastAPI Gateway
   ↓           ↓           ↓
Ingestion   Research   Execution
Service     Service    Service
         ↓
  Postgres/Timescale · Redis · Parquet
         ↓
  Backtest / Eval Harness
```

Pipeline per signal:
**Market Data → Feature Extraction → LLM Analysis → Trade Thesis → Risk Filter → (Paper|Live) Execution → Performance Tracking**

## Stack

| Layer | Choice |
|-------|--------|
| Backend | Python 3.12 + FastAPI, managed by `uv` |
| Frontend | TanStack Start + React, `npm` |
| Database | PostgreSQL + TimescaleDB (candles), Redis (cache/queue) |
| LLM | OpenAI + Anthropic behind `LLMProvider` adapter |
| Data/Broker | Alpaca primary, pluggable for Polygon, Finnhub, etc. |
| Backtesting | VectorBT (sweeps) + Backtrader (event-driven) |

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Python 3.12+ (for local dev without Docker)
- Node 20+ (for frontend)
- `uv` — `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env and add your API keys (Alpaca, OpenAI or Anthropic, Finnhub)
```

### 2. Start infrastructure

```bash
docker-compose up -d db redis
```

### 3. Run the backend locally

```bash
cd backend
uv sync --dev
uv run uvicorn stocktopus.main:app --reload
```

### 4. Verify

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0"}
```

## Development

```bash
cd backend

# Install all deps (including dev)
uv sync --dev

# Run tests
uv run pytest

# Lint + format
uv run ruff check src tests
uv run ruff format src tests

# Type check
uv run mypy src
```

### Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
```

## Phases

See `PLAN.md` for the full roadmap. See `docs/evaluation.md` for phase-gate criteria.

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Project bootstrap | 🚧 In Progress |
| 1 | Evaluation charter | ⏳ Pending |
| 2 | Universe scope config | ⏳ Pending |
| 3 | Data ingestion layer | ⏳ Pending |
| 4 | Feature extraction | ⏳ Pending |
| 5 | LLM analysis layer | ⏳ Pending |
| 6 | Opening momentum strategy | ⏳ Pending |
| 7 | Backtesting harness | ⏳ Pending |
| 8 | Paper trading | ⏳ Pending |
| 9 | Tiny real money | ⏳ Pending |

## Docs

- `PLAN.md` — Full implementation plan with confirmed assumptions
- `docs/evaluation.md` — Evaluation charter and phase-gate criteria
- `docs/tax.md` — Tax awareness design notes (US federal)
