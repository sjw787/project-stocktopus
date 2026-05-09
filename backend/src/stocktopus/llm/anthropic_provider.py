"""Anthropic implementation of LLMProvider.

Supports Messages API (claude-3-5-haiku, claude-3-5-sonnet, claude-3-opus, etc.).
System prompt is extracted from the messages list if present (Anthropic uses a top-level
`system` param rather than a system message in the messages array).
"""

from __future__ import annotations

import time

from anthropic import AsyncAnthropic

from stocktopus.providers.llm import LLMMessage, LLMProvider, LLMResponse

_PRICING: dict[str, dict[str, float]] = {
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.0},
    "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
}
_DEFAULT_MODEL = "claude-3-5-haiku-20241022"
_FALLBACK_PRICING = _PRICING["claude-3-5-haiku-20241022"]


class AnthropicProvider(LLMProvider):
    """LLM adapter backed by the Anthropic Messages API."""

    def __init__(self, api_key: str, default_model: str = _DEFAULT_MODEL) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
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

        # Anthropic splits system content from the messages array.
        system_parts: list[str] = []
        user_messages: list[dict] = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
            else:
                user_messages.append({"role": m.role, "content": m.content})

        # If JSON output is requested, append a reminder in the system prompt.
        if response_schema is not None:
            system_parts.append(
                "Respond with valid JSON only. Do not include markdown fences."
            )

        kwargs: dict = dict(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=user_messages,
        )
        if system_parts:
            kwargs["system"] = "\n\n".join(system_parts)

        resp = await self._client.messages.create(**kwargs)
        latency_ms = int((time.monotonic() - t0) * 1000)
        usage = resp.usage
        cost = self._calc_cost(usage.input_tokens, usage.output_tokens, model)

        return LLMResponse(
            content=resp.content[0].text,
            model=model,
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
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
