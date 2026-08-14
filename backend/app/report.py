"""
Report generation module.

Turns an AnalysisRecord into a downloadable plain-text or PDF summary.
Uses reportlab for PDF so we don't depend on any external binaries.
"""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    ListFlowable,
    ListItem,
)

from app.models import AnalysisRecord


def generate_text_report(record: AnalysisRecord) -> str:
    a = record.analysis
    sb = a.section_breakdown

    lines = []
    lines.append("=" * 60)
    lines.append("CV ANALYSIS REPORT")
    lines.append("=" * 60)
    lines.append(f"File: {record.filename}")
    lines.append(f"Generated: {record.created_at}")
    lines.append("")
    lines.append(f"OVERALL SCORE: {a.overall_score}/100")
    lines.append(f"ATS COMPATIBILITY SCORE: {a.ats_score}/100")
    lines.append(f"HUMAN TOUCH SCORE: {a.human_touch_score}/100")
    lines.append(f"  -> {a.human_touch_comment}")
    lines.append("")

    lines.append("-" * 60)
    lines.append("SECTION BREAKDOWN")
    lines.append("-" * 60)
    for label, section in [
        ("Contact Info", sb.contact_info),
        ("Summary", sb.summary),
        ("Experience", sb.experience),
        ("Education", sb.education),
        ("Skills", sb.skills),
        ("Formatting", sb.formatting),
    ]:
        lines.append(f"{label}: {section.score}/100")
        if section.comment:
            lines.append(f"  {section.comment}")
    lines.append("")

    lines.append("-" * 60)
    lines.append("STRENGTHS")
    lines.append("-" * 60)
    for s in a.strengths:
        lines.append(f"+ {s}")
    lines.append("")

    lines.append("-" * 60)
    lines.append("WEAKNESSES / GAPS")
    lines.append("-" * 60)
    for w in a.weaknesses:
        lines.append(f"- {w}")
    lines.append("")

    lines.append("-" * 60)
    lines.append("ATS ISSUES")
    lines.append("-" * 60)
    for issue in a.ats_issues:
        lines.append(f"! {issue}")
    lines.append("")

    lines.append("-" * 60)
    lines.append(f"SUGGESTED REWRITE — {a.suggested_rewrite.section_name}")
    lines.append("-" * 60)
    if a.suggested_rewrite.original_excerpt:
        lines.append("Original:")
        lines.append(a.suggested_rewrite.original_excerpt)
        lines.append("")
    lines.append("Suggested rewrite:")
    lines.append(a.suggested_rewrite.rewritten_text)
    lines.append("")

    if a.job_match:
        lines.append("-" * 60)
        lines.append("JOB DESCRIPTION MATCH")
        lines.append("-" * 60)
        lines.append(f"Match score: {a.job_match.match_score}/100")
        lines.append(f"Matched keywords: {', '.join(a.job_match.matched_keywords)}")
        lines.append(f"Missing keywords: {', '.join(a.job_match.missing_keywords)}")
        lines.append(f"Notes: {a.job_match.notes}")

    return "\n".join(lines)


def generate_pdf_report(record: AnalysisRecord) -> bytes:
    a = record.analysis
    sb = a.section_breakdown

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCustom", parent=styles["Title"], fontSize=20, spaceAfter=6
    )
    heading_style = ParagraphStyle(
        "HeadingCustom",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=14,
        spaceAfter=6,
        textColor=colors.HexColor("#1f2937"),
    )
    body_style = styles["BodyText"]
    meta_style = ParagraphStyle(
        "Meta", parent=styles["Normal"], fontSize=9, textColor=colors.grey
    )

    elements = []
    elements.append(Paragraph("CV Analysis Report", title_style))
    elements.append(
        Paragraph(f"File: {record.filename} &nbsp;|&nbsp; Generated: {record.created_at}", meta_style)
    )
    elements.append(Spacer(1, 12))

    score_table_data = [
        ["Overall Score", "ATS Compatibility", "Human Touch"],
        [f"{a.overall_score}/100", f"{a.ats_score}/100", f"{a.human_touch_score}/100"],
    ]
    score_table = Table(score_table_data, colWidths=[160, 160, 160])
    score_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("FONTSIZE", (0, 1), (-1, 1), 16),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 1), (-1, 1), 10),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
            ]
        )
    )
    elements.append(score_table)

    elements.append(Paragraph("Section Breakdown", heading_style))
    section_rows = [["Section", "Score", "Comment"]]
    for label, section in [
        ("Contact Info", sb.contact_info),
        ("Summary", sb.summary),
        ("Experience", sb.experience),
        ("Education", sb.education),
        ("Skills", sb.skills),
        ("Formatting", sb.formatting),
    ]:
        section_rows.append([label, f"{section.score}/100", section.comment or "-"])
    section_table = Table(section_rows, colWidths=[100, 60, 320])
    section_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(section_table)

    elements.append(Paragraph("Strengths", heading_style))
    elements.append(
        ListFlowable(
            [ListItem(Paragraph(s, body_style)) for s in a.strengths],
            bulletType="bullet",
        )
    )

    elements.append(Paragraph("Weaknesses / Gaps", heading_style))
    elements.append(
        ListFlowable(
            [ListItem(Paragraph(w, body_style)) for w in a.weaknesses],
            bulletType="bullet",
        )
    )

    elements.append(Paragraph("ATS Compatibility Issues", heading_style))
    elements.append(
        ListFlowable(
            [ListItem(Paragraph(i, body_style)) for i in a.ats_issues],
            bulletType="bullet",
        )
    )

    elements.append(Paragraph("Human Touch Assessment", heading_style))
    elements.append(Paragraph(a.human_touch_comment or "-", body_style))

    elements.append(
        Paragraph(f"Suggested Rewrite — {a.suggested_rewrite.section_name}", heading_style)
    )
    if a.suggested_rewrite.original_excerpt:
        elements.append(Paragraph("<b>Original:</b>", body_style))
        elements.append(Paragraph(a.suggested_rewrite.original_excerpt, body_style))
        elements.append(Spacer(1, 6))
    elements.append(Paragraph("<b>Rewrite:</b>", body_style))
    elements.append(Paragraph(a.suggested_rewrite.rewritten_text, body_style))

    if a.job_match:
        elements.append(Paragraph("Job Description Match", heading_style))
        elements.append(Paragraph(f"Match score: {a.job_match.match_score}/100", body_style))
        elements.append(
            Paragraph(f"Matched keywords: {', '.join(a.job_match.matched_keywords)}", body_style)
        )
        elements.append(
            Paragraph(f"Missing keywords: {', '.join(a.job_match.missing_keywords)}", body_style)
        )
        elements.append(Paragraph(a.job_match.notes, body_style))

    doc.build(elements)
    return buffer.getvalue()
