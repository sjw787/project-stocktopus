"""Slippage and commission models for backtesting.

All models accept entry/exit price and quantity and return a float representing
the total friction cost in dollars.

Design principles:
- Alpaca paper/live has $0 commission but SEC/FINRA/TAF fees apply on sells.
- Slippage is modelled as a fixed bps component plus a size-aware component.
- Fills are always at "next-bar open" (caller's responsibility to pass correct price).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrictionModel:
    """Combined slippage + commission model.

    Parameters
    ----------
    slippage_bps:
        Fixed one-way slippage in basis points (applied to both entry and exit).
        Default 2 bps ≈ realistic SPY market-order slippage on paper.
    size_slippage_pct:
        Extra slippage as a fraction of shares — approximates market impact for
        larger orders. Default 0 (negligible for small retail size).
    commission_per_share:
        Fixed per-share commission. Alpaca = $0.
    sec_fee_rate:
        SEC Section 31 fee on sells (multiply by notional). ≈ $0.0000278/dollar.
    finra_taf_rate:
        FINRA TAF fee on sells (per share). ≈ $0.000166/share, capped.
    finra_taf_cap:
        Maximum FINRA TAF per transaction.
    """

    slippage_bps: float = 2.0
    size_slippage_pct: float = 0.0
    commission_per_share: float = 0.0
    sec_fee_rate: float = 0.0000278
    finra_taf_rate: float = 0.000166
    finra_taf_cap: float = 8.30

    def entry_cost(self, price: float, qty: float) -> float:
        """Total friction cost to enter a position."""
        notional = abs(price * qty)
        slippage = notional * (self.slippage_bps / 10_000)
        size_slip = abs(qty) * self.size_slippage_pct
        commission = abs(qty) * self.commission_per_share
        return slippage + size_slip + commission

    def exit_cost(self, price: float, qty: float) -> float:
        """Total friction cost to exit a position (sell-side fees included)."""
        notional = abs(price * qty)
        slippage = notional * (self.slippage_bps / 10_000)
        size_slip = abs(qty) * self.size_slippage_pct
        commission = abs(qty) * self.commission_per_share
        sec_fee = notional * self.sec_fee_rate
        finra_taf = min(abs(qty) * self.finra_taf_rate, self.finra_taf_cap)
        return slippage + size_slip + commission + sec_fee + finra_taf

    def total_round_trip(self, entry_price: float, exit_price: float, qty: float) -> float:
        """Total round-trip friction (entry + exit)."""
        return self.entry_cost(entry_price, qty) + self.exit_cost(exit_price, qty)

    @classmethod
    def zero(cls) -> FrictionModel:
        """No friction — useful for sanity-checking strategy logic."""
        return cls(
            slippage_bps=0,
            size_slippage_pct=0,
            commission_per_share=0,
            sec_fee_rate=0,
            finra_taf_rate=0,
            finra_taf_cap=0,
        )

    @classmethod
    def realistic_alpaca(cls) -> FrictionModel:
        """Realistic Alpaca frictions: 2 bps slippage + SEC/FINRA fees."""
        return cls()  # all defaults are calibrated for Alpaca
