from datetime import datetime, timedelta, timezone

from uae_job_autopilot.discovery.dedupe import deduplicate
from uae_job_autopilot.discovery.freshness import is_verified_fresh, partition_by_freshness
from uae_job_autopilot.discovery.normalize import build_job
from uae_job_autopilot.domain.enums import PublicationTimeConfidence
from uae_job_autopilot.utils.location import is_uae_location
from uae_job_autopilot.utils.money import parse_salary_to_aed_monthly


def test_title_gate_rejects_non_ai_roles():
    from uae_job_autopilot.discovery.normalize import title_matches_profile

    assert not title_matches_profile("Senior Risk Strategist, Market Manipulation (Trading Risk)")
    assert not title_matches_profile("Senior Regulatory Specialist")
    assert not title_matches_profile("Account Manager")
    assert title_matches_profile("Senior Machine Learning Engineer")
    assert title_matches_profile("AI Engineer")
    assert title_matches_profile("Forward Deployed Engineer - UAE")
    assert title_matches_profile("Binance Accelerator Program - Data Scientist, Analytics")


def test_uae_location_detection():
    assert is_uae_location("Dubai, United Arab Emirates")
    assert is_uae_location("Abu Dhabi, UAE")
    assert is_uae_location("Sharjah")
    assert not is_uae_location("Karachi, Pakistan")
    assert not is_uae_location("Remote - India")


def test_salary_parse_aed_monthly():
    lo, hi = parse_salary_to_aed_monthly("AED 25,000 - 30,000 per month")
    assert lo == 25000
    assert hi == 30000


def test_verified_freshness_window():
    now = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    fresh = build_job(
        source="greenhouse",
        source_job_id="1",
        title="AI Engineer",
        employer="Careem",
        location_raw="Dubai, UAE",
        application_url="https://example.com/1",
        published_at=now - timedelta(hours=5),
        publication_confidence=PublicationTimeConfidence.VERIFIED,
        discovered_at=now,
    )
    stale = build_job(
        source="greenhouse",
        source_job_id="2",
        title="AI Engineer",
        employer="Careem",
        location_raw="Dubai, UAE",
        application_url="https://example.com/2",
        published_at=now - timedelta(hours=30),
        publication_confidence=PublicationTimeConfidence.VERIFIED,
        discovered_at=now,
    )
    unverified = build_job(
        source="greenhouse",
        source_job_id="3",
        title="AI Engineer",
        employer="Careem",
        location_raw="Dubai, UAE",
        application_url="https://example.com/3",
        published_at=now - timedelta(hours=1),
        publication_confidence=PublicationTimeConfidence.UNVERIFIED,
        discovered_at=now,
    )
    assert is_verified_fresh(fresh, now=now, window_hours=24)
    assert not is_verified_fresh(stale, now=now, window_hours=24)
    assert not is_verified_fresh(unverified, now=now, window_hours=24)
    kept, excluded = partition_by_freshness([fresh, stale, unverified], now=now, window_hours=24)
    assert len(kept) == 1
    assert len(excluded) == 2


def test_dedupe_prefers_ats_over_aggregator():
    now = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    a = build_job(
        source="jsearch",
        source_job_id="a",
        title="ML Engineer",
        employer="Acme",
        location_raw="Dubai, UAE",
        application_url="https://example.com/same",
        published_at=now,
        publication_confidence=PublicationTimeConfidence.VERIFIED,
        discovered_at=now,
    )
    b = build_job(
        source="greenhouse",
        source_job_id="b",
        title="ML Engineer",
        employer="Acme",
        location_raw="Dubai, UAE",
        application_url="https://example.com/same",
        published_at=now,
        publication_confidence=PublicationTimeConfidence.VERIFIED,
        discovered_at=now,
    )
    unique, dupes = deduplicate([a, b])
    assert dupes == 1
    assert len(unique) == 1
    assert unique[0].source == "greenhouse"
