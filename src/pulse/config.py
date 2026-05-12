import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    name: str
    base_url: str
    api_key_env: str | None = None
    model: str
    timeout: float = 60.0
    max_retries: int = 2
    # Approximate token pricing (USD per million tokens). Used for cost
    # display only — billing reconciles against the actual provider invoice.
    # 0.0 disables cost tracking for this provider.
    prompt_cost_per_million: float = 0.0
    completion_cost_per_million: float = 0.0


class LLMConfig(BaseModel):
    providers: list[ProviderConfig] = Field(min_length=1)
    default_temperature: float = 0.6


class WebToolsConfig(BaseModel):
    base_url: str = "https://api.openadapter.in"
    api_key_env: str = "OPENADAPTER_API_KEY"
    timeout: float = 30.0


class SeoConfig(BaseModel):
    pagespeed_api_key_env: str = "PAGESPEED_API_KEY"


class SchedulerConfig(BaseModel):
    enabled: bool = True
    daily_hour: int = 6
    daily_minute: int = 0


class AgentConfig(BaseModel):
    max_iterations: int = 16


class Config(BaseModel):
    server_host: str = "127.0.0.1"
    server_port: int = 8787
    data_dir: str = "~/.pulse"
    llm: LLMConfig
    web: WebToolsConfig = WebToolsConfig()
    seo: SeoConfig = SeoConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    agent: AgentConfig = AgentConfig()

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> "Config":
        load_dotenv(override=True)
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"{p} not found")
        with p.open() as f:
            raw = yaml.safe_load(f)
        return cls(**raw)

    def resolved_api_key(self, provider: ProviderConfig) -> str | None:
        if not provider.api_key_env:
            return None
        key = os.getenv(provider.api_key_env)
        if not key:
            raise RuntimeError(
                f"env var {provider.api_key_env} (for provider '{provider.name}') is missing"
            )
        return key

    def data_path(self) -> Path:
        p = Path(self.data_dir).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def web_api_key(self) -> str:
        key = os.getenv(self.web.api_key_env)
        if not key:
            raise RuntimeError(f"env var {self.web.api_key_env} missing for web tools")
        return key

    def pagespeed_api_key(self) -> str | None:
        return os.getenv(self.seo.pagespeed_api_key_env) or None
