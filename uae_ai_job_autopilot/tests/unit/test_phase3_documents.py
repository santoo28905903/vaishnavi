from __future__ import annotations

import json
from pathlib import Path

from uae_job_autopilot.documents.ats import assess_ats_pdf
from uae_job_autopilot.documents.generator import DocumentPipeline
from uae_job_autopilot.documents.integrity import factual_integrity_check
from uae_job_autopilot.documents.master import build_master_resume
from uae_job_autopilot.domain.models import JobPosting
from uae_job_autopilot.matching.resume import extract_pdf_text

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "jobs" / "representative_jobs.json"


def _good_job() -> JobPosting:
    data = json.loads(FIXTURES.read_text())
    return JobPosting.model_validate(
        next(j for j in data["jobs"] if j["source_job_id"] == "good-rag-1")
    )


def test_master_resume_from_pdf_is_truthful(tmp_path):
    master = build_master_resume(persist=False)
    assert master.full_name.startswith("Vaishnavi")
    assert any("Relanto" in r.employer or "Google" in r.employer for r in master.experience)
    assert any("Searce" in r.employer for r in master.experience)
    assert "Python" in master.skills
    # Must not invent Meta/OpenAI employment
    blob = master.all_attested_text().lower()
    assert "netflix" not in blob


def test_integrity_rejects_fabricated_phd_and_fake_employer():
    master = build_master_resume(persist=False)
    ok, issues = factual_integrity_check(
        "I hold a PhD and worked at Netflix as Principal Scientist for 12+ years.",
        master,
    )
    assert not ok
    assert issues


def test_generate_resume_cover_ats_pass(tmp_path):
    master = build_master_resume(persist=True)
    pipeline = DocumentPipeline(master=master, data_dir=tmp_path)
    job = _good_job()
    docs = pipeline.generate_for_job(job)
    assert Path(docs.resume_pdf).exists()
    assert Path(docs.cover_pdf).exists()
    assert docs.integrity_ok
    text = extract_pdf_text(Path(docs.resume_pdf))
    assert "PROFESSIONAL SUMMARY" in text.upper() or "Professional Summary" in text or "PROFESSIONAL SUMMARY" in text
    assert master.full_name.split()[0] in text
    assert "Python" in text or "python" in text.lower()
    # Reparse ATS
    ats = assess_ats_pdf(
        Path(docs.resume_pdf),
        job_title=job.title,
        job_description=job.description_text,
        threshold=80.0,
    )
    assert ats.combined_score >= 80
    assert ats.passed
    assert docs.ats.passed
