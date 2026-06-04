"""Tool-using agent loop with SSE-friendly streaming.

Same pattern as perso/iris: stream chunks → accumulate tool calls → dispatch →
append results to history → loop until plain text or max_iterations hit.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import structlog

from .llm import LLM
from .text import strip_reasoning
from .tools import ToolRegistry

log = structlog.get_logger()


class _ThinkFilter:
    """Stream-time filter that swallows tokens inside <think>...</think> blocks.

    Reasoning-tuned open-weight models (MiniMax, GLM-5, DeepSeek-R1) emit a
    reasoning section before the user-visible answer. We don't want those
    tokens in the live terminal log or in the saved assistant message. The
    filter buffers ambiguous tail bytes (could be the start of a tag) and
    emits only confirmed-visible content.

    Idempotent on text with no tags — buffers at most ``MAX_TAIL`` bytes.
    """

    OPEN_TAGS = ("<think", "<thinking", "<reasoning", "<reflection")
    CLOSE_TAGS = ("</think>", "</thinking>", "</reasoning>", "</reflection>")
    MAX_TAIL = 16  # longest possible partial-tag prefix we ever hold back

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

    def feed(self, chunk: str) -> str:
        out: list[str] = []
        self._buf += chunk
        while self._buf:
            if self._in_think:
                # look for the closing tag
                idx = -1
                tag_used = ""
                for ct in self.CLOSE_TAGS:
                    j = self._buf.lower().find(ct)
                    if j != -1 and (idx == -1 or j < idx):
                        idx = j
                        tag_used = ct
                if idx == -1:
                    # close tag not yet in buffer — keep waiting, but flush
                    # everything except a possible partial-close suffix
                    keep = min(self.MAX_TAIL, len(self._buf))
                    self._buf = self._buf[-keep:]
                    return "".join(out)
                # drop everything up to + including the close tag
                self._buf = self._buf[idx + len(tag_used):]
                self._in_think = False
            else:
                # look for an opening tag
                lower = self._buf.lower()
                idx = -1
                tag_used = ""
                for ot in self.OPEN_TAGS:
                    j = lower.find(ot)
                    if j != -1 and (idx == -1 or j < idx):
                        idx = j
                        tag_used = ot
                if idx == -1:
                    # no opener — flush all but a partial-tag tail
                    safe = max(0, len(self._buf) - self.MAX_TAIL)
                    # only hold back if the tail might be the start of a tag
                    tail = self._buf[safe:]
                    if any(
                        ot.startswith(tail.lower()[: len(ot)]) and tail.lower().startswith(ot[: len(tail)])
                        for ot in self.OPEN_TAGS
                    ) or (tail.endswith("<") or "<" in tail[-self.MAX_TAIL:]):
                        out.append(self._buf[:safe])
                        self._buf = tail
                    else:
                        out.append(self._buf)
                        self._buf = ""
                    return "".join(out)
                # emit text before the opener
                out.append(self._buf[:idx])
                # find the end of the opening tag (after first `>` or whitespace)
                rest = self._buf[idx:]
                # opening might be "<think>" or "<think attr=...>"; consume up to '>'
                gt = rest.find(">")
                if gt == -1:
                    # opener tag isn't yet closed (no '>' in buffer) — hold
                    self._buf = rest
                    return "".join(out)
                self._buf = rest[gt + 1:]
                self._in_think = True
        return "".join(out)

    def flush(self) -> str:
        """Return any held-back text (best-effort) and reset state."""
        # If we were inside a think block when the stream ended, discard.
        if self._in_think:
            self._buf = ""
            self._in_think = False
            return ""
        rem, self._buf = self._buf, ""
        return rem


@dataclass
class ToolInvocation:
    name: str
    arguments: dict[str, Any]
    result: str


@dataclass
class AgentResult:
    content: str
    invocations: list[ToolInvocation] = field(default_factory=list)
    iterations: int = 0


class MaxIterationsExceeded(RuntimeError):
    pass


class Agent:
    def __init__(
        self,
        llm: LLM,
        registry: ToolRegistry,
        *,
        system_prompt: str | None = None,
        max_iterations: int = 16,
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations

    async def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        prefix_system: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        history = self._build_history(messages, prefix_system)
        tools_payload = self.registry.openai_tools() or None
        seen_calls: set[str] = set()

        yield {"type": "start"}

        for iteration in range(1, self.max_iterations + 1):
            yield {"type": "iteration", "n": iteration}

            text_parts: list[str] = []
            tc_acc: dict[int, dict[str, str]] = {}
            think_buf = _ThinkFilter()

            async for chunk in self.llm.stream_chat(
                history,
                tools=tools_payload,
                temperature=temperature,
                provider=provider,
                model=model,
            ):
                delta = chunk.get("delta") or {}
                content = delta.get("content")
                if content:
                    visible = think_buf.feed(content)
                    if visible:
                        text_parts.append(visible)
                        yield {"type": "text", "text": visible}

                for tc_delta in delta.get("tool_calls") or []:
                    idx = tc_delta.get("index", 0)
                    acc = tc_acc.setdefault(
                        idx, {"id": "", "name": "", "arguments_str": ""}
                    )
                    if tc_delta.get("id"):
                        acc["id"] = tc_delta["id"]
                    fn = tc_delta.get("function") or {}
                    if fn.get("name"):
                        acc["name"] = fn["name"]
                    if fn.get("arguments"):
                        acc["arguments_str"] += fn["arguments"]

            # flush anything we might have been holding inside the buffer
            tail = think_buf.flush()
            if tail:
                text_parts.append(tail)
                yield {"type": "text", "text": tail}
            full_text = strip_reasoning("".join(text_parts))
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": full_text or None,
            }
            if tc_acc:
                assistant_msg["tool_calls"] = [
                    {
                        "id": acc["id"] or f"call_{idx}",
                        "type": "function",
                        "function": {
                            "name": acc["name"],
                            "arguments": acc["arguments_str"] or "{}",
                        },
                    }
                    for idx, acc in sorted(tc_acc.items())
                ]
            history.append(assistant_msg)

            if not tc_acc:
                yield {"type": "done", "iterations": iteration, "content": full_text}
                return

            # Announce every tool call, then dispatch the independent ones
            # CONCURRENTLY (a turn often fans out crawl + audits + searches).
            # Dedup is decided sequentially (deterministic); results are emitted
            # in the original order so the history stays well-formed.
            _DUP = json.dumps({
                "ok": False,
                "error": "duplicate_call",
                "note": "this exact tool + args was already called this turn. change strategy or stop.",
            })
            parsed: list[tuple[str, str, dict[str, Any]]] = []
            for idx, acc in sorted(tc_acc.items()):
                call_id = acc["id"] or f"call_{idx}"
                name = acc["name"]
                try:
                    args = json.loads(acc["arguments_str"]) if acc["arguments_str"] else {}
                except json.JSONDecodeError:
                    args = {}
                log.info("tool_call", name=name, arguments=args)
                yield {"type": "tool_call", "id": call_id, "name": name, "arguments": args}
                parsed.append((call_id, name, args))

            tasks: dict[str, asyncio.Task] = {}
            is_dup: set[str] = set()
            for call_id, name, args in parsed:
                call_key = f"{name}:{json.dumps(args, sort_keys=True, default=str)}"
                if call_key in seen_calls:
                    is_dup.add(call_id)
                else:
                    seen_calls.add(call_key)
                    tasks[call_id] = asyncio.create_task(self.registry.dispatch(name, args))

            results: dict[str, str] = {}
            for cid, task in tasks.items():
                results[cid] = await task

            for call_id, name, args in parsed:
                result = _DUP if call_id in is_dup else results[call_id]
                yield {"type": "tool_result", "id": call_id, "name": name, "result": result}
                history.append(
                    {"role": "tool", "tool_call_id": call_id, "content": result}
                )

        yield {
            "type": "error",
            "message": f"agent did not finish within {self.max_iterations} iterations",
        }

    async def run(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> AgentResult:
        content = ""
        iterations = 0
        invocations: list[ToolInvocation] = []
        pending: dict[str, dict[str, Any]] = {}

        async for ev in self.stream(messages, **kwargs):
            t = ev.get("type")
            if t == "iteration":
                iterations = ev.get("n", iterations)
            elif t == "tool_call":
                pending[ev["id"]] = {"name": ev["name"], "arguments": ev["arguments"]}
            elif t == "tool_result":
                meta = pending.pop(ev["id"], None)
                invocations.append(
                    ToolInvocation(
                        name=ev["name"],
                        arguments=meta["arguments"] if meta else {},
                        result=ev["result"],
                    )
                )
            elif t == "done":
                content = ev.get("content", "")
                iterations = ev.get("iterations", iterations)
            elif t == "error":
                raise MaxIterationsExceeded(ev.get("message", "agent failed"))

        return AgentResult(content=content, invocations=invocations, iterations=iterations)

    def _build_history(
        self,
        messages: list[dict[str, Any]],
        prefix_system: str | None,
    ) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        system_text = self.system_prompt or ""
        if prefix_system:
            system_text = (
                (system_text + "\n\n" + prefix_system).strip()
                if system_text
                else prefix_system
            )
        if system_text and not (messages and messages[0].get("role") == "system"):
            history.append({"role": "system", "content": system_text})
        history.extend(messages)
        return history
