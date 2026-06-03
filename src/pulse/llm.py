"""OpenAI-compatible LLM with provider failover.

Ported from perso/iris — simplified (no vision routing, no local image inlining).
"""

from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import openai
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import Config, ProviderConfig
from .text import strip_reasoning


# --- usage tracking --------------------------------------------------------


@dataclass
class UsageTracker:
    """Accumulates token + cost usage across LLM calls within a scope."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    by_provider: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(
        self,
        *,
        provider: ProviderConfig,
        prompt: int,
        completion: int,
    ) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        call_cost = (
            (prompt / 1_000_000.0) * provider.prompt_cost_per_million
            + (completion / 1_000_000.0) * provider.completion_cost_per_million
        )
        self.cost_usd += call_cost
        self.calls += 1
        slot = self.by_provider.setdefault(
            f"{provider.name}:{provider.model}",
            {"prompt": 0.0, "completion": 0.0, "cost": 0.0, "calls": 0.0},
        )
        slot["prompt"] += prompt
        slot["completion"] += completion
        slot["cost"] += call_cost
        slot["calls"] += 1


_usage_tracker: ContextVar[UsageTracker | None] = ContextVar(
    "pulse_usage_tracker", default=None
)


@asynccontextmanager
async def usage_scope():
    """Async context manager that captures all LLM usage in its body.

    Uses contextvars so concurrent runs / chats stay isolated.
    """
    tracker = UsageTracker()
    token = _usage_tracker.set(tracker)
    try:
        yield tracker
    finally:
        _usage_tracker.reset(token)


def _record_usage(provider: ProviderConfig, prompt: int, completion: int) -> None:
    tracker = _usage_tracker.get()
    if tracker is None:
        return
    tracker.add(provider=provider, prompt=prompt, completion=completion)

log = structlog.get_logger()

# Transient errors retried per-provider by tenacity. RateLimitError is handled
# separately at the failover level (it respects the server's Retry-After and
# waits out a gateway-wide throttle instead of burning through providers).
RETRYABLE = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
)

# How patiently we ride out a fully-throttled gateway (every provider 429s at
# once). The gateway tells us "retry in Ns"; we honor it, up to a cap.
_RATE_LIMIT_ROUNDS = 5
_RATE_LIMIT_MAX_WAIT = 20.0


def _retry_after_seconds(e: Exception) -> float | None:
    """The server's suggested wait from a 429: the Retry-After header, else a
    'Retry in 3s'-style hint in the message. None if not specified."""
    resp = getattr(e, "response", None)
    headers = getattr(resp, "headers", None)
    if headers:
        ra = headers.get("retry-after") or headers.get("Retry-After")
        if ra:
            try:
                return float(ra)
            except (TypeError, ValueError):
                pass
    m = re.search(r"retry\s+in\s+(\d+(?:\.\d+)?)\s*s", str(e), re.IGNORECASE)
    return float(m.group(1)) if m else None


def _throttle_wait(retry_afters: list[float]) -> float:
    """How long to sleep before re-trying the whole provider chain — the soonest
    a provider said it'd be ready, clamped, plus a small buffer."""
    return min(max(min(retry_afters), 1.0), _RATE_LIMIT_MAX_WAIT) + 0.5


@dataclass
class Message:
    role: str
    content: "str | list[dict[str, Any]]"


class AllProvidersFailed(Exception):
    pass


