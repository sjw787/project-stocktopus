# Evaluation Charter

## Target Metric

> "Can the system identify statistically favorable short-term setups better than random chance after fees?"

This is the governing question for every experiment, strategy, and model change.

## Primary KPIs

| KPI | Minimum Bar | Notes |
|-----|-------------|-------|
| Win Rate | > 40% | A 40% WR can be profitable with good R:R |
| Expectancy | > $0 per trade | Must be positive after slippage + fees |
| Sharpe Ratio | > 1.0 | Annualized, on daily equity returns |
| Max Drawdown | < 15% | From peak equity |
| Profit Factor | > 1.25 | Gross profit / gross loss |
| Hit Rate by Regime | Tracked per regime | No single regime should carry all edge |

## Evaluation Rules

1. **All metrics are computed after realistic frictions** — slippage, SEC/TAF fees, and entry latency.
2. **Walk-forward validation is mandatory** — never evaluate on the training window.
3. **Per-regime breakdown is mandatory** — report trending, mean-reverting, high-vol, and low-vol regimes separately.
4. **OOS split** — the final 20% of historical data is held out and touched only once, for final validation.
5. **Minimum sample size** — no strategy advances with fewer than 100 trades in the evaluation period.
6. **Edge must survive regime diversity** — a strategy that only works in one regime is not viable.

## Phase Gates

### Phase 6 → Phase 7
- 30 days of clean SPY 1m/5m data with zero RTH gaps.
- LLM produces schema-valid `RegimeAssessment` on 100 historical decision points.
- Feature snapshots round-trip correctly (serialize → deserialize → same values).

### Phase 7 → Phase 8
- Backtest over 3 years shows positive expectancy after realistic frictions.
- Per-regime breakdown passes — no single regime carries the edge.
- Walk-forward and OOS splits are both positive.

### Phase 8 → Phase 9
- ≥ 100 paper trades completed.
- ≥ 3 distinct market regimes represented in the paper-trade set.
- Live paper distribution is within drift tolerance of the backtest distribution.

## Experiment Log Format

Each experiment must record:

```yaml
id: exp-<YYYYMMDD>-<slug>
hypothesis: "..."
strategy_version: "..."
parameters: {}
evaluation_period:
  start: YYYY-MM-DD
  end: YYYY-MM-DD
  regimes_covered: []
results:
  win_rate: 0.0
  expectancy_per_trade: 0.0
  sharpe: 0.0
  max_drawdown: 0.0
  profit_factor: 0.0
  trade_count: 0
  per_regime: {}
conclusion: "..."
next_steps: "..."
```

Artifacts live under `runs/<experiment-id>/`.
