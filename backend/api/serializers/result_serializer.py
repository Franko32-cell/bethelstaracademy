from rest_framework import serializers

from apps.results.models import Result
from apps.results.scoring import result_level, result_scores
from api.views.grades import get_grade_and_remark, get_thresholds


class ResultSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    class_name   = serializers.SerializerMethodField()

    level      = serializers.SerializerMethodField()
    exam_only  = serializers.SerializerMethodField()
    sba_raw    = serializers.SerializerMethodField()
    sba        = serializers.SerializerMethodField()
    exam_score = serializers.SerializerMethodField()

    # Grade and remark are computed from the live total + the student's class level.
    grade  = serializers.SerializerMethodField()
    remark = serializers.SerializerMethodField()

    class Meta:
        model  = Result
        fields = [
            "id",
            "student",
            "student_name",
            "subject",
            "subject_name",
            "school_class",
            "class_name",
            "term",
            "year",
            "test1",
            "group_work",
            "test2",
            "exam",
            "level",
            "exam_only",
            "sba_raw",
            "sba",
            "exam_score",
            "score",
            "grade",
            "remark",
            "subject_position",
            "created_at",
        ]
        read_only_fields = [
            "score", "subject_position", "created_at", "grade", "remark",
            "level", "exam_only", "sba_raw", "sba", "exam_score",
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _thresholds(self, obj):
        return get_thresholds(result_level(obj))

    def _scores(self, obj):
        return result_scores(obj)

    # ------------------------------------------------------------------
    # Field methods
    # ------------------------------------------------------------------

    def get_student_name(self, obj):
        return obj.student.full_name if obj.student else "-"

    def get_subject_name(self, obj):
        return obj.subject.name if obj.subject else "-"

    def get_class_name(self, obj):
        return obj.school_class.name if obj.school_class else "-"

    def get_level(self, obj):
        return result_level(obj)

    def get_exam_only(self, obj):
        return self._scores(obj)["exam_only"]

    def get_sba_raw(self, obj):
        return self._scores(obj)["sba_raw"]

    def get_sba(self, obj):
        return self._scores(obj)["sba"]

    def get_exam_score(self, obj):
        return self._scores(obj)["exam_score"]

    def get_grade(self, obj):
        grade, _ = get_grade_and_remark(self._scores(obj)["total"], self._thresholds(obj))
        return grade

    def get_remark(self, obj):
        _, remark = get_grade_and_remark(self._scores(obj)["total"], self._thresholds(obj))
        return remark
