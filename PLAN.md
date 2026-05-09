# Stocktopus — Implementation Plan

## Problem Statement
Build an AI-assisted trading research and execution system for SPY (later QQQ) that prioritizes **trade-selection quality over prediction**. The LLM acts as a "research director" that assesses regime, sentiment, and risk — not a price oracle. The system progresses through nine phases from infrastructure to real-money execution, with paper trading as a hard gate before any capital is risked.

## Guiding Principles
- **Research system first, trading bot second.** Every component must support hypothesis testing and evaluation before automation.
- **LLM scope is narrow.** It classifies regime, summarizes context, scores risk — it does not predict prices.
- **Capital preservation > frequency.** Filters that *reject* trades are as valuable as those that find them.
- **Provider-agnostic adapters.** Alpaca first, but data/LLM/broker layers are pluggable so Polygon, Finnhub, Bedrock, etc. can slot in later.
- **Single-user now, multi-user-ready.** No auth in v1, but data models include a `user_id` and secrets are looked up via an injectable provider so per-user BYO-keys can be added without refactor.

## Stack Decisions
| Layer | Choice | Notes |
|---|---|---|
| Backend | Python + FastAPI | Async, typed, great for data work |
| Frontend | TanStack Start + React | Dashboards, charts, trade journal |
| Charts | Plotly (server-rendered) + lightweight-charts (client) | Plotly for analytics, LWC for live |
| Data analysis | Pandas, NumPy, Polars (where hot) | |
| Market data + Broker | Alpaca (primary) behind `MarketDataProvider` and `BrokerProvider` interfaces | Polygon/AlphaVantage/Finnhub addable later |
| News/Sentiment | Finnhub + NewsAPI behind `NewsProvider` interface | |
| LLM | OpenAI + Anthropic behind `LLMProvider` adapter | Bedrock/Ollama addable later |
| Backtesting | VectorBT (vectorized sweeps) + Backtrader (event-driven realism) | |
| Storage | PostgreSQL (relational) + TimescaleDB extension (candles) + Parquet (cold/raw) | |
| Cache/Queue | Redis (cache, rate-limit, simple jobs) | |
| Orchestration | APScheduler initially; Celery/Arq if it grows | |
| Secrets | `.env` locally; abstract behind `SecretsProvider` for future per-user vault | |
| Deploy target | Local dev → single VPS/Docker Compose → cloud later | |

## Confirmed Planning Assumptions
- **Budget:** keep v1 operating costs under roughly **$50/month** across market data, news APIs, LLM calls, and infrastructure.
- **Historical data target:** use a **3-year** lookback for initial backtesting.
- **Trading session:** use regular market hours only for initial strategy evaluation, paper trading, and live trading.
- **Strategy direction:** live/paper implementation starts **long-only**, while the backtest harness may evaluate short-side variants for research.
- **Tooling:** backend uses **uv**; frontend uses **npm**.
- **Market breadth v1:** use low-cost proxies first: sector ETFs, SPY, QQQ, IWM, DIA, and VIX.
- **Morning sentiment window:** prior regular-session close through 9:30am ET.
- **LLM failure policy:** fail closed; no new trades without a valid current LLM assessment.
- **Scheduled event policy:** allow trades during FOMC/CPI/NFP/Fed-speech windows with widened stops only when position size is reduced so max dollar risk stays unchanged. Default event window is 30 minutes before through 60 minutes after the event.
- **Tax scope:** start with United States federal tax awareness, with state-specific handling added later.
- **Tiny-live caps:** default to `max_position_usd = 50`, `max_daily_loss = 25`, `no_overnight_holds = true`, `no_leverage = true`.

---

## Architecture

```
                 ┌─────────────────────────────────────┐
                 │        Frontend (TanStack)          │
                 │  dashboards · journal · controls    │
                 └──────────────────┬──────────────────┘
                                    │ REST / WS
                 ┌──────────────────▼──────────────────┐
                 │           FastAPI Gateway           │
                 └──────┬──────────┬──────────┬────────┘
                        │          │          │
        ┌───────────────▼──┐  ┌────▼─────┐  ┌─▼────────────┐
        │ Ingestion Service│  │ Research │  │ Execution    │
        │ candles · news · │  │ Service  │  │ Service      │
        │ macro · VIX      │  │ (LLM +   │  │ (paper/live, │
        └─────┬────────────┘  │ features)│  │  risk gate)  │
              │               └────┬─────┘  └──────┬───────┘
              ▼                    ▼               ▼
        ┌─────────────────────────────────────────────────┐
        │  Storage:  Postgres/Timescale · Redis · Parquet │
        └─────────────────────────────────────────────────┘
                                    │
                            ┌───────▼────────┐
                            │ Backtest /     │
                            │ Eval Harness   │
                            └────────────────┘
```

