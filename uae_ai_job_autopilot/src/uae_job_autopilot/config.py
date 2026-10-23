from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = PACKAGE_ROOT / "config"
DEFAULT_DATA_DIR = PACKAGE_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"
    environment: str = "local"
    jsearch_api_key: str | None = None
    jsearch_api_host: str = "jsearch.p.rapidapi.com"
    jooble_api_key: str | None = None
    discovery_dry_run: bool = False


class SearchProfile(BaseModel):
    target_country: str = "United Arab Emirates"
    locations: list[str] = Field(default_factory=list)
    target_titles: list[str] = Field(default_factory=list)
    freshness_window_hours: int = 24
    evaluation_cap: int = 50
    priority_employers: list[str] = Field(default_factory=list)
    title_keywords: list[str] = Field(default_factory=list)


class SourceConfig(BaseModel):
    enabled: bool = False
    status: str = "planned"
    requires_env: str | None = None
    boards: list[str] = Field(default_factory=list)
    sites: list[str] = Field(default_factory=list)
    alert_dir: str | None = None
    detail: str | None = None


class SourcesConfig(BaseModel):
    defaults: dict[str, Any] = Field(default_factory=dict)
    aggregators: dict[str, SourceConfig] = Field(default_factory=dict)
    ats_public: dict[str, SourceConfig] = Field(default_factory=dict)
    job_boards: dict[str, SourceConfig] = Field(default_factory=dict)
    recruiters: dict[str, SourceConfig] = Field(default_factory=dict)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_search_profile(config_dir: Path | None = None) -> SearchProfile:
    config_dir = config_dir or DEFAULT_CONFIG_DIR
    raw = _load_yaml(config_dir / "search_profile.yaml")
    freshness = raw.get("freshness") or {}
    evaluation = raw.get("evaluation_cap") or {}
    titles = list(raw.get("target_titles") or [])
    # Derive keyword stems for soft title filtering on large boards.
    keywords = []
    for t in titles:
        for part in t.lower().replace("/", " ").split():
            if len(part) > 2 and part not in {"and", "the", "for"}:
                keywords.append(part)
    # Always keep AI/ML stems.
    for k in (
        "ai",
        "ml",
        "llm",
        "rag",
        "nlp",
        "machine",
        "learning",
        "data",
        "scientist",
        "generative",
        "agentic",
        "mlops",
        "applied",
        "forward",
        "deployed",
    ):
        if k not in keywords:
            keywords.append(k)
    return SearchProfile(
        target_country=raw.get("target_country") or "United Arab Emirates",
        locations=list(raw.get("locations") or []),
        target_titles=titles,
        freshness_window_hours=int(freshness.get("window_hours") or 24),
        evaluation_cap=int(
            evaluation.get("max_verified_fresh_unique_jobs")
            if isinstance(evaluation, dict)
            else (evaluation or 50)
        ),
        priority_employers=list(raw.get("priority_employers") or []),
        title_keywords=keywords,
    )


def _parse_source_map(raw: dict[str, Any] | None) -> dict[str, SourceConfig]:
    out: dict[str, SourceConfig] = {}
    for name, cfg in (raw or {}).items():
        if not isinstance(cfg, dict):
            continue
        out[name] = SourceConfig.model_validate(cfg)
    return out


def load_sources_config(config_dir: Path | None = None) -> SourcesConfig:
    config_dir = config_dir or DEFAULT_CONFIG_DIR
    raw = _load_yaml(config_dir / "sources.yaml")
    return SourcesConfig(
        defaults=dict(raw.get("defaults") or {}),
        aggregators=_parse_source_map(raw.get("aggregators")),
        ats_public=_parse_source_map(raw.get("ats_public")),
        job_boards=_parse_source_map(raw.get("job_boards")),
        recruiters=_parse_source_map(raw.get("recruiters")),
    )


def get_settings() -> Settings:
    return Settings()
