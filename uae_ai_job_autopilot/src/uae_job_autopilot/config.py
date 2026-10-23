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

    # Phase 2 — TypeSafe Jev / generative
    typesafe_api_key: str | None = None
    typesafe_api_base: str = "https://api.typesafe.ai"
    jev_model: str = "jev-1.14.0"
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_enabled: bool = False
    enable_cloud_generative: bool = False

    # Phase 3 — persistence / Sheets / Gmail
    database_url: str = "sqlite:///./data/db/uae_jobs.db"
    google_service_account_json: str | None = None
    google_sheets_spreadsheet_id: str | None = None
    gmail_credentials_json: str | None = None
    report_to_email: str = "vaishnavibatchu28@gmail.com"
    sheets_enabled: bool = False
    gmail_enabled: bool = False

    # Phase 4 — cloud ops
    daily_cost_cap_usd: float = 2.0
    lock_name: str = "uae_job_autopilot_daily"
    lock_ttl_seconds: int = 7200
    allow_sqlite_in_cloud: bool = False
    pipeline_stages: str = "discover,evaluate,prepare_docs,apply,report"
    enable_live_submission: bool = False  # Phase 5 real channels; mock_sandbox can still dry-run


class ModelsConfig(BaseModel):
    jev_endpoint: str = "https://api.typesafe.ai/v1/systemone"
    jev_default_model: str = "jev-1.14.0"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_cache: bool = True
    resume_embedding_weight: float = 0.40
    resume_rubric_weight: float = 0.60
    resume_threshold: float = 75.0
    visa_deterministic_weight: float = 0.50
    visa_jev_weight: float = 0.50
    visa_threshold: float = 70.0
    ats_structure_weight: float = 0.40
    ats_keyword_weight: float = 0.60
    ats_threshold: float = 80.0
    ollama_enabled: bool = False
    ollama_model: str = "qwen2.5:7b-instruct"
    groq_enabled: bool = False
    groq_model: str = "llama-3.1-8b-instant"
    gemini_enabled: bool = False
    gemini_model: str = "gemini-2.0-flash-lite"
    # TypeSafe list price (input): $0.042 / MTok; output free (docs, Oct 2026)
    jev_cost_per_mtok_input_usd: float = 0.042


class CandidateProfile(BaseModel):
    full_name: str
    email: str
    phone: str | None = None
    linkedin: str | None = None
    current_city: str = "Pune"
    current_country: str = "India"
    total_experience_years_approx: float = 4.0
    current_title: str = "Senior Data Scientist"
    current_employer: str = ""
    previous_employers: list[str] = Field(default_factory=list)
    resume_pdf: str = "data/resume/Vaishnavi_Santoshi_Batchu_Resume_ATS.pdf"
    requires_employer_sponsorship: bool = True
    relocation_willing: bool = True
    notice_period_days: int = 30
    expected_monthly_aed_min: float = 25000
    expected_monthly_aed_max: float = 30000
    expected_monthly_aed_default: float = 28000
    hard_floor_monthly_aed: float = 20000
    skills: list[str] = Field(default_factory=list)
    resume_text: str = ""
    summary: str = ""


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


def load_models_config(config_dir: Path | None = None) -> ModelsConfig:
    config_dir = config_dir or DEFAULT_CONFIG_DIR
    raw = _load_yaml(config_dir / "models.yaml")
    jev = raw.get("jev") or {}
    emb = raw.get("embeddings") or {}
    scoring = raw.get("scoring") or {}
    resume = scoring.get("resume_fit") or {}
    visa = scoring.get("visa") or {}
    generative = raw.get("generative") or {}
    local = generative.get("local_router") or {}
    cloud = generative.get("cloud_router") or {}
    providers = {p.get("name"): p for p in (cloud.get("providers") or []) if isinstance(p, dict)}
    groq = providers.get("groq") or {}
    gemini = providers.get("gemini") or {}
    return ModelsConfig(
        jev_endpoint=str(jev.get("endpoint") or "https://api.typesafe.ai/v1/systemone"),
        jev_default_model=str(jev.get("default_model") or "jev-1.14.0"),
        embedding_model=str(emb.get("model") or "sentence-transformers/all-MiniLM-L6-v2"),
        embedding_cache=bool(emb.get("cache", True)),
        resume_embedding_weight=float(resume.get("embedding_weight") or 0.40),
        resume_rubric_weight=float(resume.get("rubric_weight") or 0.60),
        resume_threshold=float(resume.get("threshold") or 75),
        visa_deterministic_weight=float(visa.get("deterministic_weight") or 0.50),
        visa_jev_weight=float(visa.get("jev_weight") or 0.50),
        visa_threshold=float(visa.get("threshold") or 70),
        ats_structure_weight=float((scoring.get("ats") or {}).get("structure_weight") or 0.40),
        ats_keyword_weight=float((scoring.get("ats") or {}).get("keyword_weight") or 0.60),
        ats_threshold=float((scoring.get("ats") or {}).get("threshold") or 80),
        ollama_enabled=bool(local.get("enabled", False)),
        ollama_model=str(local.get("model") or "qwen2.5:7b-instruct"),
        groq_enabled=bool(groq.get("enabled", False)),
        groq_model=str(groq.get("model") or "llama-3.1-8b-instant"),
        gemini_enabled=bool(gemini.get("enabled", False)),
        gemini_model=str(gemini.get("model") or "gemini-2.0-flash-lite"),
    )


def load_candidate_profile(config_dir: Path | None = None) -> CandidateProfile:
    config_dir = config_dir or DEFAULT_CONFIG_DIR
    raw = _load_yaml(config_dir / "candidate.yaml")
    loc = raw.get("current_location") or {}
    role = raw.get("current_role") or {}
    visa = raw.get("visa") or {}
    reloc = raw.get("relocation") or {}
    comp = raw.get("compensation") or {}
    return CandidateProfile(
        full_name=str(raw.get("full_name") or ""),
        email=str(raw.get("email") or ""),
        phone=raw.get("phone"),
        linkedin=raw.get("linkedin"),
        current_city=str(loc.get("city") or "Pune"),
        current_country=str(loc.get("country") or "India"),
        total_experience_years_approx=float(raw.get("total_experience_years_approx") or 4),
        current_title=str(role.get("title") or "Senior Data Scientist"),
        current_employer=str(role.get("employer") or ""),
        previous_employers=list(raw.get("previous_employers") or []),
        resume_pdf=str(raw.get("resume_pdf") or "data/resume/Vaishnavi_Santoshi_Batchu_Resume_ATS.pdf"),
        requires_employer_sponsorship=bool(visa.get("requires_employer_sponsorship", True)),
        relocation_willing=bool(reloc.get("willing", True)),
        notice_period_days=int(raw.get("notice_period_days") or 30),
        expected_monthly_aed_min=float(comp.get("expected_monthly_min") or 25000),
        expected_monthly_aed_max=float(comp.get("expected_monthly_max") or 30000),
        expected_monthly_aed_default=float(comp.get("expected_monthly_default") or 28000),
        hard_floor_monthly_aed=float(comp.get("hard_floor_monthly_max_offer") or 20000),
    )


def get_settings() -> Settings:
    return Settings()
