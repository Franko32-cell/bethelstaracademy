# api/views/accounts_view.py

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from django.db.models import Sum, Count, Q, F
from django.utils.dateparse import parse_date

from apps.fees.models import Fee, PaymentTransaction
from api.views.fee_view import can_correct_payment, is_paystack_txn

TERM_LABELS = {
    "term1": "Term 1",
    "term2": "Term 2",
    "term3": "Term 3",
}


def _year(request):
    """Validated ?year= param as int, or None."""
    try:
        y = int(request.query_params.get("year", ""))
    except (TypeError, ValueError):
        return None
    return y if 2000 <= y <= 2100 else None


def _class_name(fee):
    """Class the student was in when billed; falls back to their current class."""
    cls = fee.school_class or fee.student.school_class
    return cls.name if cls else "-"


def _user_label(user, empty="System"):
    if not user:
        return empty
    return user.get_full_name() or user.username


class AccountsDashboardView(APIView):
    """Overall financial summary across all classes and terms."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        term         = request.query_params.get("term")
        school_class = request.query_params.get("school_class")
        year         = _year(request)

        fees = Fee.objects.all()
        if term:         fees = fees.filter(term=term)
        if year:         fees = fees.filter(year=year)
        if school_class: fees = fees.filter(school_class_id=school_class)

        agg = fees.aggregate(
            total_expected = Sum("amount"),
            total_books    = Sum("book_user_fee"),
            total_wb       = Sum("workbook_fee"),
            total_arrears  = Sum("arrears"),
            total_paid     = Sum("paid"),
            total_balance  = Sum("balance"),
            total_students = Count("id"),
            fully_paid     = Count("id", filter=Q(balance__lte=0)),
            partial        = Count("id", filter=Q(paid__gt=0, balance__gt=0)),
            unpaid         = Count("id", filter=Q(paid=0)),
        )

        total_billed = (
            (agg["total_expected"] or 0) +
            (agg["total_books"]    or 0) +
            (agg["total_wb"]       or 0) +
            (agg["total_arrears"]  or 0)
        )

        # Per-term breakdown
        term_breakdown = []
        for t in ["term1", "term2", "term3"]:
            t_fees = fees.filter(term=t)
            t_agg  = t_fees.aggregate(
                billed = Sum("amount"),
                paid   = Sum("paid"),
                bal    = Sum("balance"),
            )
            term_breakdown.append({
                "term":    t,
                "label":   TERM_LABELS[t],
                "billed":  float(t_agg["billed"] or 0),
                "paid":    float(t_agg["paid"]   or 0),
                "balance": float(t_agg["bal"]    or 0),
            })

        # Recent transactions — voided payments are excluded.
        recent_qs = (
            PaymentTransaction.objects
            .filter(is_void=False, fee__in=fees)
            .select_related("fee__student", "fee__school_class", "fee__student__school_class", "recorded_by")
            .order_by("-created_at")[:10]
        )
        recent_transactions = [
            {
                "id":               t.id,
                "student_name":     t.fee.student.full_name,
                "admission_number": t.fee.student.admission_number,
                "class":            _class_name(t.fee),
                "term":             TERM_LABELS.get(t.fee.term, t.fee.term),
                "amount":           float(t.amount),
                "note":             t.note,
                "recorded_by":      _user_label(t.recorded_by, "System"),
                "created_at":       t.created_at.strftime("%d %b %Y, %I:%M %p"),
            }
            for t in recent_qs
        ]

        return Response({
            "total_billed":        float(total_billed),
            "total_paid":          float(agg["total_paid"]    or 0),
            "total_balance":       float(agg["total_balance"] or 0),
            "total_students":      agg["total_students"]      or 0,
            "fully_paid":          agg["fully_paid"]          or 0,
            "partial":             agg["partial"]             or 0,
            "unpaid":              agg["unpaid"]              or 0,
            "collection_rate":     round(
                float(agg["total_paid"] or 0) / float(total_billed) * 100, 1
            ) if total_billed else 0,
            "term_breakdown":      term_breakdown,
            "recent_transactions": recent_transactions,
        })


class IncomeLedgerView(APIView):
    """
    Full transaction log with filtering.
    Voided payments are hidden by default. Auditors can pass ?include_void=1
    to see them (each row carries is_void / void_reason).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        term         = request.query_params.get("term")
        school_class = request.query_params.get("school_class")
        student      = request.query_params.get("student")
        year         = _year(request)
        include_void = request.query_params.get("include_void") in ("1", "true", "True")
        date_from    = request.query_params.get("date_from")
        date_to      = request.query_params.get("date_to")
        search       = request.query_params.get("q", "").strip()

        transactions = PaymentTransaction.objects.select_related(
            "fee__student",
            "fee__school_class",
            "fee__student__school_class",
            "recorded_by",
        ).order_by("-created_at")

        if not include_void:
            transactions = transactions.filter(is_void=False)

        if term:         transactions = transactions.filter(fee__term=term)
        if year:         transactions = transactions.filter(fee__year=year)
        if school_class: transactions = transactions.filter(fee__school_class_id=school_class)
        if student:      transactions = transactions.filter(fee__student_id=student)

        if date_from:
            parsed_date = parse_date(date_from)
            if parsed_date is None:
                return Response({"error": "date_from must be YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)
            transactions = transactions.filter(created_at__date__gte=parsed_date)
        if date_to:
            parsed_date = parse_date(date_to)
            if parsed_date is None:
                return Response({"error": "date_to must be YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)
            transactions = transactions.filter(created_at__date__lte=parsed_date)
        if search:
            search_filter = (
                Q(fee__student__first_name__icontains=search)
                | Q(fee__student__last_name__icontains=search)
                | Q(fee__student__student_name__icontains=search)
                | Q(fee__student__user__first_name__icontains=search)
                | Q(fee__student__user__last_name__icontains=search)
                | Q(fee__student__user__username__icontains=search)
                | Q(fee__student__admission_number__icontains=search)
                | Q(note__icontains=search)
            )
            receipt_search = search.upper()
            if receipt_search.startswith("RCP-"):
                receipt_search = receipt_search[4:]
            if receipt_search.isdecimal():
                search_filter |= Q(pk=int(receipt_search))
            transactions = transactions.filter(search_filter)

        # Money collected never counts voided rows, even when they are listed.
        agg = transactions.filter(is_void=False).aggregate(total=Sum("amount"))

        data = [
            {
                "id":               t.id,
                "fee_id":           t.fee_id,
                "receipt_no":       f"RCP-{t.id:06d}",
                "student_name":     t.fee.student.full_name,
                "admission_number": t.fee.student.admission_number,
                "class":            _class_name(t.fee),
                "term":             TERM_LABELS.get(t.fee.term, t.fee.term),
                "year":             t.fee.year,
                "amount":           float(t.amount),
                "note":             t.note,
                "recorded_by":      _user_label(t.recorded_by, "-"),
                "created_at":       t.created_at.strftime("%d %b %Y, %I:%M %p"),
                "is_void":          t.is_void,
                "void_reason":      t.void_reason,
                "can_correct":      (not t.is_void)
                                    and (not is_paystack_txn(t))
                                    and can_correct_payment(request.user, t),
            }
            for t in transactions
        ]

        return Response({
            "total_collected": float(agg["total"] or 0),
            "count":           len(data),
            "transactions":    data,
        })


class FeeCollectionReportView(APIView):
    """Per-class fee collection breakdown."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        term = request.query_params.get("term")
        year = _year(request)

        fees = Fee.objects.all()
        if term:
            fees = fees.filter(term=term)
        if year:
            fees = fees.filter(year=year)

        class_data = (
            fees
            .values(
                class_id   = F("school_class__id"),
                class_name = F("school_class__name"),
            )
            .annotate(
                total_billed   = Sum("amount"),
                total_paid     = Sum("paid"),
                total_balance  = Sum("balance"),
                total_students = Count("id"),
                fully_paid     = Count("id", filter=Q(balance__lte=0)),
                unpaid         = Count("id", filter=Q(paid=0)),
            )
            .order_by("class_name")
        )

        rows = []
        for row in class_data:
            billed = float(row["total_billed"] or 0)
            paid   = float(row["total_paid"]   or 0)
            rows.append({
                "class_id":        row["class_id"],
                "class_name":      row["class_name"] or "Unassigned",
                "total_students":  row["total_students"],
                "total_billed":    billed,
                "total_paid":      paid,
                "total_balance":   float(row["total_balance"] or 0),
                "fully_paid":      row["fully_paid"],
                "unpaid":          row["unpaid"],
                "collection_rate": round(paid / billed * 100, 1) if billed else 0,
            })

        return Response(rows)


class DefaultersListView(APIView):
    """Students with outstanding fee balances."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        term         = request.query_params.get("term")
        school_class = request.query_params.get("school_class")
        year         = _year(request)

        fees = (
            Fee.objects
            .filter(balance__gt=0)
            .select_related("student", "school_class", "student__school_class")
            .order_by("-balance")
        )

        if term:         fees = fees.filter(term=term)
        if year:         fees = fees.filter(year=year)
        if school_class: fees = fees.filter(school_class_id=school_class)

        data = [
            {
                "student_id":       fee.student.id,
                "student_name":     fee.student.full_name,
                "admission_number": fee.student.admission_number,
                "class":            _class_name(fee),
                "term":             TERM_LABELS.get(fee.term, fee.term),
                "total_amount":     float(fee.total_amount),
                "paid":             float(fee.paid),
                "balance":          float(fee.balance),
                "arrears":          float(fee.arrears),
            }
            for fee in fees
        ]

        agg = fees.aggregate(total_outstanding=Sum("balance"))

        return Response({
            "total_outstanding": float(agg["total_outstanding"] or 0),
            "count":             len(data),
            "defaulters":        data,
        })