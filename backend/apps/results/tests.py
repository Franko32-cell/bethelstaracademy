from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.classes.models import SchoolClass
from apps.students.models import Student
from apps.subjects.models import Subject
from apps.results.models import Result
from apps.attendance.models import Attendance
from apps.results.whatsapp import normalize_gh_phone, send_whatsapp_report
from unittest.mock import patch
from io import BytesIO


class ResultsApiTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tester", password="pass")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.school_class = SchoolClass.objects.create(name="JSS 1", level="basic_7_9")
        self.subject = Subject.objects.create(name="Mathematics", school_class=self.school_class)
        self.student = Student.objects.create(
            user=self.user,
            admission_number="AD001",
            first_name="Jane",
            last_name="Doe",
            school_class=self.school_class,
        )

    def test_normalize_gh_phone(self):
        self.assertEqual(normalize_gh_phone("0241234567"), "233241234567")
        self.assertEqual(normalize_gh_phone("+233241234567"), "233241234567")
        self.assertEqual(normalize_gh_phone("233241234567"), "233241234567")
        self.assertIsNone(normalize_gh_phone("024123"))

    def test_send_whatsapp_report_skips_missing_or_invalid_phone(self):
        self.assertEqual(send_whatsapp_report(self.student, BytesIO(b"pdf"), "Report")["reason"], "no_phone")
        self.student.parent_phone = "not-a-phone"
        self.student.save(update_fields=["parent_phone"])
        self.assertEqual(send_whatsapp_report(self.student, BytesIO(b"pdf"), "Report")["reason"], "invalid_phone")

    @patch("apps.results.whatsapp._upload_pdf", return_value="https://res.cloudinary.com/test/report.pdf")
    @patch("apps.results.whatsapp.requests.post")
    def test_send_whatsapp_report_success_and_termii_error(self, post, _upload):
        self.student.parent_phone = "0241234567"
        self.student.save(update_fields=["parent_phone"])
        response = post.return_value
        response.status_code = 200
        response.text = "{}"
        response.json.return_value = {"message_id": "msg-1"}
        self.assertEqual(send_whatsapp_report(self.student, BytesIO(b"pdf"), "Report")["message_id"], "msg-1")
        response.status_code = 500
        self.assertEqual(send_whatsapp_report(self.student, BytesIO(b"pdf"), "Report")["reason"], "termii_error")

    def test_bulk_save_preserves_school_class_and_year(self):
        result = Result.objects.create(
            student=self.student,
            subject=self.subject,
            school_class=self.school_class,
            term="term3",
            year=settings.CURRENT_YEAR,
            test1=5,
            group_work=10,
            test2=15,
            exam=40,
        )

        payload = [{
            "student": self.student.id,
            "subject": self.subject.id,
            "term": "term3",
            "test1": 7,
        }]

        response = self.client.post("/api/results/bulk/", payload, format="json")
        self.assertEqual(response.status_code, 200)

        result.refresh_from_db()
        self.assertEqual(result.school_class_id, self.school_class.id)
        self.assertEqual(result.test1, 7.0)
        self.assertEqual(result.group_work, 10.0)
        self.assertEqual(result.test2, 15.0)
        self.assertEqual(result.exam, 40.0)
        self.assertEqual(result.year, settings.CURRENT_YEAR)

    def test_report_endpoint_filters_by_year(self):
        Result.objects.create(
            student=self.student,
            subject=self.subject,
            school_class=self.school_class,
            term="term3",
            year=settings.CURRENT_YEAR - 1,
            test1=1,
            group_work=1,
            test2=1,
            exam=10,
        )
        Result.objects.create(
            student=self.student,
            subject=self.subject,
            school_class=self.school_class,
            term="term3",
            year=settings.CURRENT_YEAR,
            test1=7,
            group_work=8,
            test2=9,
            exam=20,
        )
        Attendance.objects.create(
            student=self.student,
            school_class=self.school_class,
            term="term3",
            year=settings.CURRENT_YEAR,
            date="2026-05-20",
            status="present",
        )

        response = self.client.get(
            f"/api/report/student/{self.student.id}/",
            {"term": "term3", "year": settings.CURRENT_YEAR},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["year"], settings.CURRENT_YEAR)
        self.assertEqual(response.data["attendance_total"], 1)
        self.assertEqual(response.data["attendance"], 1)
        self.assertEqual(response.data["total_score"], 30.0)

    def test_report_attitude_and_head_teacher_remark_round_trip(self):
        url = f"/api/report/student/{self.student.id}/"
        report_fields = {
            "term": "term3",
            "year": settings.CURRENT_YEAR,
            "attitude": "Respectful <and attentive>",
            "head_teacher_remark": "A successful & productive term.",
        }

        save_response = self.client.patch(url, report_fields, format="json")
        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(save_response.data["attitude"], "Respectful <and attentive>")
        self.assertEqual(save_response.data["head_teacher_remark"], "A successful & productive term.")

        read_response = self.client.get(
            url, {"term": "term3", "year": settings.CURRENT_YEAR},
        )
        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.data["attitude"], "Respectful <and attentive>")
        self.assertEqual(read_response.data["head_teacher_remark"], "A successful & productive term.")

        pdf_response = self.client.get(
            f"{url}pdf/", {"term": "term3", "year": settings.CURRENT_YEAR},
        )
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")

    def test_exam_only_report_pdf_generates(self):
        nursery_class = SchoolClass.objects.create(name="Nursery 1", level="nursery_kg")
        nursery_student = Student.objects.create(
            user=get_user_model().objects.create_user(username="nursery-pupil"),
            admission_number="NUR001",
            first_name="Sam",
            last_name="Learner",
            school_class=nursery_class,
        )
        Result.objects.create(
            student=nursery_student,
            subject=self.subject,
            school_class=nursery_class,
            term="term3",
            year=settings.CURRENT_YEAR,
            exam=72,
        )

        response = self.client.get(
            f"/api/report/student/{nursery_student.id}/pdf/",
            {"term": "term3", "year": settings.CURRENT_YEAR},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_report_endpoint_returns_position_and_summary(self):
        student2 = Student.objects.create(
            user=get_user_model().objects.create_user(username="tester2", password="pass"),
            admission_number="AD002",
            first_name="John",
            last_name="Smith",
            school_class=self.school_class,
        )
        Result.objects.create(
            student=self.student,
            subject=self.subject,
            school_class=self.school_class,
            term="term3",
            year=settings.CURRENT_YEAR,
            test1=10,
            group_work=10,
            test2=10,
            exam=10,
        )
        Result.objects.create(
            student=student2,
            subject=self.subject,
            school_class=self.school_class,
            term="term3",
            year=settings.CURRENT_YEAR,
            test1=10,
            group_work=10,
            test2=10,
            exam=10,
        )

        response = self.client.get(
            f"/api/report/student/{self.student.id}/",
            {"term": "term3", "year": settings.CURRENT_YEAR},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["show_position"])
        self.assertIsNone(response.data["position"])
        self.assertEqual(response.data["position_formatted"], "N/A")
        self.assertEqual(response.data["subjects"][0]["subject_position"], "1st")
        self.assertEqual(response.data["out_of"], 2)
        self.assertEqual(response.data["average_score"], 30)
        self.assertEqual(response.data["overall_grade"], "9")
