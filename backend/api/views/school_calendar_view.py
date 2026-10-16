# api/views/school_calendar_view.py
from datetime import date as date_cls, timedelta

from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, DateFilter, NumberFilter, CharFilter

from apps.attendance import services
from apps.attendance.models import SchoolCalendar
from apps.audit.services import log_action
from api.serializers.school_calendar_serializer import SchoolCalendarSerializer


class IsAdminOrReadOnly(permissions.BasePermission):
    """Any signed-in user can read the calendar; only admins change it."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return getattr(user, "role", None) == "admin"


class SchoolCalendarFilter(FilterSet):
    year       = NumberFilter(field_name="year")
    term       = CharFilter(field_name="term")
    event_type = CharFilter(field_name="event_type")
    # entries overlapping [date_after, date_before]
    date_after  = DateFilter(field_name="end_date", lookup_expr="gte")
    date_before = DateFilter(field_name="start_date", lookup_expr="lte")

    class Meta:
        model = SchoolCalendar
        fields = ["year", "term", "event_type", "is_school_day"]


def _d(value, name):
    try:
        return date_cls.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError({name: "Enter a valid date (YYYY-MM-DD)."})


def _snap(e):
    return {
        "name": e.name, "event_type": e.event_type,
        "start_date": str(e.start_date), "end_date": str(e.end_date),
        "is_school_day": e.is_school_day, "year": e.year, "term": e.term,
    }


class SchoolCalendarViewSet(viewsets.ModelViewSet):
    """
    /api/school-calendar/         list (filter: year, term, event_type, date_after, date_before)
    /api/school-calendar/check/?date=YYYY-MM-DD
    /api/school-calendar/days/?start=YYYY-MM-DD&end=YYYY-MM-DD   (max 366 days)
    """
    queryset = SchoolCalendar.objects.select_related("created_by", "updated_by")
    serializer_class = SchoolCalendarSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_class = SchoolCalendarFilter
    pagination_class = None

    def _log(self, action_name, obj, before=None, after=None, desc=""):
        log_action(
            self.request, action=action_name, module="attendance",
            resource_type="SchoolCalendar", resource_id=obj.pk, resource_repr=str(obj),
            previous_value=before, new_value=after, description=desc,
        )

    def perform_create(self, serializer):
        obj = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        self._log("create", obj, after=_snap(obj), desc=f"Added calendar entry: {obj}")

    def perform_update(self, serializer):
        before = _snap(serializer.instance)
        obj = serializer.save(updated_by=self.request.user)
        self._log("update", obj, before=before, after=_snap(obj), desc=f"Updated calendar entry: {obj}")

    def perform_destroy(self, instance):
        before, label, pk = _snap(instance), str(instance), instance.pk
        instance.delete()
        log_action(
            self.request, action="delete", module="attendance",
            resource_type="SchoolCalendar", resource_id=pk, resource_repr=label,
            previous_value=before, description=f"Deleted calendar entry: {label}",
        )

    @action(detail=False, methods=["get"], url_path="check")
    def check(self, request):
        d = _d(request.query_params.get("date"), "date")
        return Response(services.day_status(d))

    @action(detail=False, methods=["get"], url_path="days")
    def days(self, request):
        start = _d(request.query_params.get("start"), "start")
        end = _d(request.query_params.get("end"), "end")
        if end < start:
            raise ValidationError({"end": "End date cannot be before the start date."})
        if end - start > timedelta(days=366):
            raise ValidationError({"end": "Range cannot exceed 366 days."})
        return Response({
            "start": start.isoformat(), "end": end.isoformat(),
            "school_days": services.count_school_days(start, end),
            "non_school_days": services.non_school_days(start, end),
        })
