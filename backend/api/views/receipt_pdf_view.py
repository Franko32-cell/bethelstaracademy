from io import BytesIO
import os
from urllib.parse import quote
import re
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from PIL import Image as PilImage, ImageOps

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

import requests

from apps.fees.models import Fee, PaymentTransaction
from apps.students.models import Student

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

BLUE   = colors.HexColor("#1e40af")
LBLUE  = colors.HexColor("#dbeafe")
DGRAY  = colors.HexColor("#374151")
LGRAY  = colors.HexColor("#9ca3af")
WHITE  = colors.white
GREEN  = colors.HexColor("#16a34a")
LGREEN = colors.HexColor("#dcfce7")
RED    = colors.HexColor("#dc2626")
LRED   = colors.HexColor("#fef2f2")
BLACK  = colors.HexColor("#111827")

TERM_LABELS = {"term1": "Term 1", "term2": "Term 2", "term3": "Term 3"}
LOGO_PATH   = os.path.join(settings.BASE_DIR, "static", "images", "logo.jpeg")

W = A5[0] - 24 * mm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def para(text, size=9, bold=False, color=DGRAY, align=TA_LEFT):
    return Paragraph(str(text), ParagraphStyle(
        "p",
        parent=getSampleStyleSheet()["Normal"],
        fontSize=size,
        fontName="Helvetica-Bold" if bold else "Helvetica",
        textColor=color,
        alignment=align,
        leading=size + 4,
        spaceAfter=0,
    ))


def rcp(txn_id):
    return f"RCP-{txn_id:06d}"


def load_logo():
    try:
        if os.path.exists(LOGO_PATH):
            return Image(LOGO_PATH, width=16 * mm, height=16 * mm)
    except Exception:
        pass
    return None


def load_student_photo(student, size=18 * mm):
    try:
        if not student.photo:
            return None
        photo_url = student.photo.url
        if not photo_url.startswith("http"):
            path = os.path.join(settings.MEDIA_ROOT, str(student.photo))
            if os.path.exists(path):
                with open(path, "rb") as f:
                    img_bytes = BytesIO(f.read())
            else:
                return None
        else:
            resp = requests.get(photo_url, timeout=5, stream=True)
            resp.raise_for_status()
            img_bytes = BytesIO()
            for chunk in resp.iter_content(chunk_size=8192):
                img_bytes.write(chunk)
            img_bytes.seek(0)

        # Resize before loading into ReportLab — major memory saving
        pil_img = PilImage.open(img_bytes)
        pil_img = ImageOps.exif_transpose(pil_img)

        target_px = int(size * 3.78)  # mm to pixels approx
        pil_img.thumbnail((target_px, target_px), PilImage.LANCZOS)

        if pil_img.mode in ("RGBA", "P", "CMYK", "LA", "L"):
            pil_img = pil_img.convert("RGB")

        corrected = BytesIO()
        pil_img.save(corrected, format="JPEG", quality=75, optimize=True)
        corrected.seek(0)
        pil_img.close()

        return Image(corrected, width=size, height=size)

    except Exception:
        pass
    return None


def draw_void_watermark(canvas, doc):
    """Big diagonal VOID across the page (drawn behind the content)."""
    canvas.saveState()
    canvas.setFillColor(RED)
    canvas.setFillAlpha(0.15)
    canvas.setFont("Helvetica-Bold", 96)
    canvas.translate(A5[0] / 2, A5[1] / 2)
    canvas.rotate(35)
    canvas.drawCentredString(0, 0, "VOID")
    canvas.restoreState()


# ---------------------------------------------------------------------------
# Receipt PDF View
# ---------------------------------------------------------------------------

class PaymentReceiptPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, transaction_id):
        # Students must not be able to download other people's receipts.
        # Remove this guard if you intentionally expose receipts to a student/parent portal
        # (in that case, also check the receipt belongs to that student).
        if getattr(request.user, "role", "") == "student":
            return Response(
                {"error": "You do not have permission to download receipts."},
                status=status.HTTP_403_FORBIDDEN,
            )

        txn = get_object_or_404(
            PaymentTransaction.objects.select_related(
                "fee__student__school_class", "fee__school_class", "recorded_by", "voided_by",
            ),
            id=transaction_id,
        )
        fee     = txn.fee
        student = fee.student

        is_void = txn.is_void
        # If this receipt was issued as a correction, find the receipt it replaced
        replaces = PaymentTransaction.objects.filter(replaced_by=txn).only("id").first()

        buffer = BytesIO()
        pdf    = SimpleDocTemplate(
            buffer,
            pagesize=A5,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
        )
        elements = []

        # ── Header ────────────────────────────────────────────────────────
        logo      = load_logo()
        logo_cell = logo if logo else para("", 9)

        title_text  = "PAYMENT RECEIPT - VOID" if is_void else "PAYMENT RECEIPT"
        title_color = RED if is_void else BLACK

        school_block = [
            para("BETHEL STAR ACADEMY", 15, bold=True, color=BLUE, align=TA_CENTER),
            para("POWER KNOWLEDGE WISDOM",  7, color=LGRAY, align=TA_CENTER),
            para("P.O.Box 105, Darkuman",   7, color=LGRAY, align=TA_CENTER),
            Spacer(1, 1 * mm),
            para(title_text, 10, bold=True, color=title_color, align=TA_CENTER),
        ]
        header = Table([[logo_cell, school_block, para("", 9)]], colWidths=[18 * mm, W - 36 * mm, 18 * mm])
        header.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), LRED if is_void else LBLUE),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING",   (0, 0), (0,  0),  5),
            ("BOX",           (0, 0), (-1, -1), 0, BLUE),
        ]))
        elements.append(header)
        elements.append(Spacer(1, 4 * mm))

        # ── VOID banner (top of the page so it can't be missed) ───────────
        if is_void:
            banner = Table([[para(
                "THIS RECEIPT HAS BEEN CANCELLED AND IS NOT VALID AS PROOF OF PAYMENT",
                8, bold=True, color=WHITE, align=TA_CENTER,
            )]], colWidths=[W])
            banner.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), RED),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            elements.append(banner)
            elements.append(Spacer(1, 3 * mm))

        # ── Receipt meta ──────────────────────────────────────────────────
        receipt_no   = rcp(txn.id)
        receipt_date = txn.created_at.strftime("%d %b %Y  %I:%M %p")

        meta = Table([[
            para(f"Receipt No: {receipt_no}", 8, bold=True, color=RED if is_void else BLUE),
            para(f"Date: {receipt_date}", 8, color=DGRAY, align=TA_RIGHT),
        ]], colWidths=[W / 2, W / 2])
        meta.setStyle(TableStyle([
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        elements.append(meta)
        elements.append(Spacer(1, 3 * mm))

        # ── Student info + photo ──────────────────────────────────────────
        billed_class = fee.school_class or student.school_class   # class at time of billing
        class_name = billed_class.name if billed_class else "—"
        term_label = f"{TERM_LABELS.get(fee.term, fee.term)} {fee.year}"

        photo      = load_student_photo(student, size=18 * mm)
        photo_cell = photo if photo else para("", 9)

        def info_row(label, value):
            return [para(label, 8, bold=True, color=BLUE), para(value, 8, color=BLACK)]

        info = Table([
            info_row("Student",      student.full_name),
            info_row("Admission No", student.admission_number),
            info_row("Class",        class_name),
            info_row("Term",         term_label),
        ], colWidths=[28 * mm, W - 28 * mm - 22 * mm])
        info.setStyle(TableStyle([
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("LINEBELOW",     (0, 0), (-1, -2), 0.3, colors.HexColor("#e5e7eb")),
        ]))

        photo_wrapper = Table([[photo_cell]], colWidths=[20 * mm])
        photo_wrapper.setStyle(TableStyle([
            ("BOX",           (0, 0), (-1, -1), 1.2, BLUE),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("BACKGROUND",    (0, 0), (-1, -1), LBLUE),
        ]))

        student_card = Table(
            [[info, photo_wrapper]],
            colWidths=[W - 22 * mm, 22 * mm],
        )
        student_card.setStyle(TableStyle([
            ("BOX",           (0, 0), (-1, -1), 0.6, colors.HexColor("#d1d5db")),
            ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#f9fafb")),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(student_card)
        elements.append(Spacer(1, 4 * mm))

        # ── Payment breakdown ─────────────────────────────────────────────
        elements.append(para("Payment Details", 9, bold=True, color=BLUE))
        elements.append(Spacer(1, 2 * mm))

        breakdown_rows = [
            [para("Description", 8, bold=True, color=BLUE), para("Amount (GHS)", 8, bold=True, color=BLUE, align=TA_RIGHT)],
            [para("School Fees", 8), para(f"{float(fee.amount):,.2f}", 8, align=TA_RIGHT)],
        ]
        if float(fee.book_user_fee) > 0:
            breakdown_rows.append([para("Book User Fee", 8), para(f"{float(fee.book_user_fee):,.2f}", 8, align=TA_RIGHT)])
        if float(fee.workbook_fee) > 0:
            breakdown_rows.append([para("Workbook Fee",  8), para(f"{float(fee.workbook_fee):,.2f}",  8, align=TA_RIGHT)])
        if float(fee.arrears) > 0:
            breakdown_rows.append([para("Arrears", 8, color=RED), para(f"{float(fee.arrears):,.2f}", 8, color=RED, align=TA_RIGHT)])

        # Spacer row marks where the summary block begins
        breakdown_rows.append([para("", 3), para("", 3)])
        divider = len(breakdown_rows) - 1

        breakdown_rows.append([
            para("Total Fee Due", 9, bold=True, color=BLACK),
            para(f"{float(fee.total_amount):,.2f}", 9, bold=True, color=BLACK, align=TA_RIGHT),
        ])

        balance = float(fee.balance)

        if is_void:
            # No "outstanding balance" line: the figure on a cancelled receipt
            # would reflect today's balance, not this payment, and be misleading.
            breakdown_rows.append([
                para("Amount Cancelled (this receipt)", 9, bold=True, color=RED),
                para(f"<strike>{float(txn.amount):,.2f}</strike>", 9, bold=True, color=RED, align=TA_RIGHT),
            ])
            last_bg = LRED
        else:
            breakdown_rows.append([
                para("Amount Paid (this receipt)", 9, bold=True, color=GREEN),
                para(f"{float(txn.amount):,.2f}", 9, bold=True, color=GREEN, align=TA_RIGHT),
            ])
            balance_color = GREEN if balance <= 0 else RED
            breakdown_rows.append([
                para("Outstanding Balance", 9, bold=True, color=balance_color),
                para(f"{balance:,.2f}", 9, bold=True, color=balance_color, align=TA_RIGHT),
            ])
            last_bg = LGREEN if balance <= 0 else LRED

        btbl = Table(breakdown_rows, colWidths=[W - 40 * mm, 40 * mm])
        btbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0),  (-1, 0),              LBLUE),
            ("ROWBACKGROUNDS",(0, 1),  (-1, divider - 1),    [WHITE, colors.HexColor("#f9fafb")]),
            ("BACKGROUND",    (0, divider + 1), (-1, -1),    colors.HexColor("#f0fdf4") if not is_void else LRED),
            ("LINEABOVE",     (0, divider + 1), (-1, divider + 1), 0.8, RED if is_void else BLUE),
            ("BACKGROUND",    (0, -1), (-1, -1),              last_bg),
            ("TOPPADDING",    (0, 0),  (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0),  (-1, -1), 4),
            ("LEFTPADDING",   (0, 0),  (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0),  (-1, -1), 6),
            ("BOX",           (0, 0),  (-1, -1), 0.6, colors.HexColor("#d1d5db")),
            ("GRID",          (0, 0),  (-1, divider - 1), 0.3, colors.HexColor("#e5e7eb")),
        ]))
        elements.append(btbl)
        elements.append(Spacer(1, 5 * mm))

        # ── Payment note ──────────────────────────────────────────────────
        if txn.note:
            note_tbl = Table([[para(f"Note: {txn.note}", 8, color=DGRAY)]], colWidths=[W])
            note_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#fffbeb")),
                ("BOX",           (0, 0), (-1, -1), 0.5, colors.HexColor("#fde68a")),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING",   (0, 0), (-1, -1), 7),
            ]))
            elements.append(note_tbl)
            elements.append(Spacer(1, 4 * mm))

        # ── Replacement reference (this receipt corrects an earlier one) ──
        if replaces and not is_void:
            ref_tbl = Table([[para(
                f"This receipt replaces cancelled receipt {rcp(replaces.id)}.",
                8, bold=True, color=BLUE,
            )]], colWidths=[W])
            ref_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), LBLUE),
                ("BOX",           (0, 0), (-1, -1), 0.5, BLUE),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING",   (0, 0), (-1, -1), 7),
            ]))
            elements.append(ref_tbl)
            elements.append(Spacer(1, 4 * mm))

        # ── Void details ──────────────────────────────────────────────────
        if is_void:
            voided_when = txn.voided_at.strftime("%d %b %Y  %I:%M %p") if txn.voided_at else "—"
            voided_by   = (txn.voided_by.get_full_name() or txn.voided_by.username) if txn.voided_by else "—"
            lines = [
                para(f"Cancelled on: {voided_when}", 8, color=RED),
                para(f"Cancelled by: {voided_by}", 8, color=RED),
                para(f"Reason: {txn.void_reason or '—'}", 8, color=RED),
            ]
            if txn.replaced_by_id:
                lines.append(para(
                    f"Replaced by receipt: {rcp(txn.replaced_by_id)}", 8, bold=True, color=RED,
                ))
            void_tbl = Table([[l] for l in lines], colWidths=[W])
            void_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), LRED),
                ("BOX",           (0, 0), (-1, -1), 0.8, RED),
                ("TOPPADDING",    (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING",   (0, 0), (-1, -1), 7),
            ]))
            elements.append(void_tbl)
            elements.append(Spacer(1, 4 * mm))

        # ── Recorded by ───────────────────────────────────────────────────
        recorded_by = "System"
        if txn.recorded_by:
            recorded_by = txn.recorded_by.get_full_name() or txn.recorded_by.username

        elements.append(para(f"Received by: {recorded_by}", 8, color=LGRAY))
        elements.append(Spacer(1, 5 * mm))

        # ── Status stamp ──────────────────────────────────────────────────
        if is_void:
            stamp_text  = "VOID - CANCELLED"
            stamp_color = RED
            stamp_bg    = LRED
        elif balance <= 0:
            stamp_text  = "✓  PAYMENT RECEIVED"
            stamp_color = GREEN
            stamp_bg    = LGREEN
        else:
            stamp_text  = "◑  PARTIAL PAYMENT"
            stamp_color = colors.HexColor("#d97706")
            stamp_bg    = colors.HexColor("#fffbeb")

        stamp = Table([[para(stamp_text, 11, bold=True, color=stamp_color, align=TA_CENTER)]], colWidths=[W])
        stamp.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), stamp_bg),
            ("BOX",           (0, 0), (-1, -1), 1.5, stamp_color),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        elements.append(stamp)
        elements.append(Spacer(1, 8 * mm))

        # ── Headmaster signature ─────────────────────────────────────────
        # Single signature line reserved for the headmaster only — no other
        # staff signature slot is provided on this receipt.
        signature = Table(
            [[para("", 9), para("_________________________", 9, align=TA_CENTER)]],
            colWidths=[W - 65 * mm, 65 * mm],
        )
        signature.setStyle(TableStyle([
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        elements.append(signature)

        signature_label = Table(
            [[para("", 9), para("Headmaster's Signature", 8, bold=True, color=DGRAY, align=TA_CENTER)]],
            colWidths=[W - 65 * mm, 65 * mm],
        )
        signature_label.setStyle(TableStyle([
            ("TOPPADDING",    (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        elements.append(signature_label)
        elements.append(Spacer(1, 5 * mm))

        # ── Footer ────────────────────────────────────────────────────────
        elements.append(HRFlowable(width="100%", thickness=0.4, color=colors.HexColor("#e5e7eb")))
        elements.append(Spacer(1, 2 * mm))
        if is_void:
            elements.append(para("This receipt is cancelled. Do not accept it as proof of payment.", 7, color=RED, align=TA_CENTER))
            elements.append(para("Bethel Star Academy", 7, color=LGRAY, align=TA_CENTER))
        else:
            elements.append(para("This is an official receipt. Please retain for your records.", 7, color=LGRAY, align=TA_CENTER))
            elements.append(para("Thank you for your payment. — Bethel Star Academy", 7, color=LGRAY, align=TA_CENTER))

        if is_void:
            pdf.build(elements, onFirstPage=draw_void_watermark, onLaterPages=draw_void_watermark)
        else:
            pdf.build(elements)
        pdf_data = buffer.getvalue()
        buffer.close()  # ← free memory immediately

        name_slug = student.student_name.strip().replace(" ", "_")
        if not name_slug:
            name_slug = student.admission_number

        safe_name = re.sub(r'[^A-Za-z0-9_-]+', '_', name_slug).strip("_")
        prefix    = "VOID_receipt" if is_void else "receipt"
        filename  = f"{prefix}_{receipt_no}_{safe_name}.pdf"

        response = HttpResponse(pdf_data, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'
        )
        return response