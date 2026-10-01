import hmac
import hashlib
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum, Count, Q, Prefetch
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action

from apps.fees.models import Fee, PaymentTransaction
from apps.students.models import Student
from api.serializers.fee_serializer import FeeSerializer
from apps.fees.services.termii import TermiiSMSService, TermiiSMSError
from apps.fees.services.templates import fee_payment_received

# ── Audit logging ────────────────────────────────────────────────────────
from apps.audit.models import AuditLog
from apps.audit.services import log_action

logger = logging.getLogger(__name__)

# Non-admins may correct their OWN payments only within this window.
CORRECTION_WINDOW = timedelta(hours=24)


def to_decimal(value, default=Decimal("0")):
    try:
        return Decimal(str(value)) if value not in (None, "") else default
    except Exception:
        return default


def parse_year(value, default=None):
    """Return an int year, `default` if blank, or raise ValueError if invalid."""
    if value in (None, ""):
        return default
    year = int(value)
    if not (2000 <= year <= 2100):
        raise ValueError("year out of range")
    return year


def user_display(user):
    if not user:
        return "System"
    return user.get_full_name() or user.username


def can_correct_payment(user, txn):
    """Admins can always correct. Others only their own entries within 24h."""
    if user.is_superuser or getattr(user, "role", "") == "admin":
        return True
    if txn.recorded_by_id and txn.recorded_by_id == user.id:
        return timezone.now() - txn.created_at <= CORRECTION_WINDOW
    return False


def is_paystack_txn(txn):
    return bool(txn.reference) or "paystack" in (txn.note or "").lower()


def send_payment_sms(fee, amount, txn_id):
    """Send the standard 'payment received' SMS. Never raises."""
    parent_phone = fee.student.parent_phone
    if not parent_phone:
        logger.warning("No parent phone for student %s — SMS skipped", fee.student.full_name)
        return
    message = fee_payment_received(
        parent_name    = fee.student.parent_name or "Parent/Guardian",
        student_name   = fee.student.full_name,
        student_class  = str(fee.student.school_class) if fee.student.school_class else "N/A",
        amount_paid    = amount,
        balance        = fee.balance,
        term           = fee.get_term_display(),
        transaction_id = txn_id,
    )
    try:
        TermiiSMSService().send(phone=parent_phone, message=message)
        logger.info("SMS sent for student %s | txn=%s", fee.student.full_name, txn_id)
    except TermiiSMSError as e:
        logger.error("SMS failed for student %s: %s", fee.student.full_name, e)
    except Exception:
        logger.exception("Unexpected SMS error for student %s", fee.student.full_name)


def send_correction_sms(student, term_label, balance, old_id, old_amount, new_id, new_amount):
    """Tell the parent a receipt was cancelled/replaced. Never raises."""
    if not student.parent_phone:
        return
    name = student.parent_name or "Parent/Guardian"
    if new_id:
        message = (
            f"Dear {name}, a correction was made to a fee payment for {student.full_name} "
            f"({term_label}). Receipt #{old_id} (GHS {old_amount}) is cancelled and replaced by "
            f"receipt #{new_id} (GHS {new_amount}). Outstanding balance: GHS {balance}."
        )
    else:
        message = (
            f"Dear {name}, receipt #{old_id} (GHS {old_amount}) for {student.full_name} "
            f"({term_label}) has been cancelled. Outstanding balance: GHS {balance}. "
            f"Please contact the school office if you have questions."
        )
    try:
        TermiiSMSService().send(phone=student.parent_phone, message=message)
    except TermiiSMSError as e:
        logger.error("Correction SMS failed for %s: %s", student.full_name, e)
    except Exception:
        logger.exception("Unexpected correction SMS error for %s", student.full_name)


