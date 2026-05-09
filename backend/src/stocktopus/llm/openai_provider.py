"""OpenAI implementation of LLMProvider.

Supports chat completions (gpt-4o, gpt-4o-mini, etc.) with structured JSON output.
Pricing is per-million-tokens and falls back to gpt-4o-mini rates for unknown models.
"""

from __future__ import annotations

import time

from openai import AsyncOpenAI

from stocktopus.providers.llm import LLMMessage, LLMProvider, LLMResponse

# Pricing in USD per 1M tokens (input, output) — update as models change.
_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 5.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}
_DEFAULT_MODEL = "gpt-4o-mini"
_FALLBACK_PRICING = _PRICING["gpt-4o-mini"]


class OpenAIProvider(LLMProvider):
    """LLM adapter backed by OpenAI chat completions API."""

    def __init__(self, api_key: str, default_model: str = _DEFAULT_MODEL) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._default_model = default_model

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        response_schema: dict | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        model = model or self._default_model
        t0 = time.monotonic()

        kwargs: dict = dict(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if response_schema is not None:
            # Structured JSON output — ask the model to respond with valid JSON only.
            kwargs["response_format"] = {"type": "json_object"}

        resp = await self._client.chat.completions.create(**kwargs)
        latency_ms = int((time.monotonic() - t0) * 1000)
        usage = resp.usage
        cost = self._calc_cost(usage.prompt_tokens, usage.completion_tokens, model)

        return LLMResponse(
            content=resp.choices[0].message.content or "",
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )

    def estimated_cost_usd(self, prompt_tokens: int, completion_tokens: int) -> float:
        return self._calc_cost(prompt_tokens, completion_tokens, self._default_model)

    def _calc_cost(self, prompt_tokens: int, completion_tokens: int, model: str) -> float:
        pricing = _PRICING.get(model, _FALLBACK_PRICING)
        return (
            prompt_tokens * pricing["input"] + completion_tokens * pricing["output"]
        ) / 1_000_000
