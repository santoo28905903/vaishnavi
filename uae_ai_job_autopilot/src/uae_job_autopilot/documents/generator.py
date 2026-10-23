from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from uae_job_autopilot.config import DEFAULT_DATA_DIR, ModelsConfig, Settings, get_settings, load_models_config
from uae_job_autopilot.documents.ats import ATSAssessment, assess_ats_pdf
from uae_job_autopilot.documents.integrity import factual_integrity_check
from uae_job_autopilot.documents.master import MasterResume, load_master_resume
from uae_job_autopilot.documents.pdf_render import render_cover_letter_pdf, render_resume_pdf
from uae_job_autopilot.domain.models import JobPosting
from uae_job_autopilot.models.cache import JsonFileCache
from uae_job_autopilot.models.costs import CostLedger
from uae_job_autopilot.models.routers import GenerativeRouter
from uae_job_autopilot.utils.timeutil import utcnow

logger = logging.getLogger(__name__)


class GeneratedDocuments(BaseModel):
    job_key: str
    resume_version: str
    cover_version: str
    resume_pdf: str
    cover_pdf: str
    resume_text_path: str
    cover_text_path: str
    ats: ATSAssessment
    generator_provider: str
    integrity_ok: bool
    integrity_issues: list[str] = Field(default_factory=list)
    tailored_resume: dict[str, Any] = Field(default_factory=dict)
    tailored_cover: dict[str, Any] = Field(default_factory=dict)