# ──────────────────────────────────────────────────────────────────────────────
# Paystack Webhook
# ──────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([AllowAny])
def paystack_webhook(request):
    """
    Paystack POSTs here after every successful charge.
    - Verifies HMAC-SHA512 signature
    - Idempotent: unique `reference` column + exact-match check
    - Atomic and row-locked so concurrent payments can't overwrite each other
    """
    secret    = getattr(settings, "PAYSTACK_SECRET_KEY", "")
    signature = request.headers.get("x-paystack-signature", "")
    body      = request.body

    expected = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, signature):
        logger.warning("Paystack webhook: invalid signature received")
        return Response({"error": "Invalid signature"}, status=status.HTTP_400_BAD_REQUEST)

    payload = request.data
    event   = payload.get("event")

    if event != "charge.success":
        return Response({"status": "ignored"})

    data        = payload.get("data", {})
    reference   = data.get("reference", "")
    amount_kobo = data.get("amount", 0)
    amount      = Decimal(str(amount_kobo)) / 100

    meta   = data.get("metadata", {}) or {}
    fields = {f["variable_name"]: f["value"] for f in meta.get("custom_fields", [])}
    fee_id = fields.get("fee_id")

    if not fee_id:
        logger.error("Paystack webhook: no fee_id in metadata. ref=%s", reference)
        return Response({"status": "no fee_id"})

    if not reference:
        logger.error("Paystack webhook: missing reference")
        return Response({"status": "no reference"})

    # Legacy rows have the reference only inside `note`, so check both.
    def already_recorded():
        return PaymentTransaction.objects.filter(
            Q(reference=reference) | Q(note__icontains=reference)
        ).exists()

    if already_recorded():
        logger.info("Paystack webhook: duplicate ref=%s — skipping", reference)
        return Response({"status": "duplicate"})

    try:
        with transaction.atomic():
            try:
                fee = (
                    Fee.objects
                    .select_for_update(of=("self",))
                    .select_related("student", "student__school_class")
                    .get(id=fee_id)
                )
            except Fee.DoesNotExist:
                logger.error("Paystack webhook: Fee %s not found", fee_id)
                return Response({"status": "fee not found"})

            # Re-check inside the lock (another delivery may have just finished)
            if already_recorded():
                return Response({"status": "duplicate"})

            if amount > fee.balance:
                logger.warning(
                    "Paystack webhook: amount %s exceeds balance %s for fee %s — capping",
                    amount, fee.balance, fee_id,
                )
                amount = fee.balance

            if amount <= 0:
                logger.warning(
                    "Paystack webhook: fee %s already fully paid, ref=%s — needs manual refund review",
                    fee_id, reference,
                )
                return Response({"status": "already paid"})

            old_balance = fee.balance
            fee.paid += amount
            fee.save()

            txn = PaymentTransaction.objects.create(
                fee         = fee,
                amount      = amount,
                note        = f"Paystack webhook ref: {reference}",
                reference   = reference,
                recorded_by = None,
            )

            log_action(
                request=request,
                action=AuditLog.Action.PAYMENT_PROCESSED,
                module=AuditLog.Module.FEES,
                resource_type="PaymentTransaction",
                resource_id=txn.id,
                resource_repr=f"Payment: {fee.student.full_name} — {fee.get_term_display()} (Paystack)",
                previous_value={"balance": str(old_balance)},
                new_value={"balance": str(fee.balance), "amount_paid": str(amount)},
                description=f"Paystack webhook ref: {reference}",
            )
    except IntegrityError:
        # Unique `reference` collision from a simultaneous duplicate delivery
        logger.info("Paystack webhook: duplicate ref=%s (integrity) — skipping", reference)
        return Response({"status": "duplicate"})

    send_payment_sms(fee, amount, txn.id)
    return Response({"status": "ok"})


# ──────────────────────────────────────────────────────────────────────────────
# FeeViewSet
# ──────────────────────────────────────────────────────────────────────────────

