from uae_job_autopilot.discovery.orchestrator import DiscoveryOrchestrator
from uae_job_autopilot.domain.enums import SourceStatus


def test_dry_run_does_not_claim_sources_searched():
    orch = DiscoveryOrchestrator()
    report = orch.run(dry_run=True)
    assert report.dry_run is True
    assert report.stats.sources_attempted == 0
    assert report.selected_jobs == []
    # Enabled adapters should report skipped (not attempted) in dry-run
    enabled_health = [h for h in report.source_health if h.source in {
        "greenhouse", "lever", "ashby", "jsearch", "linkedin_jobs"
    }]
    assert enabled_health
    for h in enabled_health:
        assert h.attempted is False
        assert h.status in {
            SourceStatus.SKIPPED_DISABLED,
            SourceStatus.SKIPPED_NOT_CONFIGURED,
            SourceStatus.SKIPPED_UNSUPPORTED,
        }