def application_key(job: JobPosting) -> str:
    raw = f"{job.employer}|{job.title}|{job.application_url}".lower()
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class DocumentPipeline:
    def __init__(
        self,
        *,
        master: MasterResume | None = None,
        settings: Settings | None = None,
        models: ModelsConfig | None = None,
        router: GenerativeRouter | None = None,
        ledger: CostLedger | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.master = master or load_master_resume()
        self.settings = settings or get_settings()
        self.models = models or load_models_config()
        self.ledger = ledger or CostLedger()
        self.router = router or GenerativeRouter(
            settings=self.settings, models=self.models, ledger=self.ledger
        )
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.cache = JsonFileCache("generated_documents", root=self.data_dir / "cache")

    def generate_for_job(self, job: JobPosting) -> GeneratedDocuments:
        key = application_key(job)
        cache_key = JsonFileCache.key_for(
            key, self.master.version, job.title, job.employer, (job.description_text or "")[:500]
        )
        cached = self.cache.get_json(cache_key)
        if cached and Path(cached.get("resume_pdf", "")).exists():
            return GeneratedDocuments.model_validate(cached)

        tailored_resume, provider = self._tailor_resume(job)
        tailored_cover, cover_provider = self._tailor_cover(job)
        provider = provider or cover_provider

        resume_blob = json.dumps(tailored_resume) + "\n" + "\n".join(
            tailored_cover.get("paragraphs") or []
        )
        ok, issues = factual_integrity_check(
            resume_blob,
            self.master,
            job_title=job.title,
            job_employer=job.employer,
        )
        if not ok:
            logger.warning("Integrity issues for %s: %s — falling back to deterministic text", key, issues)
            tailored_resume = self._deterministic_resume(job)
            tailored_cover = self._deterministic_cover(job)
            provider = "deterministic_fallback"
            resume_blob = json.dumps(tailored_resume) + "\n" + "\n".join(
                tailored_cover.get("paragraphs") or []
            )
            ok, issues = factual_integrity_check(
                resume_blob, self.master, job_title=job.title, job_employer=job.employer
            )

        out_dir = self.data_dir / "documents" / key
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
        resume_version = f"r-{self.master.version}-{stamp}"
        cover_version = f"c-{self.master.version}-{stamp}"
        resume_pdf = out_dir / f"{resume_version}.pdf"
        cover_pdf = out_dir / f"{cover_version}.pdf"
        resume_txt = out_dir / f"{resume_version}.json"
        cover_txt = out_dir / f"{cover_version}.json"

        render_resume_pdf(tailored_resume, resume_pdf)
        render_cover_letter_pdf(tailored_cover, cover_pdf)
        resume_txt.write_text(json.dumps(tailored_resume, indent=2), encoding="utf-8")
        cover_txt.write_text(json.dumps(tailored_cover, indent=2), encoding="utf-8")

        ats = assess_ats_pdf(
            resume_pdf,
            job_title=job.title,
            job_description=job.description_text,
            threshold=self.models.ats_threshold if hasattr(self.models, "ats_threshold") else 80.0,
            structure_weight=getattr(self.models, "ats_structure_weight", 0.40),
            keyword_weight=getattr(self.models, "ats_keyword_weight", 0.60),
        )
        # If ATS fails keyword coverage, reorder skills toward job keywords and re-render once
        if not ats.passed and ats.keywords_missed:
            tailored_resume = self._boost_keywords(tailored_resume, ats.keywords_missed)
            render_resume_pdf(tailored_resume, resume_pdf)
            resume_txt.write_text(json.dumps(tailored_resume, indent=2), encoding="utf-8")
            ats = assess_ats_pdf(
                resume_pdf,
                job_title=job.title,
                job_description=job.description_text,
                threshold=80.0,
            )

        result = GeneratedDocuments(
            job_key=key,
            resume_version=resume_version,
            cover_version=cover_version,
            resume_pdf=str(resume_pdf),
            cover_pdf=str(cover_pdf),
            resume_text_path=str(resume_txt),
            cover_text_path=str(cover_txt),
            ats=ats,
            generator_provider=provider,
            integrity_ok=ok,
            integrity_issues=issues,
            tailored_resume=tailored_resume,
            tailored_cover=tailored_cover,
        )
        self.cache.set_json(cache_key, json.loads(result.model_dump_json()))
        return result

    def _tailor_resume(self, job: JobPosting) -> tuple[dict[str, Any], str]:
        base = self._deterministic_resume(job)
        if not self.router.available_providers():
            return base, "deterministic"
        prompt = self._resume_prompt(job, base)
        try:
            gen = self.router.generate(prompt, operation="tailor_resume")
            text = gen.get("text") or ""
            # Expect JSON; if not, keep deterministic
            m = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not m:
                return base, "deterministic"
            parsed = json.loads(m.group(0))
            # Merge: only allow reordering / selecting from master bullets
            merged = self._merge_resume_json(base, parsed)
            ok, _ = factual_integrity_check(
                json.dumps(merged), self.master, job_title=job.title, job_employer=job.employer
            )
            if not ok:
                return base, "deterministic"
            return merged, str(gen.get("provider") or "generative")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Generative resume failed: %s", exc)
            return base, "deterministic"

    def _tailor_cover(self, job: JobPosting) -> tuple[dict[str, Any], str]:
        base = self._deterministic_cover(job)
        if not self.router.available_providers():
            return base, "deterministic"
        prompt = (
            "Write a truthful 3-paragraph cover letter as JSON with keys "
            "paragraphs (array of 3 strings). Use ONLY facts from the candidate profile. "
            "Do not invent employers, degrees, metrics, or visa status.\n"
            f"Candidate: {self.master.full_name}, {self.master.headline}\n"
            f"Summary: {self.master.summary[:500]}\n"
            f"Skills: {', '.join(self.master.skills[:20])}\n"
            f"Recent role: {self.master.experience[0].title if self.master.experience else ''} "
            f"at {self.master.experience[0].employer if self.master.experience else ''}\n"
            f"Job: {job.title} at {job.employer} in {job.location_raw}\n"
            f"Job description excerpt: {(job.description_text or '')[:800]}\n"
            "Return JSON only."
        )
        try:
            gen = self.router.generate(prompt, operation="tailor_cover")
            text = gen.get("text") or ""
            m = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not m:
                return base, "deterministic"
            parsed = json.loads(m.group(0))
            paras = parsed.get("paragraphs")
            if not isinstance(paras, list) or len(paras) < 2:
                return base, "deterministic"
            cover = dict(base)
            cover["paragraphs"] = [str(p) for p in paras[:4]]
            ok, _ = factual_integrity_check(
                "\n".join(cover["paragraphs"]),
                self.master,
                job_title=job.title,
                job_employer=job.employer,
            )
            if not ok:
                return base, "deterministic"
            return cover, str(gen.get("provider") or "generative")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Generative cover failed: %s", exc)
            return base, "deterministic"

    def _deterministic_resume(self, job: JobPosting) -> dict[str, Any]:
        keywords = re.findall(r"[A-Za-z][A-Za-z0-9+#.]{2,}", f"{job.title} {job.description_text or ''}")
        kw_lower = {k.lower() for k in keywords}

        def skill_rank(s: str) -> tuple[int, str]:
            return (0 if s.lower() in kw_lower or any(s.lower() in k for k in kw_lower) else 1, s)

        skills = sorted(self.master.skills, key=skill_rank)

        experience = []
        for role in self.master.experience:
            bullets = list(role.bullets)
            bullets.sort(
                key=lambda b: (
                    0
                    if any(k in b.lower() for k in ("rag", "llm", "agent", "vertex", "langgraph", "python"))
                    and any(k in " ".join(kw_lower) for k in ("rag", "llm", "ai", "ml", "python"))
                    else 1,
                    -len(b),
                )
            )
            experience.append(
                {
                    "title": role.title,
                    "employer": role.employer,
                    "dates": " – ".join(x for x in [role.start, role.end] if x),
                    "location": role.location,
                    "bullets": bullets[:6],
                }
            )

        # Emphasize job title keywords in headline without inventing titles held
        headline = self.master.headline
        return {
            "full_name": self.master.full_name,
            "email": self.master.email,
            "phone": self.master.phone,
            "linkedin": self.master.linkedin,
            "location": self.master.location,
            "headline": headline,
            "summary": self.master.summary,
            "skills": skills,
            "experience": experience,
            "education": [e.model_dump() for e in self.master.education],
            "certifications": list(self.master.certifications),
            "languages": list(self.master.languages),
            "target_job_title": job.title,
            "target_employer": job.employer,
        }

    def _deterministic_cover(self, job: JobPosting) -> dict[str, Any]:
        role = self.master.experience[0] if self.master.experience else None
        skills = ", ".join(self.master.skills[:8])
        p1 = (
            f"I am writing to apply for the {job.title} role at {job.employer}. "
            f"I am a {self.master.headline.split('|')[0].strip()} based in {self.master.location}, "
            f"with approximately {4}+ years of experience delivering production Generative AI systems."
        )
        p2 = (
            f"In my current role as {role.title if role else self.master.headline} "
            f"at {role.employer if role else 'Relanto'}, I work on RAG, multi-agent orchestration, "
            f"and cloud AI platforms. Relevant strengths include {skills}."
        )
        if role and role.bullets:
            p2 += f" Example: {role.bullets[0]}"
        p3 = (
            f"I am open to relocating to the UAE and would require employer-sponsored work authorization. "
            f"I would welcome the opportunity to contribute to {job.employer}'s AI initiatives. "
            f"Thank you for your consideration."
        )
        return {
            "full_name": self.master.full_name,
            "email": self.master.email,
            "phone": self.master.phone,
            "location": self.master.location,
            "date": date.today().isoformat(),
            "employer": job.employer,
            "salutation": "Dear Hiring Manager,",
            "paragraphs": [p1, p2, p3],
            "closing": "Sincerely,",
        }

    def _resume_prompt(self, job: JobPosting, base: dict[str, Any]) -> str:
        return (
            "Return JSON only for a tailored resume. You may REORDER skills and SELECT "
            "existing bullets, but must NOT invent employers, degrees, metrics, or skills.\n"
            f"Base JSON:\n{json.dumps(base)[:6000]}\n"
            f"Target job: {job.title} at {job.employer}\n"
            f"Description: {(job.description_text or '')[:1000]}\n"
        )

    def _merge_resume_json(self, base: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        # Skills: only keep those in master
        if isinstance(parsed.get("skills"), list):
            allowed = {s.lower() for s in self.master.skills}
            skills = [s for s in parsed["skills"] if str(s).lower() in allowed]
            if skills:
                merged["skills"] = skills
        # Bullets: only keep bullets that exist in master (substring match)
        master_bullets = [b for r in self.master.experience for b in r.bullets]
        if isinstance(parsed.get("experience"), list):
            new_exp = []
            for i, role in enumerate(merged["experience"]):
                src = parsed["experience"][i] if i < len(parsed["experience"]) else {}
                bullets = []
                for b in src.get("bullets") or role.get("bullets") or []:
                    b = str(b)
                    if any(b in mb or mb in b or b[:40] in mb for mb in master_bullets):
                        bullets.append(next((mb for mb in master_bullets if b[:40] in mb or mb[:40] in b), b))
                role = dict(role)
                role["bullets"] = bullets or role.get("bullets")
                # Lock employer/title to master
                new_exp.append(role)
            merged["experience"] = new_exp
        # Never allow generative overwrite of identity fields
        for k in ("full_name", "email", "phone", "education", "certifications"):
            merged[k] = base[k]
        return merged

    def _boost_keywords(self, resume: dict[str, Any], missed: list[str]) -> dict[str, Any]:
        skills = list(resume.get("skills") or [])
        master_skills_l = {s.lower(): s for s in self.master.skills}
        for m in missed:
            if m.lower() in master_skills_l:
                s = master_skills_l[m.lower()]
                if s in skills:
                    skills.remove(s)
                skills.insert(0, s)
        # Also inject missed tokens into summary only if present in master summary/skills/pdf
        summary = resume.get("summary") or ""
        for m in missed[:5]:
            if m.lower() in self.master.all_attested_text().lower() and m.lower() not in summary.lower():
                summary = f"{summary} Experience includes {m}."
        resume = dict(resume)
        resume["skills"] = skills
        resume["summary"] = summary
        return resume
