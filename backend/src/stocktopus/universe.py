"""Universe configuration — defines the allowed trading instruments and restrictions.

The system starts with SPY only. QQQ is flag-gated. All other instruments are
explicitly excluded to prevent accidental trades outside the research scope.
"""

from dataclasses import dataclass, field

# Instruments explicitly excluded from trading regardless of any signal.
EXCLUDED_CATEGORIES: frozenset[str] = frozenset(
    [
        "penny_stocks",  # price < $5, low liquidity
        "options",  # derivatives, not in scope for v1
        "crypto",  # excluded per plan
        "leveraged_etfs",  # TQQQ, SQQQ, etc.
        "inverse_etfs",  # SH, SPXS, etc. — excluded until short strategies are live-tested
    ]
)

# Known leveraged/inverse ETF tickers to block at the symbol level.
BLOCKED_SYMBOLS: frozenset[str] = frozenset(
    [
        # Leveraged SPY/QQQ variants
        "UPRO",
        "SPXL",
        "SPXS",
        "TQQQ",
        "SQQQ",
        "QLD",
        "QID",
        # Leveraged broad market
        "SSO",
        "SDS",
        "UDOW",
        "SDOW",
        # Inverse S&P
        "SH",
        "SDS",
        "SPXU",
        # Crypto ETFs (until explicitly scoped in)
        "GBTC",
        "IBIT",
        "FBTC",
    ]
)


@dataclass(frozen=True)
class UniverseConfig:
    """Defines which symbols are active and which are flag-gated.

    Attributes:
        primary_symbols: Symbols actively traded and researched.
        gated_symbols: Symbols that can be enabled via feature flag but are off by default.
        penny_stock_threshold: Price below which a symbol is treated as a penny stock.
    """

    primary_symbols: frozenset[str] = field(default_factory=lambda: frozenset(["SPY"]))
    gated_symbols: frozenset[str] = field(default_factory=lambda: frozenset(["QQQ"]))
    penny_stock_threshold: float = 5.0

    def is_allowed(self, symbol: str, *, qqq_enabled: bool = False) -> bool:
        """Return True if the symbol is permitted for trading."""
        if symbol in BLOCKED_SYMBOLS:
            return False
        if symbol in self.primary_symbols:
            return True
        return bool(qqq_enabled and symbol in self.gated_symbols)

    def validate_symbol(self, symbol: str, *, qqq_enabled: bool = False) -> None:
        """Raise ValueError if the symbol is not allowed."""
        if not self.is_allowed(symbol, qqq_enabled=qqq_enabled):
            raise ValueError(
                f"Symbol '{symbol}' is not in the allowed universe. "
                f"Primary: {sorted(self.primary_symbols)}, "
                f"Gated (qqq_enabled={qqq_enabled}): {sorted(self.gated_symbols)}"
            )

    @property
    def all_active_symbols(self) -> frozenset[str]:
        """Return primary symbols only (gated symbols excluded unless flag enabled)."""
        return self.primary_symbols


# Default singleton used throughout the application.
DEFAULT_UNIVERSE = UniverseConfig()