Pipeline per signal:
**Market Data → Feature Extraction → LLM Analysis → Trade Thesis → Risk Filter → (Paper|Live) Execution → Performance Tracking → Journal/Review**

---

## Phased Roadmap

### Phase 0 — Project Bootstrap
- Monorepo layout: `backend/`, `frontend/`, `infra/`, `notebooks/`, `docs/`.
- `pyproject.toml` managed by uv, pre-commit (ruff, black, mypy), pytest.
- Docker Compose: postgres+timescale, redis, backend, frontend.
- CI: lint + test on PR.
- `.env.example`, secrets abstraction, structured logging (loguru/structlog).

### Phase 1 — Define the Goal (instrumentation, not code)
- Write the **Evaluation Charter**: target metric is *"edge over random after fees, on SPY intraday setups."*
- Define KPIs: win rate, expectancy, Sharpe, max DD, profit factor, hit-rate-by-regime.
- Create `docs/evaluation.md` documenting how every experiment will be judged.

### Phase 2 — Narrow Market Scope
- Universe config: `SPY` only initially; `QQQ` flag-gated.
- Hardcoded exclusions in config: penny stocks, options, crypto, leveraged ETFs.
- Trading calendar (pandas-market-calendars) for sessions, halts, early closes.

### Phase 3 — Data Ingestion Layer
**3a. Price/Volume**
- `MarketDataProvider` interface; `AlpacaMarketData` implementation.
- Pull 1m and 5m candles, volume, VWAP, premarket bars.
- Backfill job + incremental live ingest (websocket).
- Derived series: SMA20/50/200, daily/yearly MAs, ATR, RVOL.
- Persist to TimescaleDB hypertable `candles(symbol, tf, ts, ohlcv, vwap)`.

**3b. News/Sentiment**
- `NewsProvider` interface; Finnhub + NewsAPI implementations.
- Tag stories: macro, Fed, CPI/NFP, earnings, geopolitics.
- Store raw + normalized in `news_events`. Dedup by URL+title hash.

**3c. Market Context**
- VIX, SPY gap %, and low-cost breadth proxies: sector ETFs, SPY, QQQ, IWM, DIA.
- Computed every minute into `market_context` table.

**3d. Quality**
- Data integrity tests (no gaps in RTH, monotonic timestamps, sane OHLC).
- Backfill CLI: `stocktopus ingest backfill --symbol SPY --from 2018-01-01`.

### Phase 4 — Feature Extraction & Architecture
- Pure-function `features/` module: each feature has a name, inputs, output, and unit test.
- Feature snapshot at decision time → `feature_snapshots` row (immutable, audit-friendly).
- Define `TradeThesis` and `RegimeAssessment` Pydantic models — the contract between the LLM layer and the rest of the system.

### Phase 5 — LLM Analysis Layer (narrow scope)
- `LLMProvider` adapter (OpenAI + Anthropic), with retries, cost tracking, prompt-version pinning.
- Implement the **Research Director** prompt from the outline as a versioned template under `prompts/research_director/v1.md`.
- Output is a *structured* `RegimeAssessment`: regime label, long/short/no-trade lean, confidence 1–10, reasoning, key risks, invalidation conditions.
- **Strict JSON schema validation**; reject and retry on malformed output.
- Log every prompt/response pair with input feature snapshot for later replay.
- **Tax-awareness hook**: include holding-period and wash-sale context in the prompt; flag when a setup would realize STCG vs LTCG. (See "Tax Considerations" below.)

### Phase 6 — First Strategy: Opening Momentum
Configurable rules:
- SPY gap up > 0.5% (configurable threshold)
- Opening volume elevated (RVOL > 1.5)
- Price above VWAP after first 5m
- News sentiment net-positive using the prior regular-session close through 9:30am ET.
- Entry: after first pullback that holds VWAP
- Stop loss: 0.5%
- Take profit: 1% baseline; **dynamic extension** to 1.5–2% when LLM regime confidence ≥ 8 *and* trend strength signals confirm. All thresholds live in `strategies/opening_momentum.yaml`.
- Live/paper trading starts long-only; short-side variants may be evaluated in backtests for research.
- Strategy interface: `Strategy.evaluate(context) -> Optional[TradeThesis]` so future strategies plug in.

### Phase 7 — Backtesting & Evaluation Harness
- VectorBT for parameter sweeps; Backtrader for realistic event-driven runs.
- **Realism requirements:**
  - Slippage model (bps + size-aware)
  - Commissions (Alpaca = $0, but model SEC/TAF fees)
  - Realistic fills (next-bar open, not signal-bar close)
  - Latency simulation (configurable)
  - Failed/partial fills
