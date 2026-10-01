from rest_framework import serializers
from apps.fees.models import Fee, PaymentTransaction


def _user_name(user):
    if not user:
        return None
    return user.get_full_name() or user.username


class PaymentTransactionSerializer(serializers.ModelSerializer):
    recorded_by_name   = serializers.SerializerMethodField()
    voided_by_name     = serializers.SerializerMethodField()
    student_name       = serializers.SerializerMethodField()
    admission_number   = serializers.SerializerMethodField()
    created_at_display = serializers.SerializerMethodField()

    class Meta:
        model  = PaymentTransaction
        fields = [
            "id",
            "fee",
            "student_name",
            "admission_number",
            "amount",
            "recorded_by",
            "recorded_by_name",
            "note",
            "created_at",
            "created_at_display",
            "is_void",
            "voided_at",
            "voided_by_name",
            "void_reason",
            "replaced_by",
        ]
        # Everything audit-related is read-only: it can only change through
        # the correct-payment endpoint.
        read_only_fields = [
            "created_at", "is_void", "voided_at", "voided_by_name",
            "void_reason", "replaced_by",
        ]

    def get_recorded_by_name(self, obj):
        return _user_name(obj.recorded_by)

    def get_voided_by_name(self, obj):
        return _user_name(obj.voided_by)

    def get_student_name(self, obj):
        return obj.fee.student.full_name

    def get_admission_number(self, obj):
        return obj.fee.student.admission_number

    def get_created_at_display(self, obj):
        return obj.created_at.strftime("%d %b %Y, %I:%M %p")


class FeeSerializer(serializers.ModelSerializer):
    student_name     = serializers.SerializerMethodField()
    admission_number = serializers.SerializerMethodField()
    is_fully_paid    = serializers.SerializerMethodField()
    total_amount     = serializers.SerializerMethodField()
    class_name       = serializers.SerializerMethodField()
    transactions     = PaymentTransactionSerializer(many=True, read_only=True)

    class Meta:
        model  = Fee
        fields = [
            "id",
            "student",
            "student_name",
            "admission_number",
            "term",
            "year",
            "school_class",
            "class_name",
            "amount",
            "book_user_fee",
            "workbook_fee",
            "arrears",
            "total_amount",
            "paid",
            "balance",
            "is_fully_paid",
            "transactions",
            "created_at",
            "updated_at",
        ]
        # `paid` is read-only so nobody can PATCH it directly and change money
        # without a transaction record. Payments go through /pay/ and
        # /correct-payment/ only.
        read_only_fields = ["paid", "balance", "school_class", "created_at", "updated_at"]

    def get_student_name(self, obj):
        return obj.student.full_name

    def get_admission_number(self, obj):
        return obj.student.admission_number

    def get_is_fully_paid(self, obj):
        return obj.balance <= 0

    def get_total_amount(self, obj):
        return obj.total_amount

    def get_class_name(self, obj):
        cls = obj.school_class or obj.student.school_class
        return cls.name if cls else None