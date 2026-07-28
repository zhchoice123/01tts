import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_TECH_FEEDS = [
    "https://spring.io/blog.atom",
    "https://inside.java/feed.xml",
    "https://github.blog/engineering/feed/",
    "https://kubernetes.io/feed.xml",
    "https://aws.amazon.com/blogs/architecture/feed/",
    "https://blog.cloudflare.com/rss/",
    "https://martinfowler.com/feed.atom",
    "https://www.postgresql.org/news.rss",
]


@dataclass(frozen=True)
class WorkerConfig:
    redis_url: str
    redis_password: str
    server_url: str
    audio_output_dir: str
    news_sources: list[str]
    deepseek_model: str
    openai_model: str
    moonshot_model: str
    deepseek_api_key: str
    openai_api_key: str
    moonshot_api_key: str

    def __repr__(self) -> str:
        """Sanitized string representation never printing raw API keys or passwords."""
        def mask(val: str) -> str:
            return "***" if val else ""

        return (
            f"WorkerConfig("
            f"redis_url={self.redis_url!r}, "
            f"redis_password={mask(self.redis_password)!r}, "
            f"server_url={self.server_url!r}, "
            f"audio_output_dir={self.audio_output_dir!r}, "
            f"news_sources={self.news_sources!r}, "
            f"deepseek_model={self.deepseek_model!r}, "
            f"openai_model={self.openai_model!r}, "
            f"moonshot_model={self.moonshot_model!r}, "
            f"deepseek_api_key={mask(self.deepseek_api_key)!r}, "
            f"openai_api_key={mask(self.openai_api_key)!r}, "
            f"moonshot_api_key={mask(self.moonshot_api_key)!r}"
            f")"
        )


def _nested(data: dict[str, Any], section: str, key: str, default: Any = "") -> Any:
    value = data.get(section, {})
    if not isinstance(value, dict):
        return default
    return value.get(key, default)


def load_config(path: Path) -> WorkerConfig:
    data: dict[str, Any] = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Configuration root must be a mapping: {path}")
        data = loaded

    news_sources_raw = _nested(data, "news", "sources", [])
    if isinstance(news_sources_raw, str):
        news_sources = [s.strip() for s in news_sources_raw.split(",") if s.strip()]
    elif isinstance(news_sources_raw, list):
        news_sources = [str(s).strip() for s in news_sources_raw if str(s).strip()]
    else:
        news_sources = []

    env_news = os.getenv("NEWS_SOURCES", "")
    if env_news.strip():
        news_sources = [s.strip() for s in env_news.split(",") if s.strip()]
    if not news_sources:
        news_sources = list(DEFAULT_TECH_FEEDS)

    # Key Precedence: Environment variables take priority, file config overrides only if env not set
    deepseek_key = os.getenv("DEEPSEEK_API_KEY") or str(_nested(data, "deepseek", "api_key", ""))
    openai_key = os.getenv("OPENAI_API_KEY") or str(_nested(data, "openai", "api_key", ""))
    moonshot_key = os.getenv("MOONSHOT_API_KEY") or str(_nested(data, "moonshot", "api_key", ""))

    return WorkerConfig(
        redis_url=os.getenv(
            "REDIS_URL",
            str(_nested(data, "redis", "url", "redis://localhost:6379/0")),
        ),
        redis_password=os.getenv(
            "REDIS_PASSWORD",
            str(_nested(data, "redis", "password", "")),
        ),
        server_url=os.getenv(
            "SERVER_URL",
            str(_nested(data, "server", "url", "http://localhost:8080")),
        ),
        audio_output_dir=os.getenv(
            "AUDIO_OUTPUT_DIR",
            str(_nested(data, "audio", "output_dir", "./output")),
        ),
        news_sources=news_sources,
        deepseek_model=os.getenv(
            "DEEPSEEK_MODEL",
            str(_nested(data, "deepseek", "model", "deepseek-v4-flash")),
        ),
        openai_model=os.getenv(
            "OPENAI_MODEL",
            str(_nested(data, "openai", "model", "gpt-4o-mini")),
        ),
        moonshot_model=os.getenv(
            "MOONSHOT_MODEL",
            str(_nested(data, "moonshot", "model", "kimi-k3")),
        ),
        deepseek_api_key=deepseek_key,
        openai_api_key=openai_key,
        moonshot_api_key=moonshot_key,
    )
