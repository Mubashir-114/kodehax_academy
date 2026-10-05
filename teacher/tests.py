from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from teacher.models import Assignment, ClassRoom
from users.models import User


@override_settings(ROOT_URLCONF="kodehax_academy.urls")
class DeleteClassroomTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="classroom-teacher",
            password="test-password",
            role="teacher",
        )
        self.other_teacher = User.objects.create_user(
            username="other-classroom-teacher",
            password="test-password",
            role="teacher",
        )
        self.classroom = ClassRoom.objects.create(
            name="Delete me",
            teacher=self.teacher,
        )
        self.assignment = Assignment.objects.create(
            classroom=self.classroom,
            title="Related assignment",
            description="This should be removed with the classroom.",
            due_date=timezone.now() + timezone.timedelta(days=1),
        )
        self.delete_url = reverse(
            "delete_classroom",
            kwargs={"class_id": self.classroom.id},
        )

    def test_teacher_can_delete_owned_classroom_and_cascaded_assignments(self):
        self.client.force_login(self.teacher)

        response = self.client.post(self.delete_url)

        self.assertRedirects(response, reverse("teacher_dashboard"))
        self.assertFalse(ClassRoom.objects.filter(id=self.classroom.id).exists())
        self.assertFalse(Assignment.objects.filter(id=self.assignment.id).exists())

    def test_teacher_dashboard_shows_classroom_delete_control(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("teacher_dashboard"))

        self.assertContains(response, "Delete Classroom")
        self.assertContains(response, self.delete_url)

    def test_delete_requires_post(self):
        self.client.force_login(self.teacher)

        response = self.client.get(self.delete_url)

        self.assertRedirects(
            response,
            reverse("class_detail", kwargs={"id": self.classroom.id}),
        )
        self.assertTrue(ClassRoom.objects.filter(id=self.classroom.id).exists())

    def test_teacher_cannot_delete_another_teachers_classroom(self):
        self.client.force_login(self.other_teacher)

        response = self.client.post(self.delete_url)

        self.assertRedirects(response, reverse("teacher_dashboard"))
        self.assertTrue(ClassRoom.objects.filter(id=self.classroom.id).exists())

    def test_non_teacher_cannot_delete_classroom(self):
        student = User.objects.create_user(
            username="classroom-student",
            password="test-password",
            role="student",
        )
        self.client.force_login(student)

        response = self.client.post(self.delete_url)

        self.assertRedirects(response, reverse("home"))
        self.assertTrue(ClassRoom.objects.filter(id=self.classroom.id).exists())