class LLM:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._clients: dict[str, openai.AsyncOpenAI] = {}

    def _client(self, provider: ProviderConfig) -> openai.AsyncOpenAI:
        key = f"{provider.base_url}|{provider.api_key_env or ''}"
        if key in self._clients:
            return self._clients[key]
        api_key = self.config.resolved_api_key(provider) or "sk-noop"
        client = openai.AsyncOpenAI(
            base_url=provider.base_url,
            api_key=api_key,
            timeout=provider.timeout,
            max_retries=0,
        )
        self._clients[key] = client
        return client

    def _select_providers(
        self, provider_name: str | None, model_override: str | None
    ) -> list[ProviderConfig]:
        base = list(self.config.llm.providers)
        if provider_name and model_override:
            for p in base:
                if p.name == provider_name and p.model == model_override:
                    return [p]
            template = next((p for p in base if p.name == provider_name), None)
            if template is None:
                raise AllProvidersFailed(f"unknown provider '{provider_name}'")
            return [template.model_copy(update={"model": model_override})]
        if provider_name:
            matches = [p for p in base if p.name == provider_name]
            if not matches:
                raise AllProvidersFailed(f"unknown provider '{provider_name}'")
            return matches
        return base

    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        msg = await self.complete_chat(
            [{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )
        return strip_reasoning(msg.get("content") or "")

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        candidates = self._select_providers(provider, model)
        errors: list[tuple[str, str]] = []
        for round_i in range(_RATE_LIMIT_ROUNDS):
            errors = []
            retry_afters: list[float] = []
            all_rate_limited = True
            for prov in candidates:
                try:
                    return await self._complete_one(prov, messages, tools, temperature, max_tokens, json_mode)
                except openai.RateLimitError as e:
                    ra = _retry_after_seconds(e) or 3.0
                    retry_afters.append(ra)
                    errors.append((f"{prov.name}:{prov.model}", repr(e)))
                    log.warning("provider_rate_limited", provider=prov.name, model=prov.model, retry_after=ra)
                except Exception as e:
                    all_rate_limited = False
                    log.warning("provider_failed", provider=prov.name, error=repr(e))
                    errors.append((f"{prov.name}:{prov.model}", repr(e)))
            # every provider failed this round; if it was purely throttling, wait
            # out the server's suggested delay and try the whole chain again
            if all_rate_limited and retry_afters and round_i < _RATE_LIMIT_ROUNDS - 1:
                wait_s = _throttle_wait(retry_afters)
                log.info("all_providers_throttled_backoff", wait=round(wait_s, 1), round=round_i + 1)
                await asyncio.sleep(wait_s)
                continue
            break
        raise AllProvidersFailed(f"all {len(errors)} attempts failed: {errors}")

    async def _complete_one(
        self,
        provider: ProviderConfig,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        max_tokens: int | None,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        client = self._client(provider)
        temp = temperature if temperature is not None else self.config.llm.default_temperature
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(provider.max_retries + 1),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(RETRYABLE),
            reraise=True,
        ):
            with attempt:
                log.info(
                    "llm_call",
                    provider=provider.name,
                    model=provider.model,
                    n_messages=len(messages),
                    n_tools=len(tools) if tools else 0,
                )
                kwargs: dict[str, Any] = {
                    "model": provider.model,
                    "messages": messages,
                    "temperature": temp,
                }
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                if tools:
                    kwargs["tools"] = tools
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                resp = await client.chat.completions.create(**kwargs)
                if resp.usage:
                    _record_usage(
                        provider,
                        prompt=resp.usage.prompt_tokens or 0,
                        completion=resp.usage.completion_tokens or 0,
                    )
                msg = resp.choices[0].message
                return msg.model_dump(exclude_none=True)
        raise RuntimeError("unreachable")

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        candidates = self._select_providers(provider, model)
        errors: list[tuple[str, str]] = []
        for round_i in range(_RATE_LIMIT_ROUNDS):
            errors = []
            retry_afters: list[float] = []
            all_rate_limited = True
            for prov in candidates:
                client = self._client(prov)
                temp = (
                    temperature if temperature is not None else self.config.llm.default_temperature
                )
                log.info("llm_stream", provider=prov.name, model=prov.model)
                kwargs: dict[str, Any] = {
                    "model": prov.model,
                    "messages": messages,
                    "temperature": temp,
                    "stream": True,
                    # Request the provider to send a final chunk with token usage.
                    # Most OpenAI-compatible servers honor this; if not, the
                    # final chunk just won't have a usage block.
                    "stream_options": {"include_usage": True},
                }
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                if tools:
                    kwargs["tools"] = tools
                try:
                    stream = await client.chat.completions.create(**kwargs)
                except openai.RateLimitError as e:
                    ra = _retry_after_seconds(e) or 3.0
                    retry_afters.append(ra)
                    errors.append((f"{prov.name}:{prov.model}", repr(e)))
                    log.warning("provider_rate_limited", provider=prov.name, model=prov.model, retry_after=ra)
                    continue
                except Exception as e:
                    all_rate_limited = False
                    log.warning("provider_failed", provider=prov.name, error=repr(e))
                    errors.append((f"{prov.name}:{prov.model}", repr(e)))
                    continue
                # provider accepted the request — stream it out and we're done
                try:
                    async for chunk in stream:
                        # The final usage chunk has no choices.
                        usage = getattr(chunk, "usage", None)
                        if usage:
                            _record_usage(
                                prov,
                                prompt=usage.prompt_tokens or 0,
                                completion=usage.completion_tokens or 0,
                            )
                        if not chunk.choices:
                            continue
                        choice = chunk.choices[0]
                        delta = (
                            choice.delta.model_dump(exclude_none=True) if choice.delta else {}
                        )
                        yield {"delta": delta, "finish_reason": choice.finish_reason}
                finally:
                    close = getattr(stream, "close", None)
                    if callable(close):
                        try:
                            await close()
                        except Exception:
                            pass
                return
            # every provider failed this round; ride out a pure throttle
            if all_rate_limited and retry_afters and round_i < _RATE_LIMIT_ROUNDS - 1:
                wait_s = _throttle_wait(retry_afters)
                log.info("all_providers_throttled_backoff", wait=round(wait_s, 1), round=round_i + 1, stream=True)
                await asyncio.sleep(wait_s)
                continue
            break
        raise AllProvidersFailed(f"all {len(errors)} attempts failed: {errors}")
