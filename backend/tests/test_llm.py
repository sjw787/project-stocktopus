"""Unit tests for Phase 5 — LLM analysis layer.

Tests cover:
  - OpenAI / Anthropic provider cost calculations (no real API calls)
  - Research Director JSON parsing and retry logic (mocked LLM)
  - RegimeAssessment schema validation
"""

from __future__ import annotations

import json

import pytest

from stocktopus.features.models import Regime, RegimeAssessment, TradeLean
from stocktopus.llm.anthropic_provider import AnthropicProvider
from stocktopus.llm.openai_provider import OpenAIProvider
from stocktopus.providers.llm import LLMMessage, LLMResponse

# ── OpenAI provider ───────────────────────────────────────────────────────────


def test_openai_cost_gpt4o() -> None:
    provider = OpenAIProvider(api_key="sk-test", default_model="gpt-4o")
    # 1000 input + 500 output with gpt-4o rates ($5/$15 per 1M)
    cost = provider._calc_cost(1000, 500, "gpt-4o")
    expected = (1000 * 5.0 + 500 * 15.0) / 1_000_000
    assert cost == pytest.approx(expected)


def test_openai_cost_gpt4o_mini() -> None:
    provider = OpenAIProvider(api_key="sk-test")
    cost = provider._calc_cost(10_000, 2_000, "gpt-4o-mini")
    expected = (10_000 * 0.15 + 2_000 * 0.60) / 1_000_000
    assert cost == pytest.approx(expected)


def test_openai_cost_unknown_model_uses_fallback() -> None:
    provider = OpenAIProvider(api_key="sk-test")
    cost_known = provider._calc_cost(100, 100, "gpt-4o-mini")
    cost_unknown = provider._calc_cost(100, 100, "gpt-99-future")
    # Unknown model falls back to gpt-4o-mini rates.
    assert cost_known == pytest.approx(cost_unknown)


def test_openai_estimated_cost_usd_uses_default_model() -> None:
    provider = OpenAIProvider(api_key="sk-test", default_model="gpt-4o-mini")
    cost = provider.estimated_cost_usd(1_000, 500)
    expected = provider._calc_cost(1_000, 500, "gpt-4o-mini")
    assert cost == pytest.approx(expected)


# ── Anthropic provider ────────────────────────────────────────────────────────


def test_anthropic_cost_haiku() -> None:
    provider = AnthropicProvider(api_key="sk-test")
    cost = provider._calc_cost(5_000, 1_000, "claude-3-5-haiku-20241022")
    expected = (5_000 * 0.80 + 1_000 * 4.0) / 1_000_000
    assert cost == pytest.approx(expected)


def test_anthropic_cost_sonnet() -> None:
    provider = AnthropicProvider(api_key="sk-test")
    cost = provider._calc_cost(5_000, 1_000, "claude-3-5-sonnet-20241022")
    expected = (5_000 * 3.0 + 1_000 * 15.0) / 1_000_000
    assert cost == pytest.approx(expected)


def test_anthropic_cost_unknown_model_uses_fallback() -> None:
    provider = AnthropicProvider(api_key="sk-test")
    cost_haiku = provider._calc_cost(100, 100, "claude-3-5-haiku-20241022")
    cost_unknown = provider._calc_cost(100, 100, "claude-99-future")
    assert cost_haiku == pytest.approx(cost_unknown)


# ── RegimeAssessment schema ───────────────────────────────────────────────────


def test_regime_assessment_valid() -> None:
    ra = RegimeAssessment(
        regime=Regime.TRENDING_UP,
        lean=TradeLean.LONG,
        confidence=7,
        reasoning="SPY is above VWAP and all SMAs are trending higher.",
        key_risks=["Macro risk from Fed decision", "Elevated VIX"],
        invalidation="Break below VWAP on elevated volume",
    )
    assert ra.confidence == 7
    assert ra.regime == Regime.TRENDING_UP


def test_regime_assessment_confidence_bounds() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RegimeAssessment(
            regime=Regime.RANGING,
            lean=TradeLean.NO_TRADE,
            confidence=11,  # out of range
            reasoning="...",
            key_risks=["x"],
            invalidation="y",
        )

    with pytest.raises(ValidationError):
        RegimeAssessment(
            regime=Regime.RANGING,
            lean=TradeLean.NO_TRADE,
            confidence=0,  # out of range
            reasoning="...",
            key_risks=["x"],
            invalidation="y",
        )


def test_regime_assessment_roundtrip_json() -> None:
    ra = RegimeAssessment(
        regime=Regime.HIGH_VOLATILITY,
        lean=TradeLean.NO_TRADE,
        confidence=3,
        reasoning="VIX spike, avoid.",
        key_risks=["High VIX"],
        invalidation="VIX drops below 20",
    )
    dumped = ra.model_dump(mode="json")
    restored = RegimeAssessment(**dumped)
    assert restored.regime == ra.regime
    assert restored.confidence == ra.confidence


# ── Research Director JSON parsing ────────────────────────────────────────────


def _valid_ra_json() -> str:
    return json.dumps(
        {
            "regime": "trending_up",
            "lean": "long",
            "confidence": 7,
            "reasoning": "SPY is above VWAP with strong RVOL.",
            "key_risks": ["Fed event risk", "Overbought RSI"],
            "invalidation": "Close below VWAP",
        }
    )


def test_parse_regime_assessment_clean_json() -> None:
    from stocktopus.llm.research_director import _parse_regime_assessment

    ra = _parse_regime_assessment(_valid_ra_json())
    assert ra.regime == Regime.TRENDING_UP
    assert ra.lean == TradeLean.LONG
    assert ra.confidence == 7


def test_parse_regime_assessment_strips_markdown_fences() -> None:
    from stocktopus.llm.research_director import _parse_regime_assessment

    fenced = f"```json\n{_valid_ra_json()}\n```"
    ra = _parse_regime_assessment(fenced)
    assert ra.regime == Regime.TRENDING_UP


def test_parse_regime_assessment_strips_plain_fences() -> None:
    from stocktopus.llm.research_director import _parse_regime_assessment

    fenced = f"```\n{_valid_ra_json()}\n```"
    ra = _parse_regime_assessment(fenced)
    assert ra.confidence == 7


def test_parse_regime_assessment_invalid_json_raises() -> None:
    from stocktopus.llm.research_director import _parse_regime_assessment

    with pytest.raises(json.JSONDecodeError):
        _parse_regime_assessment("not json at all")


def test_parse_regime_assessment_invalid_schema_raises() -> None:
    from pydantic import ValidationError

    from stocktopus.llm.research_director import _parse_regime_assessment

    bad = json.dumps({"regime": "trending_up", "lean": "long", "confidence": 99})
    with pytest.raises((ValidationError, Exception)):
        _parse_regime_assessment(bad)


# ── LLM provider interface contract ──────────────────────────────────────────


def test_llm_message_role_values() -> None:
    msg = LLMMessage(role="system", content="You are a research director.")
    assert msg.role == "system"
    msg2 = LLMMessage(role="user", content="Analyze SPY.")
    assert msg2.role == "user"


def test_llm_response_has_latency_ms() -> None:
    resp = LLMResponse(
        content='{"regime": "trending_up"}',
        model="gpt-4o-mini",
        prompt_tokens=500,
        completion_tokens=200,
        cost_usd=0.0002,
        latency_ms=342,
    )
    assert resp.latency_ms == 342
