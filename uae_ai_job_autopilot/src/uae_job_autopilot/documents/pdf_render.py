from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def _styles():
    base = getSampleStyleSheet()
    return {
        "name": ParagraphStyle(
            "Name",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            spaceAfter=4,
            leading=16,
        ),
        "meta": ParagraphStyle(
            "Meta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            spaceAfter=8,
            leading=11,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            spaceBefore=8,
            spaceAfter=4,
            leading=13,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            spaceAfter=3,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=11,
            leftIndent=12,
            spaceAfter=2,
        ),
    }


def _esc(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_resume_pdf(structured: dict, path: Path) -> Path:
    """ATS-friendly single-column PDF: standard headings, no tables/graphics."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )
    styles = _styles()
    story = []
    story.append(Paragraph(_esc(structured.get("full_name", "")), styles["name"]))
    meta = " • ".join(
        x
        for x in [
            structured.get("location"),
            structured.get("phone"),
            structured.get("email"),
            structured.get("linkedin"),
        ]
        if x
    )
    story.append(Paragraph(_esc(meta), styles["meta"]))
    if structured.get("headline"):
        story.append(Paragraph(_esc(structured["headline"]), styles["body"]))

    story.append(Paragraph("PROFESSIONAL SUMMARY", styles["h2"]))
    story.append(Paragraph(_esc(structured.get("summary", "")), styles["body"]))

    story.append(Paragraph("SKILLS", styles["h2"]))
    story.append(Paragraph(_esc(", ".join(structured.get("skills") or [])), styles["body"]))

    story.append(Paragraph("WORK EXPERIENCE", styles["h2"]))
    for role in structured.get("experience") or []:
        header = f"{role.get('title', '')} — {role.get('employer', '')}"
        dates = " | ".join(x for x in [role.get("dates"), role.get("location")] if x)
        story.append(Paragraph(_esc(header), styles["body"]))
        if dates:
            story.append(Paragraph(_esc(dates), styles["meta"]))
        for b in role.get("bullets") or []:
            story.append(Paragraph(f"• {_esc(b)}", styles["bullet"]))

    story.append(Paragraph("EDUCATION", styles["h2"]))
    for edu in structured.get("education") or []:
        line = f"{edu.get('degree', '')} — {edu.get('institution', '')}"
        if edu.get("years"):
            line += f" ({edu['years']})"
        story.append(Paragraph(_esc(line), styles["body"]))

    if structured.get("certifications"):
        story.append(Paragraph("CERTIFICATIONS", styles["h2"]))
        for c in structured["certifications"]:
            story.append(Paragraph(f"• {_esc(c)}", styles["bullet"]))

    if structured.get("languages"):
        story.append(Paragraph("LANGUAGES", styles["h2"]))
        story.append(Paragraph(_esc(", ".join(structured["languages"])), styles["body"]))

    doc.build(story)
    return path


def render_cover_letter_pdf(structured: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = _styles()
    story = []
    story.append(Paragraph(_esc(structured.get("full_name", "")), styles["name"]))
    meta = " • ".join(
        x for x in [structured.get("email"), structured.get("phone"), structured.get("location")] if x
    )
    story.append(Paragraph(_esc(meta), styles["meta"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(_esc(structured.get("date", "")), styles["body"]))
    story.append(Paragraph(_esc(structured.get("employer", "Hiring Manager")), styles["body"]))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(_esc(structured.get("salutation", "Dear Hiring Manager,")), styles["body"])
    )
    for para in structured.get("paragraphs") or []:
        story.append(Paragraph(_esc(para), styles["body"]))
        story.append(Spacer(1, 6))
    story.append(Paragraph(_esc(structured.get("closing", "Sincerely,")), styles["body"]))
    story.append(Paragraph(_esc(structured.get("full_name", "")), styles["body"]))
    doc.build(story)
    return path
