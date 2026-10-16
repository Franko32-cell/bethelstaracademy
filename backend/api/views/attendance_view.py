# api/views/attendance_view.py
import logging
from datetime import date as date_cls

from django.conf import settings
from django.utils import timezone
from rest_framework import viewsets, filters, permissions
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django_filters.rest_framework import (
    DjangoFilterBackend,
    FilterSet,
    DateFilter,
    CharFilter,
    NumberFilter,
)

from apps.attendance.models import Attendance
from apps.attendance import services
from apps.audit.services import log_action
from apps.teachers.models import Teacher
from api.serializers.attendance_serializer import AttendanceSerializer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def teacher_class_id(user):
    """The single class a teacher is assigned to (Teacher.school_class), or None."""
    return (
        Teacher.objects.filter(user=user)
        .values_list("school_class_id", flat=True)
        .first()
    )


def _parse_date(value, name):
    try:
        return date_cls.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError({name: "Enter a valid date (YYYY-MM-DD)."})


def _snapshot(a):
    return {
        "student": a.student_id,
        "school_class": a.school_class_id,
        "date": str(a.date),
        "status": a.status,
        "notes": a.notes,
    }


# ---------------------------------------------------------------------------
# Pagination — opt-in so existing callers that expect a plain list keep working
# ---------------------------------------------------------------------------
class OptionalPageNumberPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500

    def paginate_queryset(self, queryset, request, view=None):
        if "page" not in request.query_params and "page_size" not in request.query_params:
            return None
        return super().paginate_queryset(queryset, request, view)


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------
class AttendanceFilterBackend(DjangoFilterBackend):
    """
    Accepts friendly aliases (class, academic_year, start_date, end_date) and
    rejects invalid dates / ranges with a clear 400 instead of silently
    returning everything.
    """
    ALIASES = {
        "class": "school_class",
        "class_id": "school_class",
        "academic_year": "year",
        "start_date": "date_after",
        "end_date": "date_before",
    }

    def get_filterset_kwargs(self, request, queryset, view):
        kwargs = super().get_filterset_kwargs(request, queryset, view)
        data = kwargs["data"].copy()
        for old, new in self.ALIASES.items():
            if data.get(old) and not data.get(new):
                data[new] = data[old]
        # "2026/2027" -> 2026
        year = data.get("year")
        if year and "/" in str(year):
            data["year"] = str(year).split("/")[0].strip()
        after, before = data.get("date_after"), data.get("date_before")
        if after:
            after = _parse_date(after, "date_after")
        if before:
            before = _parse_date(before, "date_before")
        if after and before and after > before:
            raise ValidationError(
                {"date_range": "Start date cannot be after the end date."}
            )
        kwargs["data"] = data
        return kwargs


class AttendanceFilter(FilterSet):
    """
    ?date=2026-09-01                     single date
    ?date_after=..&date_before=..        inclusive range (aliases start_date / end_date)
    ?school_class=3  (alias class)       ?student=7   ?teacher=2
    ?term=term1      ?year=2026 (alias academic_year)
    ?status=absent   or ?status=absent,late
    """
    school_class = NumberFilter(field_name="school_class__id")
    student      = NumberFilter(field_name="student__id")
    teacher      = NumberFilter(method="filter_teacher")
    status       = CharFilter(method="filter_status")

    date        = DateFilter(field_name="date")
    date_after  = DateFilter(field_name="date", lookup_expr="gte")
    date_before = DateFilter(field_name="date", lookup_expr="lte")

    term = CharFilter(field_name="term")
    year = NumberFilter(field_name="year")

    class Meta:
        model  = Attendance
        fields = ["date", "school_class", "student", "teacher", "status", "term", "year"]

    def filter_teacher(self, qs, name, value):
        # A teacher is responsible for their assigned class.
        return qs.filter(school_class__teachers__id=value)

    def filter_status(self, qs, name, value):
        wanted = [v.strip() for v in str(value).split(",") if v.strip()]
        valid = {c[0] for c in Attendance.Status.choices}
        bad = [v for v in wanted if v not in valid]
        if bad:
            raise ValidationError({"status": f"Invalid status: {', '.join(bad)}."})
        return qs.filter(status__in=wanted) if wanted else qs


