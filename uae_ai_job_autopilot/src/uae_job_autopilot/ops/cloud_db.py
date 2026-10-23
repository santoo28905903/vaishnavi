from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from uae_job_autopilot.config import Settings, get_settings
from uae_job_autopilot.db.repository import ApplicationRepository
from uae_job_autopilot.db.tables import make_session_factory

logger = logging.getLogger(__name__)


class DatabaseConfigError(RuntimeError):
    """Raised when production/cloud persistence is misconfigured."""


def is_cloud_environment(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    env = (settings.environment or "").lower()
    if env in {"cloud", "production", "prod", "github_actions", "ci_cloud"}:
        return True
    # GitHub Actions runners
    if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
        return True
    return False


def assert_persistent_database(settings: Settings | None = None) -> str:
    """
    Production/cloud must not use ephemeral SQLite.
    Returns the validated DATABASE_URL.
    """
    settings = settings or get_settings()
    url = (settings.database_url or "").strip()
    if not url:
        raise DatabaseConfigError("DATABASE_URL is required")

    cloud = is_cloud_environment(settings)
    scheme = urlparse(url.replace("postgresql+psycopg", "postgresql")).scheme.lower()

    if cloud and not settings.allow_sqlite_in_cloud:
        if scheme.startswith("sqlite"):
            raise DatabaseConfigError(
                "Cloud/production runs require a persistent DATABASE_URL "
                "(PostgreSQL). Ephemeral SQLite is not allowed."
            )
        if not (
            scheme.startswith("postgres")
            or scheme.startswith("postgresql")
            or "psycopg" in url
        ):
            # Allow other durable engines explicitly named, but warn for unknowns
            logger.warning("Non-Postgres DATABASE_URL in cloud: scheme=%s", scheme)

    return url


def resolve_database_url(settings: Settings | None = None) -> str:
    """Local may use SQLite; cloud must pass assert_persistent_database."""
    settings = settings or get_settings()
    if is_cloud_environment(settings):
        return assert_persistent_database(settings)
    return settings.database_url


def build_repository(settings: Settings | None = None) -> ApplicationRepository:
    url = resolve_database_url(settings)
    # Ensure tables (including Phase 4 lock/checkpoint) exist
    make_session_factory(url)
    return ApplicationRepository.from_url(url)