class FeeViewSet(ModelViewSet):

    queryset           = Fee.objects.all().select_related("student")
    serializer_class   = FeeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # PERF: prefetch nested transactions (and their recorded_by) so the
        # list endpoint doesn't do an N+1 cascade. `.fee.student` resolves from
        # the already-loaded Fee instance, so no extra query for it.
        qs = (
            super()
            .get_queryset()
            .select_related("student")
            .prefetch_related(
                Prefetch(
                    "transactions",
                    queryset=PaymentTransaction.objects
                        .select_related("recorded_by", "voided_by")
                        .order_by("-created_at"),
                )
            )
        )
        params = self.request.query_params

        student      = params.get("student")
        term         = params.get("term")
        year         = params.get("year")
        school_class = params.get("school_class")
        status_param = params.get("status")

        if student:      qs = qs.filter(student_id=student)
        if term:         qs = qs.filter(term=term)
        if year:
            try:
                qs = qs.filter(year=int(year))
            except ValueError:
                pass
        if school_class: qs = qs.filter(school_class_id=school_class)

        if status_param == "paid":
            qs = qs.filter(balance__lte=0)
        elif status_param == "partial":
            qs = qs.filter(paid__gt=0, balance__gt=0)
        elif status_param == "unpaid":
            qs = qs.filter(paid=0)

        return qs

    # ── Never silently destroy a fee that has money recorded on it ────────────

    def destroy(self, request, *args, **kwargs):
        fee = self.get_object()
        if fee.paid > 0 or fee.transactions.filter(is_void=False).exists():
            return Response(
                {"error": "This fee has recorded payments. Void the payments first, "
                          "then delete the fee."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        student_name = fee.student.full_name
        term_label   = fee.get_term_display()
        fee_id       = fee.id
        fee.delete()
        log_action(
            request=request,
            action=AuditLog.Action.DELETE,
            module=AuditLog.Module.FEES,
            resource_type="Fee",
            resource_id=fee_id,
            resource_repr=f"Fee deleted: {student_name} — {term_label}",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Record a payment ──────────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        self.get_object()  # permission / 404 check using the filtered queryset

        amount = request.data.get("amount")
        note   = request.data.get("note", "")

        if amount is None:
            return Response({"error": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = Decimal(str(amount))
        except Exception:
            return Response({"error": "amount must be a number"}, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0:
            return Response({"error": "amount must be greater than 0"}, status=status.HTTP_400_BAD_REQUEST)

        paystack_ref = None
        if note and "paystack ref:" in note.lower():
            paystack_ref = note.split(":")[-1].strip() or None

        try:
            with transaction.atomic():
                # Lock the row so two simultaneous payments can't overwrite each other
                fee = (
                    Fee.objects
                    .select_for_update(of=("self",))
                    .select_related("student", "student__school_class")
                    .get(pk=pk)
                )

                if amount > fee.balance:
                    return Response(
                        {"error": f"Amount exceeds outstanding balance of {fee.balance}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if paystack_ref and PaymentTransaction.objects.filter(
                    Q(reference=paystack_ref) | Q(note__icontains=paystack_ref)
                ).exists():
                    logger.info("pay(): duplicate Paystack ref=%s — skipping", paystack_ref)
                    return Response(FeeSerializer(fee).data)

                old_balance = fee.balance
                fee.paid += amount
                fee.save()

                txn = PaymentTransaction.objects.create(
                    fee         = fee,
                    amount      = amount,
                    note        = note,
                    reference   = paystack_ref,
                    recorded_by = request.user,
                )

                log_action(
                    request=request,
                    action=AuditLog.Action.PAYMENT_PROCESSED,
                    module=AuditLog.Module.FEES,
                    resource_type="PaymentTransaction",
                    resource_id=txn.id,
                    resource_repr=f"Payment: {fee.student.full_name} — {fee.get_term_display()}",
                    previous_value={"balance": str(old_balance)},
                    new_value={"balance": str(fee.balance), "amount_paid": str(amount)},
                    description=note or "",
                )
        except IntegrityError:
            return Response({"error": "This payment reference was already recorded."},
                            status=status.HTTP_400_BAD_REQUEST)

        send_payment_sms(fee, amount, txn.id)

        return Response({
            **FeeSerializer(fee).data,
            "transaction_id": txn.id,
        })

    # ── Void a wrong payment (and optionally replace it) ──────────────────────

    @action(detail=True, methods=["post"], url_path="correct-payment")
    def correct_payment(self, request, pk=None):
        """
        Body: { transaction_id, reason, amount? }
        - amount omitted  -> payment is just cancelled (voided)
        - amount provided -> payment is voided and replaced with the new amount
        The original row is never deleted: it is flagged void and linked to
        its replacement, so the audit trail stays intact.
        """
        self.get_object()  # permission / 404 check

        txn_id     = request.data.get("transaction_id")
        reason     = (request.data.get("reason") or "").strip()
        new_amount = request.data.get("amount")

        if not txn_id or not reason:
            return Response(
                {"error": "transaction_id and reason are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_amount in (None, ""):
            new_amount = None
        else:
            try:
                new_amount = Decimal(str(new_amount))
            except Exception:
                return Response({"error": "amount must be a number"}, status=status.HTTP_400_BAD_REQUEST)
            if new_amount <= 0:
                return Response({"error": "amount must be greater than 0"},
                                status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            fee = (
                Fee.objects
                .select_for_update(of=("self",))
                .select_related("student", "student__school_class")
                .get(pk=pk)
            )

            try:
                old_txn = fee.transactions.select_for_update().get(pk=txn_id, is_void=False)
            except PaymentTransaction.DoesNotExist:
                return Response(
                    {"error": "Transaction not found or already voided"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if not can_correct_payment(request.user, old_txn):
                return Response(
                    {"error": "You can only correct your own payments within 24 hours. "
                              "Ask an administrator to make this correction."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if is_paystack_txn(old_txn):
                return Response(
                    {"error": "Online (Paystack) payments can't be voided here. "
                              "Refund them through Paystack instead."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            old_paid   = fee.paid
            old_amount = old_txn.amount
            paid_after_void = max(Decimal("0"), fee.paid - old_amount)

            # Validate the replacement BEFORE writing anything
            if new_amount is not None:
                outstanding = fee.total_amount - paid_after_void
                if new_amount > outstanding:
                    return Response(
                        {"error": f"Amount exceeds outstanding balance of {outstanding}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # 1) Void the wrong payment (row is kept)
            old_txn.is_void     = True
            old_txn.voided_at   = timezone.now()
            old_txn.voided_by   = request.user
            old_txn.void_reason = reason
            old_txn.save()
            fee.paid = paid_after_void

            # 2) Optionally record the correct payment
            new_txn = None
            if new_amount is not None:
                fee.paid += new_amount
                new_txn = PaymentTransaction.objects.create(
                    fee         = fee,
                    amount      = new_amount,
                    note        = f"Correction of receipt #{old_txn.id}: {reason}",
                    recorded_by = request.user,
                )
                old_txn.replaced_by = new_txn
                old_txn.save(update_fields=["replaced_by"])

            fee.save()  # recalculates balance

            log_action(
                request=request,
                action=AuditLog.Action.PAYMENT_PROCESSED,
                module=AuditLog.Module.FEES,
                resource_type="PaymentTransaction",
                resource_id=old_txn.id,
                resource_repr=f"Payment VOIDED: {fee.student.full_name} — {fee.get_term_display()}",
                previous_value={"paid": str(old_paid), "voided_amount": str(old_amount)},
                new_value={
                    "paid": str(fee.paid),
                    "replacement_amount": str(new_amount) if new_amount is not None else None,
                    "replacement_txn": new_txn.id if new_txn else None,
                },
                description=reason,
            )

            # Capture values for the SMS (sent only after the DB commit succeeds)
            student    = fee.student
            term_label = fee.get_term_display()
            balance    = fee.balance
            old_id     = old_txn.id
            new_id     = new_txn.id if new_txn else None

            transaction.on_commit(
                lambda: send_correction_sms(
                    student, term_label, balance, old_id, old_amount, new_id, new_amount,
                )
            )

        # Re-read with prefetched transactions so the response is fresh
        fee = self.get_queryset().get(pk=pk)
        return Response({
            **FeeSerializer(fee).data,
            "voided_transaction_id": old_id,
            "transaction_id": new_id,
        })

    # ── List payment transactions for a fee record ────────────────────────────

    @action(detail=True, methods=["get"], url_path="transactions")
    def transactions(self, request, pk=None):
        fee          = self.get_object()
        transactions = fee.transactions.select_related("recorded_by", "voided_by").all()

        data = [
            {
                "id":          t.id,
                "amount":      str(t.amount),
                "note":        t.note,
                "recorded_by": user_display(t.recorded_by),
                "created_at":  t.created_at.strftime("%d %b %Y, %I:%M %p"),
                "date":        t.created_at.strftime("%d %b %Y"),
                "time":        t.created_at.strftime("%I:%M %p"),
                "is_void":     t.is_void,
                "void_reason": t.void_reason,
                "voided_by":   user_display(t.voided_by) if t.voided_by else None,
                "replaced_by": t.replaced_by_id,
                "can_correct": (not t.is_void)
                               and (not is_paystack_txn(t))
                               and can_correct_payment(request.user, t),
            }
            for t in transactions
        ]

        return Response(data)

    # ── List all payment transactions for a given date ────────────────────────
    # Powers the "Receipts by Date" tab / bulk end-of-day receipt printing.
    # NOTE: this is a separate action from the detail=True `transactions`
    # action above. DRF routes them differently (/fees/<pk>/transactions/
    # vs /fees/transactions/) based on detail=True/False, so reusing the
    # same url_path is fine — they do not collide.

    @action(detail=False, methods=["get"], url_path="transactions")
    def transactions_by_date(self, request):
        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"error": "date is required (YYYY-MM-DD)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = (
            PaymentTransaction.objects
            .filter(created_at__date=date_str)
            .select_related("fee__student", "fee__student__school_class", "recorded_by")
            .order_by("created_at")
        )

        data = []
        for t in qs:
            fee          = t.fee
            total_amount = fee.total_amount

            # Balance as of THIS payment, not the fee's current (possibly
            # later) balance — sum everything paid on this fee up to and
            # including this transaction's timestamp. This keeps a reprinted
            # receipt from a previous day accurate even if more payments
            # have been recorded on the fee since.
            paid_to_date = (
                fee.transactions
                .filter(created_at__lte=t.created_at)
                .aggregate(total=Sum("amount"))["total"]
                or Decimal("0")
            )
            balance_after   = total_amount - paid_to_date
            is_full_payment = balance_after <= 0

            data.append({
                "id":                t.id,
                "student_name":      fee.student.full_name,
                "admission_number":  fee.student.admission_number,
                "school_class_name": str(fee.student.school_class) if fee.student.school_class else None,
                "amount":            str(t.amount),
                "note":              t.note,
                "recorded_by": (
                    t.recorded_by.get_full_name() or t.recorded_by.username
                    if t.recorded_by else "System"
                ),
                "term":              fee.term,
                "year":              t.created_at.year,
                "date":              t.created_at.strftime("%d %b %Y"),
                "time":              t.created_at.strftime("%I:%M %p"),
                "total_amount":      str(total_amount),
                "paid_to_date":      str(paid_to_date),
                "balance":           str(balance_after),
                "is_full_payment":   is_full_payment,
            })

        return Response(data)

    # ── Assign fee to a single student ────────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="assign-student")
    def assign_student(self, request):
        student_id = request.data.get("student")
        term       = request.data.get("term")
        amount     = request.data.get("amount")

        if not all([student_id, term, amount]):
            return Response(
                {"error": "student, term and amount are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            year = parse_year(request.data.get("year"), default=timezone.now().year)
        except ValueError:
            return Response({"error": "year must be a valid year"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return Response({"error": "Student not found"}, status=status.HTTP_404_NOT_FOUND)

        fee, is_new = Fee.objects.get_or_create(
            student=student,
            term=term,
            year=year,
            defaults={
                "amount":        to_decimal(amount),
                "book_user_fee": to_decimal(request.data.get("book_user_fee")),
                "workbook_fee":  to_decimal(request.data.get("workbook_fee")),
                "arrears":       to_decimal(request.data.get("arrears")),
                "paid":          Decimal("0"),
            },
        )

        if not is_new:
            fee.amount        = to_decimal(amount)
            fee.book_user_fee = to_decimal(request.data.get("book_user_fee"), fee.book_user_fee)
            fee.workbook_fee  = to_decimal(request.data.get("workbook_fee"),  fee.workbook_fee)
            fee.arrears       = to_decimal(request.data.get("arrears"),       fee.arrears)
            fee.save()

        log_action(
            request=request,
            action=AuditLog.Action.CREATE if is_new else AuditLog.Action.FEE_UPDATE,
            module=AuditLog.Module.FEES,
            resource_type="Fee",
            resource_id=fee.id,
            resource_repr=f"Fee: {student.full_name} — {fee.get_term_display()} {fee.year}",
            new_value={"amount": str(fee.amount), "arrears": str(fee.arrears)},
        )

        return Response(
            FeeSerializer(fee).data,
            status=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK,
        )

    # ── Bulk assign fees to a whole class ─────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="bulk-assign")
    def bulk_assign(self, request):
        school_class = request.data.get("school_class")
        term         = request.data.get("term")
        amount       = request.data.get("amount")

        if not all([school_class, term, amount]):
            return Response(
                {"error": "school_class, term and amount are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            year = parse_year(request.data.get("year"), default=timezone.now().year)
        except ValueError:
            return Response({"error": "year must be a valid year"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount        = Decimal(str(amount))
            book_user_fee = to_decimal(request.data.get("book_user_fee"))
            workbook_fee  = to_decimal(request.data.get("workbook_fee"))
        except Exception:
            return Response({"error": "Fee values must be numbers"}, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0:
            return Response({"error": "amount must be greater than 0"}, status=status.HTTP_400_BAD_REQUEST)

        students = Student.objects.filter(school_class_id=school_class)
        if not students.exists():
            return Response({"error": "No students found for this class"},
                            status=status.HTTP_404_NOT_FOUND)

        created = updated = 0

        with transaction.atomic():
            for student in students:
                fee, is_new = Fee.objects.get_or_create(
                    student=student,
                    term=term,
                    year=year,
                    defaults={
                        "amount":        amount,
                        "book_user_fee": book_user_fee,
                        "workbook_fee":  workbook_fee,
                        "paid":          Decimal("0"),
                    },
                )
                if not is_new:
                    fee.amount        = amount
                    fee.book_user_fee = book_user_fee
                    fee.workbook_fee  = workbook_fee
                    fee.save()
                    updated += 1
                else:
                    created += 1

        log_action(
            request=request,
            action=AuditLog.Action.FEE_UPDATE,
            module=AuditLog.Module.FEES,
            resource_type="Fee",
            resource_repr=f"Bulk fee assignment: class {school_class}, {term} {year}",
            new_value={"amount": str(amount), "created": created, "updated": updated},
            description=f"{created} created, {updated} updated",
        )

        return Response({"created": created, "updated": updated, "total": created + updated})

    # ── Add arrears to a specific student fee record ──────────────────────────

    @action(detail=True, methods=["post"], url_path="add-arrears")
    def add_arrears(self, request, pk=None):
        fee     = self.get_object()
        arrears = request.data.get("arrears")

        if arrears is None:
            return Response({"error": "arrears is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            arrears = Decimal(str(arrears))
        except Exception:
            return Response({"error": "arrears must be a number"}, status=status.HTTP_400_BAD_REQUEST)

        if arrears < 0:
            return Response({"error": "arrears cannot be negative"}, status=status.HTTP_400_BAD_REQUEST)

        old_arrears = fee.arrears
        fee.arrears = arrears
        fee.save()

        log_action(
            request=request,
            action=AuditLog.Action.FEE_UPDATE,
            module=AuditLog.Module.FEES,
            resource_type="Fee",
            resource_id=fee.id,
            resource_repr=f"Arrears updated: {fee.student.full_name} — {fee.get_term_display()}",
            previous_value={"arrears": str(old_arrears)},
            new_value={"arrears": str(arrears)},
        )

        return Response(FeeSerializer(fee).data)

    # ── Summary stats for a class + term ──────────────────────────────────────

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        school_class = request.query_params.get("school_class")
        term         = request.query_params.get("term")

        if not school_class or not term:
            return Response(
                {"error": "school_class and term are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            year = parse_year(request.query_params.get("year"), default=timezone.now().year)
        except ValueError:
            return Response({"error": "year must be a valid year"}, status=status.HTTP_400_BAD_REQUEST)

        fees = (
            Fee.objects
            .filter(school_class_id=school_class, term=term, year=year)
            .select_related("student")
            .prefetch_related(
                Prefetch(
                    "transactions",
                    queryset=PaymentTransaction.objects
                        .select_related("recorded_by", "voided_by")
                        .order_by("-created_at"),
                )
            )
        )

        agg = fees.aggregate(
            total_fees     = Sum("amount"),
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

        total_expected = (
            (agg["total_fees"]    or 0) +
            (agg["total_books"]   or 0) +
            (agg["total_wb"]      or 0) +
            (agg["total_arrears"] or 0)
        )

        recent_payments = (
            PaymentTransaction.objects
            .filter(fee__in=fees, is_void=False)
            .select_related("fee__student", "recorded_by")
            .order_by("-created_at")[:20]
        )
        recent = [
            {
                "id":           t.id,
                "student_name": t.fee.student.full_name,
                "amount":       str(t.amount),
                "note":         t.note,
                "recorded_by":  user_display(t.recorded_by),
                "created_at":   t.created_at.strftime("%d %b %Y, %I:%M %p"),
            }
            for t in recent_payments
        ]

        return Response({
            "total_expected":  total_expected,
            "total_fees":      agg["total_fees"]     or 0,
            "total_books":     agg["total_books"]    or 0,
            "total_workbooks": agg["total_wb"]       or 0,
            "total_arrears":   agg["total_arrears"]  or 0,
            "total_paid":      agg["total_paid"]     or 0,
            "total_balance":   agg["total_balance"]  or 0,
            "total_students":  agg["total_students"] or 0,
            "fully_paid":      agg["fully_paid"]     or 0,
            "partial":         agg["partial"]        or 0,
            "unpaid":          agg["unpaid"]         or 0,
            "recent_payments": recent,
            "records":         FeeSerializer(fees, many=True).data,
        })

    # ── Preview fees to delete for a class (+ optional term) + year ──────────

    @action(detail=False, methods=["get"], url_path="delete-preview")
    def delete_preview(self, request):
        school_class = request.query_params.get("school_class")
        term         = request.query_params.get("term")   # optional ("All Terms")
        year         = request.query_params.get("year")

        if not school_class or not year:
            return Response(
                {"error": "school_class and year are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            year = parse_year(year)
        except ValueError:
            return Response({"error": "year must be a valid year"}, status=status.HTTP_400_BAD_REQUEST)

        fees = Fee.objects.filter(
            school_class_id=school_class,
            year=year,
        ).select_related("student")
        if term:
            fees = fees.filter(term=term)

        totals = fees.aggregate(
            total_billed=Sum("amount"),
            total_books=Sum("book_user_fee"),
            total_wb=Sum("workbook_fee"),
            total_arrears=Sum("arrears"),
            total_paid=Sum("paid"),
        )
        total_billed = (
            (totals["total_billed"]  or 0) + (totals["total_books"]   or 0) +
            (totals["total_wb"]      or 0) + (totals["total_arrears"] or 0)
        )

        data = [
            {
                "fee_id":           fee.id,
                "student_id":       fee.student.id,
                "admission_number": fee.student.admission_number,
                "student_name":     fee.student.full_name,
                "term":             fee.term,
                "year":             fee.year,
                "amount":           str(fee.amount),
                "total_amount":     str(fee.total_amount),
                "paid":             str(fee.paid),
                "balance":          str(fee.balance),
                "created_at":       fee.created_at.strftime("%d %b %Y, %I:%M %p"),
            }
            for fee in fees
        ]

        return Response(
            {
                "count":        len(data),
                "total_billed": float(total_billed),
                "total_paid":   float(totals["total_paid"] or 0),
                "fees":         data,
            },
            status=status.HTTP_200_OK,
        )

    # ── Delete fees for a class (+ optional term) + year ─────────────────────

    @action(detail=False, methods=["delete"], url_path="delete-class-fees")
    def delete_class_fees(self, request):
        school_class = request.query_params.get("school_class")
        term         = request.query_params.get("term")   # optional ("All Terms")
        year         = request.query_params.get("year")

        if not school_class or not year:
            return Response(
                {"error": "school_class and year are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            year = parse_year(year)
        except ValueError:
            return Response({"error": "year must be a valid year"}, status=status.HTTP_400_BAD_REQUEST)

        qs = Fee.objects.filter(
            school_class_id=school_class,
            year=year,
        )
        if term:
            qs = qs.filter(term=term)

        paid_total = qs.aggregate(s=Sum("paid"))["s"] or 0
        deleted_count, _ = qs.delete()

        log_action(
            request=request,
            action=AuditLog.Action.DELETE,
            module=AuditLog.Module.FEES,
            resource_type="Fee",
            resource_repr=f"Bulk delete: class {school_class}, {term or 'all terms'}, {year}",
            previous_value={"recorded_payments_total": str(paid_total)},
            description=f"{deleted_count} record(s) deleted (incl. cascaded payment rows)",
        )

        return Response(
            {"detail": f"{deleted_count} record(s) deleted successfully."},
            status=status.HTTP_200_OK,
        )

    # ── Fetch fees for unassigned students ────────────────────────────────────

    @action(detail=False, methods=["get"], url_path="unassigned-fees")
    def unassigned_fees(self, request):
        fees = Fee.objects.filter(
            student__school_class__isnull=True
        ).select_related("student", "student__user")

        data = [
            {
                "fee_id":           fee.id,
                "term":             fee.term,
                "student_id":       fee.student.id,
                "admission_number": fee.student.admission_number,
                "student_name":     fee.student.full_name,
                "school_class":     None,
                "amount":           str(fee.amount),
                "total_amount":     str(fee.total_amount),
                "paid":             str(fee.paid),
                "balance":          str(fee.balance),
                "created_at":       fee.created_at.strftime("%d %b %Y, %I:%M %p"),
            }
            for fee in fees
        ]

        return Response(data, status=status.HTTP_200_OK)

    # ── Delete wrongly billed fees for unassigned students ────────────────────

    @action(detail=False, methods=["delete"], url_path="unassigned-fees/delete")
    def delete_unassigned_fees(self, request):
        fee_id = request.query_params.get("fee_id")

        if fee_id:
            try:
                fee = Fee.objects.get(id=fee_id, student__school_class__isnull=True)
            except Fee.DoesNotExist:
                return Response(
                    {"error": "Fee not found or student is already assigned to a class."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            student_name = fee.student.full_name
            fee.delete()
            log_action(
                request=request,
                action=AuditLog.Action.DELETE,
                module=AuditLog.Module.FEES,
                resource_type="Fee",
                resource_id=fee_id,
                resource_repr=f"Unassigned fee deleted: {student_name}",
            )
            return Response(
                {"detail": f"Fee {fee_id} deleted successfully."},
                status=status.HTTP_200_OK,
            )

        deleted_count, _ = Fee.objects.filter(
            student__school_class__isnull=True
        ).delete()

        log_action(
            request=request,
            action=AuditLog.Action.DELETE,
            module=AuditLog.Module.FEES,
            resource_type="Fee",
            resource_repr="Bulk delete: unassigned-student fees",
            description=f"{deleted_count} fee record(s) deleted",
        )

        return Response(
            {"detail": f"{deleted_count} fee record(s) deleted for unassigned students."},
            status=status.HTTP_200_OK,
        )