# ---------------------------------------------------------------------------
# ViewSet
# ---------------------------------------------------------------------------
class AttendanceViewSet(viewsets.ModelViewSet):
    """
    CRUD endpoint for Attendance records.

    Access control
    --------------
    - Admins: full access to every record, any class — including delete.
    - Teachers: create/read/update ONLY for the single class they are
      assigned to (Teacher.school_class). Other classes' records are not
      even visible (404 on detail routes), and writes naming another class
      are refused with 403. Teachers can never delete a record.
    - Students: read-only access to their own records.
    - Anyone else: no access.

    Non-school days
    ---------------
    Holidays / closures / weekends (apps.attendance.services) are rejected
    on create and when a record's date is changed — enforced here and in the
    serializer/model, never only in the UI.

    term and year are NEVER accepted from the client: perform_create stamps
    them from settings; updates leave them unchanged.
    """

    serializer_class   = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class   = OptionalPageNumberPagination
    filterset_class    = AttendanceFilter
    filter_backends    = [AttendanceFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    ordering_fields    = ["date", "student", "status", "updated_at"]
    ordering           = ["-date", "student"]
    search_fields      = ["student__first_name", "student__last_name", "student__student_name", "student__admission_number"]

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _current_term() -> str:
        return getattr(settings, "CURRENT_TERM", "term3")

    @staticmethod
    def _current_year() -> int:
        return getattr(settings, "CURRENT_YEAR", timezone.localdate().year)

    @property
    def _role(self):
        return getattr(self.request.user, "role", None)

    # -- queryset (role scoped) -------------------------------------------
    def get_queryset(self):
        qs = Attendance.objects.select_related(
            "student", "student__user", "school_class", "created_by", "updated_by"
        )
        user, role = self.request.user, self._role
        if role == "admin":
            return qs
        if role == "teacher":
            class_id = teacher_class_id(user)
            return qs.filter(school_class_id=class_id) if class_id else qs.none()
        if role == "student":
            return qs.filter(student__user=user)
        return qs.none()

    # -- writes -----------------------------------------------------------
    def _assert_can_write_class(self, school_class):
        role = self._role
        if role == "admin":
            return
        if role == "teacher":
            class_id = teacher_class_id(self.request.user)
            if class_id and school_class and school_class.pk == class_id:
                return
            raise PermissionDenied(
                "You do not have permission to manage attendance for this class."
            )
        raise PermissionDenied("You do not have permission to modify attendance records.")

    def perform_create(self, serializer):
        self._assert_can_write_class(serializer.validated_data.get("school_class"))
        obj = serializer.save(
            term=self._current_term(),
            year=self._current_year(),
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        log_action(
            self.request, action="create", module="attendance",
            resource_type="Attendance", resource_id=obj.pk, resource_repr=str(obj),
            new_value=_snapshot(obj),
            description=f"Marked {obj.student} {obj.get_status_display()} on {obj.date}",
        )

    def perform_update(self, serializer):
        instance = serializer.instance
        before = _snapshot(instance)
        self._assert_can_write_class(serializer.validated_data.get("school_class", instance.school_class))
        obj = serializer.save(updated_by=self.request.user)
        log_action(
            self.request, action="attendance_update", module="attendance",
            resource_type="Attendance", resource_id=obj.pk, resource_repr=str(obj),
            previous_value=before, new_value=_snapshot(obj),
            description=f"Updated attendance for {obj.student} on {obj.date}",
        )

    def perform_destroy(self, instance):
        # Deletion is admin-only. A hidden button is not a security control,
        # so this is enforced server-side. (Teachers requesting another
        # class's record never get here: get_object() already 404s.)
        if self._role != "admin":
            raise PermissionDenied("Only administrators can delete attendance records.")
        before = _snapshot(instance)
        label, pk = str(instance), instance.pk
        instance.delete()
        log_action(
            self.request, action="delete", module="attendance",
            resource_type="Attendance", resource_id=pk, resource_repr=label,
            previous_value=before,
            description=f"Deleted attendance record: {label}",
        )

    # -- summary ----------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """
        GET /api/attendance/summary/  — same filters as the list endpoint.

        Percentages use actual school days only: weekends, holidays and
        closures are excluded, and excused days count neither for nor against
        the student. Also returns the period, the number of school days in
        it, and the holidays that were excluded.
        """
        qs = self.filter_queryset(self.get_queryset())
        params = request.query_params

        start = params.get("date_after") or params.get("start_date") or params.get("date")
        end = params.get("date_before") or params.get("end_date") or params.get("date")
        start = _parse_date(start, "start_date") if start else None
        end = _parse_date(end, "end_date") if end else None
        if not start or not end:
            bounds = qs.order_by().values_list("date", flat=True)
            dates = list(bounds.distinct())
            if dates:
                start = start or min(dates)
                end = end or max(dates)

        period = {"start": None, "end": None}
        school_days, holidays = 0, []
        if start and end:
            period = {"start": start.isoformat(), "end": end.isoformat()}
            capped_end = min(end, services.today())
            school_days = services.count_school_days(start, capped_end)
            holidays = [d for d in services.non_school_days(start, end) if d["type"] != "weekend"]

        totals = services.attendance_counts(qs)
        totals["school_days"] = school_days

        by_student = services.attendance_counts_by(
            qs, "student_id", "student__admission_number",
            "student__first_name", "student__last_name", "student__student_name",
        )
        students = []
        for r in by_student:
            name = (
                f"{r['student__first_name']} {r['student__last_name']}".strip()
                or r["student__student_name"]
                or r["student__admission_number"]
            )
            students.append({
                "student": r["student_id"],
                "student_name": name,
                "admission_number": r["student__admission_number"],
                **{k: r[k] for k in ("present", "absent", "late", "excused", "attended", "counted_days", "percentage")},
            })
        students.sort(key=lambda r: r["student_name"].lower())

        by_class = [
            {
                "school_class": r["school_class_id"],
                "class_name": r["school_class__name"],
                **{k: r[k] for k in ("present", "absent", "late", "excused", "attended", "counted_days", "percentage")},
            }
            for r in services.attendance_counts_by(qs, "school_class_id", "school_class__name")
        ]
        by_class.sort(key=lambda r: r["class_name"] or "")

        return Response({
            "period": period,
            "school_days": school_days,
            "holidays": holidays,
            "totals": totals,
            "students": students,
            "by_class": by_class,
        })
