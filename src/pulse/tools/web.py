"""Web tools backed by OpenAdapter's /v1/tools/* endpoints.

  * web_search(query, num_results)
  * read_url(url)
  * news_search(query, num_results)
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from .registry import Tool, tool

log = structlog.get_logger()


class _WebClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.timeout = timeout

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, headers=self.headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
        return r.json()


def _format_search_results(data: dict[str, Any]) -> str:
    items = (
        data.get("results")
        or data.get("data")
        or data.get("items")
        or []
    )
    if isinstance(items, dict):
        items = items.get("items") or items.get("results") or []
    if not items:
        return "(no results)"
    lines: list[str] = []
    for i, item in enumerate(items, 1):
        title = item.get("title") or item.get("name") or "(untitled)"
        url = item.get("url") or item.get("link") or ""
        snippet = (
            item.get("snippet")
            or item.get("description")
            or item.get("content")
            or ""
        )
        snippet = snippet.strip().replace("\n", " ")[:300]
        date = item.get("date") or item.get("published") or item.get("published_at")
        date_part = f" · {date}" if date else ""
        lines.append(f"{i}. {title}{date_part}\n   {url}\n   {snippet}")
    return "\n\n".join(lines)


def make_web_tools(*, base_url: str, api_key: str, timeout: float = 30.0) -> list[Tool]:
    if not api_key:
        raise ValueError("openadapter api_key required for web tools")
    client = _WebClient(base_url=base_url, api_key=api_key, timeout=timeout)
    tools: list[Tool] = []

    @tool
    async def web_search(query: str, num_results: int = 5) -> str:
        """Search the web. Use for competitor research, finding mentions,
        looking up trends, and current-info questions.

        Args:
            query: Search query.
            num_results: 1-10, default 5.
        """
        n = max(1, min(int(num_results), 10))
        try:
            data = await client.post("/v1/tools/search", {"query": query, "num_results": n})
        except Exception as e:
            return f"search failed: {e}"
        return _format_search_results(data)

    tools.append(web_search)

    @tool
    async def read_url(url: str) -> str:
        """Fetch a webpage and return clean markdown content.

        Use after a search returns a promising link, or when you need to read
        a specific page (competitor homepage, article, etc).

        Args:
            url: Full URL with https://.
        """
        try:
            data = await client.post("/v1/tools/scrape/markdown", {"url": url})
        except Exception as e:
            return f"read_url failed: {e}"
        md = (
            data.get("markdown")
            or data.get("content")
            or data.get("data", {}).get("markdown")
            or ""
        )
        md = str(md).strip()
        if not md:
            return f"(empty content for {url})"
        if len(md) > 8000:
            return md[:8000] + f"\n\n... [truncated, {len(md) - 8000} more chars]"
        return md

    tools.append(read_url)

    @tool
    async def news_search(query: str, num_results: int = 5) -> str:
        """Search recent news. Use for industry trends, competitor announcements.

        Args:
            query: News query.
            num_results: 1-10, default 5.
        """
        n = max(1, min(int(num_results), 10))
        try:
            data = await client.post("/v1/tools/search/news", {"query": query, "num_results": n})
        except Exception as e:
            return f"news_search failed: {e}"
        return _format_search_results(data)

    tools.append(news_search)

    return tools
