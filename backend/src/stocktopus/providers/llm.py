"""LLM provider — pluggable adapter for language model services."""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: str  # "system" | "user" | "assistant"
    content: str


class LLMResponse(BaseModel):
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


class LLMProvider(ABC):
    """Abstract provider for LLM chat completions.

    Implementations: OpenAIProvider, AnthropicProvider (Phase 5).
    Extend for Bedrock, Ollama, etc. without changing call sites.
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        response_schema: dict | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Run a chat completion. Pass response_schema for structured JSON output."""
        ...

    @abstractmethod
    def estimated_cost_usd(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Return estimated cost in USD for the given token counts."""
        ...
