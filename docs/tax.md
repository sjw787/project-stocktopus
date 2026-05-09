# Tax Awareness — Design Notes

> **Disclaimer:** Stocktopus surfaces tax-relevant signals to inform trade decisions.
> It does **not** provide tax advice. Consult a qualified tax professional.

## Scope

- **v1:** United States federal tax rules.
- **Deferred:** State-specific handling.

## Key Rules Modeled

### Short-Term vs Long-Term Capital Gains

- Positions held **≤ 365 days** → short-term capital gains (STCG), taxed as ordinary income.
- Positions held **> 365 days** → long-term capital gains (LTCG), taxed at preferential rates.
- For an intraday system holding positions < 1 day, virtually all trades generate STCG.

### Wash-Sale Rule (IRC § 1091)

- If you sell a position at a loss and buy a "substantially identical" security within **30 calendar days** before or after the sale, the loss is disallowed.
- The disallowed loss is added to the cost basis of the replacement shares.
- **System behavior:** When a candidate entry would trigger a wash-sale on a recent loser in the same symbol, the required LLM confidence threshold is raised by a configurable multiplier (default: 1.5×).

## Data Model

| Field | Table | Purpose |
|-------|-------|---------|
| `lot_id` | `trade_lots` | Unique lot identifier |
| `symbol` | `trade_lots` | Security symbol |
| `entry_date` | `trade_lots` | Holding period start |
| `exit_date` | `trade_lots` | Holding period end (null if open) |
| `cost_basis` | `trade_lots` | Entry cost basis |
| `proceeds` | `trade_lots` | Exit proceeds |
| `realized_pnl` | `trade_lots` | Realized gain/loss |
| `wash_sale_flag` | `trade_lots` | Whether the loss was disallowed |
| `stcg_ltcg` | `trade_lots` | `"stcg"` or `"ltcg"` classification |
| `disallowed_loss` | `trade_lots` | Loss amount added to replacement basis |

## Form 8949 Export

The system generates an annual CSV compatible with IRS Form 8949:

```
Description, Date Acquired, Date Sold, Proceeds, Cost Basis, Adjustments, Gain/Loss
SPY (lot #123), 2024-01-15, 2024-01-15, $502.50, $500.00, $0.00, $2.50
```

Export available under **Settings → Tax → Export Form 8949 (Year YYYY)**.

## LLM Tax Context Block

The Research Director prompt receives a `tax_context` block at decision time:

```json
{
  "open_lots": [
    {"symbol": "SPY", "days_held": 0, "unrealized_pnl": 1.25, "classification": "stcg"}
  ],
  "wash_sale_risk": false,
  "recent_losses": []
}
```

The LLM may reference this context in its `key_risks` or `reasoning` output. It does **not** make tax decisions — it flags risk for human review.

## State Tax (Deferred)

State-level tax handling (rates, residency rules, etc.) is deferred. The `trade_lots` data model is designed to accommodate state tax calculations when added.
