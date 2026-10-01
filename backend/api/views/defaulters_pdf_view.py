# api/views/defaulters_pdf_view.py
#
# Printable list of all debtors (students with an outstanding balance).
# Respects the same filters as the Defaulters tab: ?term=&year=&school_class=
# Leave a filter out to include everything (e.g. no term = all terms).

import os
from io import BytesIO
from collections import defaultdict
from datetime import datetime

from django.conf import settings
from django.http import HttpResponse

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fees.models import Fee
from apps.classes.models import SchoolClass
from api.views.accounts_view import TERM_LABELS, _year, _class_name

BLUE   = colors.HexColor("#1e40af")
LBLUE  = colors.HexColor("#dbeafe")
DGRAY  = colors.HexColor("#374151")
LGRAY  = colors.HexColor("#9ca3af")
RED    = colors.HexColor("#dc2626")
BLACK  = colors.HexColor("#111827")
ROWALT = colors.HexColor("#f9fafb")
LINE   = colors.HexColor("#e5e7eb")

LOGO_PATH = os.path.join(settings.BASE_DIR, "static", "images", "logo.jpeg")

PAGE   = landscape(A4)
MARGIN = 10 * mm
W      = PAGE[0] - 2 * MARGIN


def para(text, size=8, bold=False, color=DGRAY, align=TA_LEFT):
    return Paragraph(str(text), ParagraphStyle(
        "p",
        parent=getSampleStyleSheet()["Normal"],
        fontSize=size,
        fontName="Helvetica-Bold" if bold else "Helvetica",
        textColor=color,
        alignment=align,
        leading=size + 3,
        spaceAfter=0,
    ))


def money(value):
    return f"{float(value):,.2f}"


def load_logo():
    try:
        if os.path.exists(LOGO_PATH):
            return Image(LOGO_PATH, width=14 * mm, height=14 * mm)
    except Exception:
        pass
    return None


class DefaultersPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Same guard as receipts: student accounts must not see other families' debts.
        if getattr(request.user, "role", "") == "student":
            return Response(
                {"error": "You do not have permission to view this report."},
                status=status.HTTP_403_FORBIDDEN,
            )

        term         = request.query_params.get("term")
        school_class = request.query_params.get("school_class")
        year         = _year(request)

        fees = (
            Fee.objects
            .filter(balance__gt=0)
            .select_related("student", "school_class", "student__school_class")
        )
        if term:         fees = fees.filter(term=term)
        if year:         fees = fees.filter(year=year)
        if school_class: fees = fees.filter(school_class_id=school_class)

        # Group by the class the student was billed in, then sort by name
        groups = defaultdict(list)
        for fee in fees:
            cname = _class_name(fee)
            groups[cname if cname != "-" else "Unassigned"].append(fee)
        for items in groups.values():
            items.sort(key=lambda f: (f.student.full_name.lower(), f.term))

        # ── Filter labels for the subtitle ────────────────────────────────
        class_label = "All classes"
        if school_class:
            try:
                obj = SchoolClass.objects.filter(pk=school_class).first()
                class_label = obj.name if obj else "Selected class"
            except (ValueError, TypeError):
                class_label = "Selected class"
        term_label = TERM_LABELS.get(term, "All terms") if term else "All terms"
        year_label = str(year) if year else "All years"

        # ── Document ──────────────────────────────────────────────────────
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=PAGE,
            leftMargin=MARGIN, rightMargin=MARGIN,
            topMargin=MARGIN, bottomMargin=14 * mm,
            title="Debtors List",
        )
        els = []

        # Header
        logo = load_logo()
        title_block = [
            para("BETHEL STAR ACADEMY", 14, bold=True, color=BLUE, align=TA_CENTER),
            para("DEBTORS LIST - OUTSTANDING FEES", 10, bold=True, color=BLACK, align=TA_CENTER),
            para(f"{class_label}  |  {term_label}  |  {year_label}", 8, color=DGRAY, align=TA_CENTER),
        ]
        header = Table(
            [[logo if logo else "", title_block, ""]],
            colWidths=[20 * mm, W - 40 * mm, 20 * mm],
        )
        header.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, -1), LBLUE),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        els.append(header)
        els.append(Spacer(1, 3 * mm))

        generated_by = request.user.get_full_name() or request.user.username
        els.append(para(
            f"Printed {datetime.now().strftime('%d %b %Y, %I:%M %p')} by {generated_by}",
            7, color=LGRAY, align=TA_RIGHT,
        ))
        els.append(Spacer(1, 2 * mm))

        # ── Table ─────────────────────────────────────────────────────────
        col_w = [10 * mm, 62 * mm, 30 * mm, 36 * mm, 22 * mm, 29 * mm, 29 * mm, 29 * mm, 28 * mm]
        scale = W / sum(col_w)
        col_w = [c * scale for c in col_w]

        head = ["#", "Student", "Adm. No", "Class", "Term", "Total (GHS)", "Paid (GHS)", "Balance (GHS)", "Arrears (GHS)"]
        data = [[
            para(h, 8, bold=True, color=BLUE, align=TA_RIGHT if i >= 5 else TA_LEFT)
            for i, h in enumerate(head)
        ]]
        styles = [
            ("BACKGROUND", (0, 0), (-1, 0), LBLUE),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, BLUE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]

        n = 0
        g_total = g_paid = g_bal = g_arr = 0
        g_count = 0

        for cname in sorted(groups):
            items = groups[cname]

            # Class heading row
            data.append([para(f"{cname}  ({len(items)})", 9, bold=True, color=BLUE)] + [""] * 8)
            r = len(data) - 1
            styles += [
                ("SPAN", (0, r), (-1, r)),
                ("BACKGROUND", (0, r), (-1, r), colors.HexColor("#eff6ff")),
                ("LINEABOVE", (0, r), (-1, r), 0.4, BLUE),
            ]

            c_total = c_paid = c_bal = c_arr = 0
            for i, fee in enumerate(items):
                n += 1
                total = float(fee.total_amount)
                paid, bal, arr = float(fee.paid), float(fee.balance), float(fee.arrears)
                c_total += total; c_paid += paid; c_bal += bal; c_arr += arr

                data.append([
                    para(n, 8),
                    para(fee.student.full_name, 8, bold=True, color=BLACK),
                    para(fee.student.admission_number, 8),
                    para(cname, 8),
                    para(f"{TERM_LABELS.get(fee.term, fee.term)} {fee.year}", 8),
                    para(money(total), 8, align=TA_RIGHT),
                    para(money(paid), 8, color=colors.HexColor("#16a34a"), align=TA_RIGHT),
                    para(money(bal), 8, bold=True, color=RED, align=TA_RIGHT),
                    para(money(arr) if arr > 0 else "-", 8, align=TA_RIGHT),
                ])
                r = len(data) - 1
                styles.append(("LINEBELOW", (0, r), (-1, r), 0.3, LINE))
                if i % 2 == 1:
                    styles.append(("BACKGROUND", (0, r), (-1, r), ROWALT))

            # Class subtotal
            data.append([
                para(f"Subtotal - {cname}", 8, bold=True, color=BLACK, align=TA_RIGHT),
                "", "", "", "",
                para(money(c_total), 8, bold=True, color=BLACK, align=TA_RIGHT),
                para(money(c_paid), 8, bold=True, color=BLACK, align=TA_RIGHT),
                para(money(c_bal), 8, bold=True, color=RED, align=TA_RIGHT),
                para(money(c_arr), 8, bold=True, color=BLACK, align=TA_RIGHT),
            ])
            r = len(data) - 1
            styles += [
                ("SPAN", (0, r), (4, r)),
                ("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f3f4f6")),
                ("LINEABOVE", (0, r), (-1, r), 0.5, LGRAY),
            ]

            g_total += c_total; g_paid += c_paid; g_bal += c_bal; g_arr += c_arr
            g_count += len(items)

        if g_count == 0:
            els.append(Spacer(1, 20 * mm))
            els.append(para("No outstanding balances found for the selected filters.", 11, bold=True,
                            color=DGRAY, align=TA_CENTER))
        else:
            # Grand total
            data.append([
                para(f"GRAND TOTAL ({g_count} record{'s' if g_count != 1 else ''})", 9, bold=True, color=colors.white, align=TA_RIGHT),
                "", "", "", "",
                para(money(g_total), 9, bold=True, color=colors.white, align=TA_RIGHT),
                para(money(g_paid), 9, bold=True, color=colors.white, align=TA_RIGHT),
                para(money(g_bal), 9, bold=True, color=colors.white, align=TA_RIGHT),
                para(money(g_arr), 9, bold=True, color=colors.white, align=TA_RIGHT),
            ])
            r = len(data) - 1
            styles += [
                ("SPAN", (0, r), (4, r)),
                ("BACKGROUND", (0, r), (-1, r), BLUE),
                ("TOPPADDING", (0, r), (-1, r), 5),
                ("BOTTOMPADDING", (0, r), (-1, r), 5),
            ]

            tbl = Table(data, colWidths=col_w, repeatRows=1)
            tbl.setStyle(TableStyle(styles))
            els.append(tbl)

        # Page footer (page numbers)
        def footer(canvas, _doc):
            canvas.saveState()
            canvas.setFont("Helvetica", 7)
            canvas.setFillColor(LGRAY)
            canvas.drawString(MARGIN, 8 * mm, "Bethel Star Academy - Debtors List")
            canvas.drawRightString(PAGE[0] - MARGIN, 8 * mm, f"Page {_doc.page}")
            canvas.restoreState()

        doc.build(els, onFirstPage=footer, onLaterPages=footer)
        pdf = buffer.getvalue()
        buffer.close()

        filename = f"debtors_{term or 'all-terms'}_{year or 'all-years'}_{datetime.now().strftime('%Y%m%d')}.pdf"
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response
