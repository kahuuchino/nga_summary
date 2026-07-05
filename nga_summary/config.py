from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ForumConfig:
    name: str
    fid: str


@dataclass(frozen=True)
class NgaConfig:
    base_url: str
    cookie: str
    headers: dict[str, str]
    target_forums: list[ForumConfig]


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    temperature: float
    max_tokens: int


@dataclass(frozen=True)
class CrawlerConfig:
    request_timeout_seconds: int
    request_interval_seconds: float
    max_threads_per_forum: int
    max_content_threads_per_forum: int
    max_posts_per_thread: int


@dataclass(frozen=True)
class SummaryConfig:
    timezone: str
    daily_run_time: str
    output_dir: Path


@dataclass(frozen=True)
class StorageConfig:
    cache_dir: Path


@dataclass(frozen=True)
class AppConfig:
    path: Path
    nga: NgaConfig
    llm: LlmConfig
    crawler: CrawlerConfig
    summary: SummaryConfig
    storage: StorageConfig


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = _resolve_config_path(path)
    raw = _load_toml(config_path)

    nga_raw = _section(raw, "nga")
    llm_raw = _section(raw, "llm")
    crawler_raw = _section(raw, "crawler")
    summary_raw = _section(raw, "summary")
    storage_raw = _section(raw, "storage")

    forums = [
        ForumConfig(name=str(item.get("name", "")).strip(), fid=str(item.get("fid", "")).strip())
        for item in nga_raw.get("target_forums", [])
        if isinstance(item, dict)
    ]

    return AppConfig(
        path=config_path,
        nga=NgaConfig(
            base_url=str(nga_raw.get("base_url", "https://bbs.nga.cn")).rstrip("/"),
            cookie=_normalize_cookie(str(nga_raw.get("cookie", ""))),
            headers=_load_headers(nga_raw.get("headers", {})),
            target_forums=forums,
        ),
        llm=LlmConfig(
            provider=str(llm_raw.get("provider", "openai_compatible")).strip(),
            base_url=str(llm_raw.get("base_url", "")).strip(),
            api_key=str(llm_raw.get("api_key", "")).strip(),
            model=str(llm_raw.get("model", "")).strip(),
            temperature=float(llm_raw.get("temperature", 0.2)),
            max_tokens=int(llm_raw.get("max_tokens", 4000)),
        ),
        crawler=CrawlerConfig(
            request_timeout_seconds=int(crawler_raw.get("request_timeout_seconds", 20)),
            request_interval_seconds=float(crawler_raw.get("request_interval_seconds", 2)),
            max_threads_per_forum=int(crawler_raw.get("max_threads_per_forum", 50)),
            max_content_threads_per_forum=int(crawler_raw.get("max_content_threads_per_forum", 10)),
            max_posts_per_thread=int(crawler_raw.get("max_posts_per_thread", 80)),
        ),
        summary=SummaryConfig(
            timezone=str(summary_raw.get("timezone", "Asia/Shanghai")).strip(),
            daily_run_time=str(summary_raw.get("daily_run_time", "09:00")).strip(),
            output_dir=Path(str(summary_raw.get("output_dir", "summaries"))),
        ),
        storage=StorageConfig(
            cache_dir=Path(str(storage_raw.get("cache_dir", ".cache/nga_summary"))),
        ),
    )


def validate_config(config: AppConfig, require_llm: bool = True) -> list[str]:
    errors: list[str] = []
    if not config.nga.cookie:
        errors.append("nga.cookie is empty")
    if not config.nga.target_forums:
        errors.append("nga.target_forums is empty")
    for forum in config.nga.target_forums:
        if not forum.name:
            errors.append("a forum name is empty")
        if not forum.fid:
            errors.append(f"forum '{forum.name or '<unnamed>'}' has an empty fid")

    if require_llm:
        if not config.llm.base_url:
            errors.append("llm.base_url is empty")
        if not config.llm.api_key:
            errors.append("llm.api_key is empty")
        if not config.llm.model:
            errors.append("llm.model is empty")
    return errors


def _resolve_config_path(path: str | Path | None) -> Path:
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    if os.environ.get("NGA_SUMMARY_CONFIG"):
        candidates.append(Path(os.environ["NGA_SUMMARY_CONFIG"]))
    candidates.extend([Path("config.local.toml"), Path("config.toml")])

    for candidate in candidates:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(item) for item in candidates)
    raise FileNotFoundError(f"No config file found. Searched: {searched}")


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib  # type: ignore[attr-defined]
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError as exc:
            raise RuntimeError("Missing TOML reader. Run: python3 -m pip install -r requirements.txt") from exc

    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid config file: {path}")
    return data


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    if isinstance(value, dict):
        return value
    raise ValueError(f"Config section [{name}] must be a table")


def _normalize_cookie(value: str) -> str:
    return rejoin_header_lines(value.strip())


def rejoin_header_lines(value: str) -> str:
    return " ".join(part.strip() for part in value.splitlines() if part.strip())


def _load_headers(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Config key nga.headers must be a table")
    return {str(key): str(item) for key, item in value.items() if str(key).strip()}
