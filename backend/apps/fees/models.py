from django.db import models
from django.utils import timezone
from django.conf import settings
from apps.students.models import Student
from apps.classes.models import SchoolClass


TERM_CHOICES = [
    ("term1", "Term 1"),
    ("term2", "Term 2"),
    ("term3", "Term 3"),
]


def current_year():
    return timezone.now().year


class Fee(models.Model):

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="fees",
    )
    term = models.CharField(max_length=10, choices=TERM_CHOICES)

    # Academic year this fee belongs to (e.g. 2026)
    year = models.PositiveSmallIntegerField(default=current_year, db_index=True)

    # Snapshot of the student's class when the fee was created. Student only
    # stores their CURRENT class, so without this, promoting a student would
    # move last year's fees into their new class in every report.
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fees",
    )

    # Core fees
    amount        = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Optional extras
    book_user_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    workbook_fee  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    arrears       = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Payments
    paid    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["student", "term", "year"]
        ordering        = ["-created_at"]

    def __str__(self):
        return f"{self.student} - {self.term} {self.year}"

    @property
    def total_amount(self):
        return self.amount + self.book_user_fee + self.workbook_fee + self.arrears

    def save(self, *args, **kwargs):
        # Snapshot the class once, when the fee is first created
        if self._state.adding and self.school_class_id is None:
            self.school_class_id = self.student.school_class_id
        self.balance = self.total_amount - self.paid
        super().save(*args, **kwargs)


class PaymentTransaction(models.Model):

    fee = models.ForeignKey(
        Fee,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
    )
    note       = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    # ── Paystack idempotency: exact, unique reference (NULL for manual payments)
    reference = models.CharField(
        max_length=100, null=True, blank=True, unique=True, db_index=True,
    )

    # ── Void / correction audit trail (rows are never deleted) ────────────────
    is_void     = models.BooleanField(default=False)
    voided_at   = models.DateTimeField(null=True, blank=True)
    voided_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="voided_payments",
    )
    void_reason = models.TextField(blank=True)
    replaced_by = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replaces",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        tag = " [VOID]" if self.is_void else ""
        return f"{self.fee.student} - GHS {self.amount} - {self.created_at.date()}{tag}"