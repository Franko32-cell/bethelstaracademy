from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.classes.models import SchoolClass
from apps.subjects.models import Subject
from apps.teachers.models import Teacher


class TeacherContactApiTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="teacher-admin",
            password="test-password",
            role="admin",
            is_active=True,
            is_approved=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.school_class = SchoolClass.objects.create(name="Basic 7")
        self.subject = Subject.objects.create(
            name="Mathematics",
            school_class=self.school_class,
        )

    def test_teacher_contact_and_assignment_fields_are_available_and_editable(self):
        response = self.client.post(
            "/api/teachers/",
            {
                "first_name": "Naomi",
                "last_name": "Obeng",
                "email": "naomi@example.com",
                "phone": "0241234567",
                "subject": self.subject.id,
                "school_class": self.school_class.id,
                "hire_date": "2026-01-15",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["email"], "naomi@example.com")
        self.assertEqual(response.data["phone"], "0241234567")
        self.assertEqual(response.data["subject_name"], "Mathematics")
        self.assertEqual(response.data["school_class_name"], "Basic 7")

        teacher = Teacher.objects.get(pk=response.data["id"])
        update_response = self.client.patch(
            f"/api/teachers/{teacher.id}/",
            {
                "first_name": "Nana",
                "email": "nana@example.com",
                "phone": "0207654321",
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, 200, update_response.data)
        self.assertEqual(update_response.data["teacher_name"], "Nana Obeng")
        self.assertEqual(update_response.data["email"], "nana@example.com")
        self.assertEqual(update_response.data["phone"], "0207654321")

        search_response = self.client.get("/api/teachers/", {"search": "0207654321"})
        self.assertEqual(search_response.status_code, 200)
        results = (
            search_response.data["results"]
            if isinstance(search_response.data, dict)
            else search_response.data
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], teacher.id)
