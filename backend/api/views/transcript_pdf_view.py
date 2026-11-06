import re
from collections import Counter, defaultdict
from io import BytesIO
from urllib.parse import quote
from xml.sax.saxutils import escape

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.results.models import Result
from apps.results.scoring import result_scores
from apps.students.models import Student
from .grades import SCHOOL_MOTTOS, SCHOOL_NAMES, TERM_LABELS, get_grade_and_remark, get_thresholds


TERM_ORDER = {"term1": 1, "term2": 2, "term3": 3}
BLUE = colors.HexColor("#1e3a5f")
LIGHT_BLUE = colors.HexColor("#dbeafe")
LIGHT_GRAY = colors.HexColor("#f1f5f9")


def build_student_transcript_pdf(student_id):
    student = get_object_or_404(
        Student.objects.select_related("school_class", "user"),
        id=student_id,
    )
    results = list(
        Result.objects.filter(student=student)
        .select_related("subject", "school_class")
        .order_by("year", "term", "subject__name")
    )

    grouped_results = defaultdict(list)
    for result in results:
        grouped_results[(result.year, result.term)].append(result)

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"Academic Transcript - {student.full_name}",
        author="Bethel Star Academy",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TranscriptTitle",
        parent=styles["Title"],
        textColor=BLUE,
        fontSize=17,
        leading=21,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    center_style = ParagraphStyle(
        "TranscriptCenter",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#64748b"),
        fontSize=9,
        leading=12,
    )
    section_style = ParagraphStyle(
        "TranscriptSection",
        parent=styles["Heading2"],
        textColor=BLUE,
        fontSize=11,
        leading=14,
        spaceBefore=12,
        spaceAfter=5,
    )
    body_style = ParagraphStyle(
        "TranscriptBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
    )
    elements = [
        Paragraph(escape(SCHOOL_NAMES.get(
            getattr(student.school_class, "level", ""),
            "BETHEL STAR ACADEMY",
        )), title_style),
        Paragraph(escape(SCHOOL_MOTTOS.get(
            getattr(student.school_class, "level", ""),
            "POWER KNOWLEDGE WISDOM",
        )), center_style),
        Spacer(1, 8),
        Paragraph("ACADEMIC TRANSCRIPT", title_style),
        Spacer(1, 8),
    ]

    identity_rows = [
        [
            Paragraph("<b>Student</b>", body_style),
            Paragraph(escape(student.full_name), body_style),
            Paragraph("<b>Admission No.</b>", body_style),
            Paragraph(escape(student.admission_number), body_style),
        ],
        [
            Paragraph("<b>Current Class</b>", body_style),
            Paragraph(escape(str(student.school_class or "—")), body_style),
            Paragraph("<b>Gender</b>", body_style),
            Paragraph(escape(student.gender or "—"), body_style),
        ],
    ]
    identity_table = Table(identity_rows, colWidths=[25 * mm, 60 * mm, 28 * mm, 58 * mm])
    identity_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.extend([identity_table, Spacer(1, 10)])

    if not grouped_results:
        elements.append(Paragraph("No academic results are on record for this student.", body_style))
    else:
        for (year, term), term_results in sorted(
            grouped_results.items(),
            key=lambda item: (item[0][0], TERM_ORDER.get(item[0][1], 99), item[0][1]),
        ):
            class_counts = Counter(
                result.school_class_id
                for result in term_results
                if result.school_class_id is not None
            )
            term_class = next(
                (
                    result.school_class
                    for result in term_results
                    if class_counts and result.school_class_id == class_counts.most_common(1)[0][0]
                ),
                student.school_class,
            )
            class_name = str(term_class) if term_class else "—"
            level = getattr(term_class, "level", "basic_7_9") or "basic_7_9"
            thresholds = get_thresholds(level)

            elements.append(Paragraph(
                f"{escape(TERM_LABELS.get(term, term))} {year} — {escape(class_name)}",
                section_style,
            ))
            rows = [["Subject", "Score", "Grade", "Remark"]]
            scores = []
            for result in term_results:
                score = int(round(result_scores(result)["total"]))
                grade, remark = get_grade_and_remark(score, thresholds)
                scores.append(score)
                rows.append([
                    Paragraph(escape(result.subject.name), body_style),
                    str(score),
                    grade,
                    remark,
                ])
            average = round(sum(scores) / len(scores)) if scores else 0
            rows.append(["Term Average", str(average), "", ""])

            table = Table(rows, colWidths=[88 * mm, 25 * mm, 22 * mm, 36 * mm], repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 1), (-1, -2), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, LIGHT_GRAY]),
                ("BACKGROUND", (0, -1), (-1, -1), LIGHT_BLUE),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            elements.append(table)

    document.build(elements)
    buffer.seek(0)
    filename_student = re.sub(r"[^A-Za-z0-9_-]+", "_", student.admission_number).strip("_")
    filename = f"transcript_{filename_student or student.id}.pdf"
    return buffer, filename


class StudentTranscriptPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        buffer, filename = build_student_transcript_pdf(student_id)
        response = StreamingHttpResponse(iter([buffer.getvalue()]), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'
        )
        response["Content-Length"] = buffer.getbuffer().nbytes
        return response