- Reports: equity curve, win rate, expectancy, max DD, Sharpe, profit factor, **per-regime breakdown**.
- Walk-forward + out-of-sample splits enforced by harness.
- HTML report artifact per backtest run, stored under `runs/<id>/`.

### Phase 8 — Paper Trading
- Wire strategy + risk filter to Alpaca paper account.
- Minimum gate before Phase 9: **100 trades across 3+ market regimes**, tracked automatically by the regime classifier from Phase 5.
- Per-trade journal: AI confidence, entry reason, market regime, outcome, post-mortem notes.
- Daily/weekly auto-generated review: deviations between expected (backtest) and actual (paper) distributions.
- Drift alarm: if live distribution diverges from backtest beyond threshold, auto-pause.

### Phase 9 — Tiny Real Money
- Hard config caps: `max_position_usd = 50`, `max_daily_loss = 25`, `no_overnight_holds = true`, `no_leverage = true`.
- Two-key promotion: paper→live requires both a config flag *and* a CLI confirmation.
- Kill switch: single endpoint and CLI command that flattens and disables trading.
- Real-money runs share **all** code paths with paper; only the broker adapter changes.
- Continuous shadow-paper run alongside live for divergence detection.

### Risk & Safety Layer (cross-cutting, present from Phase 5+)
- Pre-trade checks: position size, daily loss, max trades/day, news-blackout windows (FOMC, CPI), volatility ceilings, correlation caps.
- Scheduled high-impact event windows default to 30 minutes before through 60 minutes after the event. Trades may be allowed only with widened stops and reduced position size so max dollar risk stays unchanged.
- LLM analysis failures fail closed: no new trades are allowed without a valid current assessment.
- All checks are configurable and unit-tested.
- Every rejected trade is logged with reason — rejection data is itself a research input.

### Tax Considerations (cross-cutting)
- Track realized P&L by lot, holding period (STCG vs LTCG threshold), and wash-sale windows (30 days).
- Decision tree input: when a candidate trade would trigger a wash sale or convert LTCG-eligible lots to STCG, raise the required edge bar (configurable multiplier).
- Tax logic initially targets United States federal rules; state-specific handling is deferred.
- Generate annual `Form 8949`-friendly CSV export.
- **Disclaimer:** the system surfaces tax-aware *signals*; it is not tax advice. Documented in `docs/tax.md`.

### Frontend (built incrementally alongside backend phases)
- Use npm for frontend package management.
- **MVP screens (during Phase 3–5):** ingestion health, latest candles, news feed, regime assessment card.
- **Strategy + backtest screens (Phase 6–7):** strategy config editor, backtest runner + report viewer.
- **Paper/live screens (Phase 8–9):** live positions, trade journal, kill switch, P&L dashboard, tax view.
- Auth-ready scaffolding (route guards exist, just no-op in single-user mode).

---

## Key Risks & Mitigations
| Risk | Mitigation |
|---|---|
| Overfitting to backtest | Walk-forward, OOS splits, regime-stratified metrics, paper-trade gate |
| LLM hallucination | Strict JSON schema, "do not invent data" prompt rules, refusal-allowed outputs, replay logs |
| Data quality gaps | Integrity tests, multiple providers behind same interface, fail-closed on missing data |
| Cost creep (LLM + data APIs) | Per-call cost tracking, daily budget caps with circuit breakers |
| Emotional/operator error in live phase | Hard config caps, kill switch, two-key promotion, shadow-paper comparison |
| Wash sale / STCG surprises | Lot tracking from day one, tax-aware filter in risk layer |

---

## Success Criteria (to advance between phases)
- **→ Phase 6:** Phase 3–5 ingest 30 days of clean SPY data with zero gaps; LLM produces schema-valid regime assessments on 100 historical decision points.
- **→ Phase 7:** Strategy implementation passes unit tests and produces deterministic signals on fixture data.
- **→ Phase 8:** Backtest over 3 years shows positive expectancy after realistic frictions; per-regime breakdown shows no single regime carrying the result.
- **→ Phase 9:** ≥100 paper trades across ≥3 regimes; live distribution within drift tolerance of backtest distribution.

---

## Out of Scope (explicit non-goals for v1)
- Options, crypto, leveraged ETFs, penny stocks
- Overnight holds (initially)
- Multi-user auth (architected for, not built)
- Mobile app
- Social/copy-trading features
- Reinforcement learning / custom-trained price models

---

## Open Questions to Resolve Before Phase 6
- Whether to add true NYSE/Nasdaq breadth data after the low-cost proxy model is working.
- Exact volatility/risk formula for sizing event-window widened-stop trades.
