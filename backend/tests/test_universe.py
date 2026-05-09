"""Tests for universe configuration."""

import pytest

from stocktopus.universe import DEFAULT_UNIVERSE, UniverseConfig


def test_spy_is_allowed() -> None:
    assert DEFAULT_UNIVERSE.is_allowed("SPY") is True


def test_qqq_blocked_by_default() -> None:
    assert DEFAULT_UNIVERSE.is_allowed("QQQ") is False


def test_qqq_allowed_when_gated_enabled() -> None:
    assert DEFAULT_UNIVERSE.is_allowed("QQQ", qqq_enabled=True) is True


def test_leveraged_etfs_blocked() -> None:
    for sym in ("TQQQ", "UPRO", "SPXL", "SQQQ"):
        assert DEFAULT_UNIVERSE.is_allowed(sym) is False, f"{sym} should be blocked"


def test_unknown_symbol_blocked() -> None:
    assert DEFAULT_UNIVERSE.is_allowed("TSLA") is False


def test_validate_symbol_passes_for_spy() -> None:
    DEFAULT_UNIVERSE.validate_symbol("SPY")  # should not raise


def test_validate_symbol_raises_for_blocked() -> None:
    with pytest.raises(ValueError, match="not in the allowed universe"):
        DEFAULT_UNIVERSE.validate_symbol("TQQQ")


def test_all_active_symbols_contains_spy() -> None:
    assert "SPY" in DEFAULT_UNIVERSE.all_active_symbols


def test_all_active_symbols_does_not_contain_qqq() -> None:
    assert "QQQ" not in DEFAULT_UNIVERSE.all_active_symbols


def test_custom_universe() -> None:
    cfg = UniverseConfig(
        primary_symbols=frozenset(["SPY", "QQQ"]),
        gated_symbols=frozenset(),
    )
    assert cfg.is_allowed("QQQ") is True
    assert cfg.is_allowed("AAPL") is False
