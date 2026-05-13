"""Runtime-mutable settings: provider overrides, role assignments, model fetching.

The YAML config bootstraps defaults; this module persists user edits to
`settings.json` in `data_dir` and merges them back into the live `Config`.

API:
    SettingsStore(data_dir)
      .load()                       -> dict snapshot
      .save_providers(list[dict])   -> persists + returns the new list
      .apply_to_config(config)      -> mutates config.llm.providers in place
      .fetch_models(provider)       -> list of model ids from /v1/models
      .test_connection(provider)    -> {ok: bool, error?: str, models?: int}

Provider shape (extends ProviderConfig):
    name: str
    base_url: str
    api_key: str | None        -- raw key (stored locally, NOT in env)
    api_key_env: str | None    -- legacy env-based lookup (optional)
    model: str
    role: "primary" | "secondary" | "vision" | "fallback"
    prompt_cost_per_million: float
    completion_cost_per_million: float
    timeout: float
    max_retries: int
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from .config import Config, ProviderConfig


SETTINGS_FILE = "settings.json"


class SettingsStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir).expanduser()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / SETTINGS_FILE

    # --- persistence -----------------------------------------------------

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return {}

    def save(self, data: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.path)

    # --- providers -------------------------------------------------------

    def list_providers(self, fallback: list[ProviderConfig]) -> list[dict[str, Any]]:
        """Return the merged list of providers. Falls back to YAML defaults
        when settings.json is empty."""
        data = self.load()
        custom = data.get("providers")
        if custom is None:
            return [self._provider_to_dict(p, i) for i, p in enumerate(fallback)]
        return custom

    def save_providers(self, providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # validate minimally
        cleaned = []
        for p in providers:
            cleaned.append(
                {
                    "name": str(p.get("name") or "").strip(),
                    "base_url": str(p.get("base_url") or "").strip(),
                    "api_key": p.get("api_key") or None,
                    "api_key_env": p.get("api_key_env") or None,
                    "model": str(p.get("model") or "").strip(),
                    "role": p.get("role") or "fallback",
                    "timeout": float(p.get("timeout") or 60.0),
                    "max_retries": int(p.get("max_retries") or 1),
                    "prompt_cost_per_million": float(p.get("prompt_cost_per_million") or 0.0),
                    "completion_cost_per_million": float(p.get("completion_cost_per_million") or 0.0),
                }
            )
        data = self.load()
        data["providers"] = cleaned
        self.save(data)
        return cleaned

    # --- live config application ----------------------------------------

    def apply_to_config(self, config: Config) -> None:
        """Replace config.llm.providers with the persisted list, sorted by role
        so primary comes first, then secondary, then fallback."""
        data = self.load()
        custom = data.get("providers")
        if not custom:
            return
        role_order = {"primary": 0, "secondary": 1, "fallback": 2, "vision": 3}
        ordered = sorted(custom, key=lambda p: role_order.get(p.get("role", "fallback"), 2))
        new_providers: list[ProviderConfig] = []
        for p in ordered:
            # for `LLM.resolved_api_key`, prefer inline api_key, falling back
            # to env. We expose the inline key via a synthetic env var so
            # ProviderConfig's existing flow stays untouched.
            api_key = p.get("api_key")
            env_name = p.get("api_key_env")
            if api_key:
                env_name = f"PULSE_KEY_{p['name'].replace('-', '_').replace(' ', '_').upper()}"
                os.environ[env_name] = api_key
            new_providers.append(
                ProviderConfig(
                    name=p["name"],
                    base_url=p["base_url"],
                    api_key_env=env_name,
                    model=p["model"],
                    timeout=float(p.get("timeout", 60.0)),
                    max_retries=int(p.get("max_retries", 1)),
                    prompt_cost_per_million=float(p.get("prompt_cost_per_million", 0.0)),
                    completion_cost_per_million=float(p.get("completion_cost_per_million", 0.0)),
                )
            )
        if new_providers:
            config.llm.providers = new_providers

    # --- network helpers ------------------------------------------------

    @staticmethod
    def _normalize_base(url: str) -> str:
        url = url.rstrip("/")
        return url

    async def fetch_models(
        self, *, base_url: str, api_key: str, timeout: float = 15.0
    ) -> list[str]:
        url = f"{self._normalize_base(base_url)}/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=timeout) as cx:
            r = await cx.get(url, headers=headers)
            r.raise_for_status()
            payload = r.json()
        data = payload.get("data") or payload.get("models") or []
        ids: list[str] = []
        for item in data:
            mid = item.get("id") if isinstance(item, dict) else item
            if mid:
                ids.append(str(mid))
        return sorted(set(ids))

    async def test_connection(
        self, *, base_url: str, api_key: str, timeout: float = 10.0
    ) -> dict[str, Any]:
        try:
            models = await self.fetch_models(
                base_url=base_url, api_key=api_key, timeout=timeout
            )
            return {"ok": True, "models": len(models), "sample": models[:5]}
        except httpx.HTTPStatusError as e:
            return {"ok": False, "status": e.response.status_code, "error": e.response.text[:240]}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # --- dict helpers ----------------------------------------------------

    @staticmethod
    def _provider_to_dict(p: ProviderConfig, idx: int = 0) -> dict[str, Any]:
        # the first YAML provider becomes primary, second secondary, rest fallback
        role = "primary" if idx == 0 else "secondary" if idx == 1 else "fallback"
        return {
            "name": p.name,
            "base_url": p.base_url,
            "api_key": None,            # never expose YAML env value
            "api_key_env": p.api_key_env,
            "model": p.model,
            "role": role,
            "timeout": p.timeout,
            "max_retries": p.max_retries,
            "prompt_cost_per_million": p.prompt_cost_per_million,
            "completion_cost_per_million": p.completion_cost_per_million,
        }
