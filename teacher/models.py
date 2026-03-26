from django.db import models
from django.conf import settings
import random
import string

User = settings.AUTH_USER_MODEL


# -----------------------------
# CLASSROOM CODE GENERATOR
# -----------------------------
def generate_class_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


# -----------------------------
# CLASSROOM
# -----------------------------
class ClassRoom(models.Model):

    name = models.CharField(max_length=255)

    description = models.TextField(blank=True)

    readme_content = models.TextField(blank=True, null=True)

    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="teacher_classes"
    )

    students = models.ManyToManyField(
        User,
        related_name="enrolled_classes",
        blank=True
    )

    class_code = models.CharField(
        max_length=6,
        unique=True,
        default=generate_class_code
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.class_code})"


# -----------------------------
# ASSIGNMENT
# -----------------------------
class Assignment(models.Model):
    ASSIGNMENT_TYPE_FILE = "file"
    ASSIGNMENT_TYPE_QUIZ = "quiz"
    ASSIGNMENT_TYPE_CODE = "code"
    ASSIGNMENT_TYPE_CHOICES = (
        (ASSIGNMENT_TYPE_FILE, "File Upload"),
        (ASSIGNMENT_TYPE_QUIZ, "Assignment (MCQ)"),
        (ASSIGNMENT_TYPE_CODE, "Coding"),
    )
    ATTEMPT_POLICY_ONCE = "once"
    ATTEMPT_POLICY_MULTIPLE = "multiple"
    ATTEMPT_POLICY_CHOICES = (
        (ATTEMPT_POLICY_ONCE, "Once only"),
        (ATTEMPT_POLICY_MULTIPLE, "Multiple attempts"),
    )

    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.CASCADE,
        related_name="assignments"
    )

    title = models.CharField(max_length=255)

    description = models.TextField()

    due_date = models.DateTimeField()

    max_score = models.FloatField(default=100)

    assignment_type = models.CharField(
        max_length=10,
        choices=ASSIGNMENT_TYPE_CHOICES,
        default=ASSIGNMENT_TYPE_FILE
    )
    attempt_policy = models.CharField(
        max_length=10,
        choices=ATTEMPT_POLICY_CHOICES,
        default=ATTEMPT_POLICY_ONCE,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.classroom.name}"

    @property
    def allows_multiple_attempts(self):
        return self.attempt_policy == self.ATTEMPT_POLICY_MULTIPLE


# -----------------------------
# SUBMISSION
# -----------------------------
class Submission(models.Model):

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="submissions"
    )

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    file = models.FileField(upload_to="assignments/")

    submitted_at = models.DateTimeField(auto_now_add=True)

    # AI evaluation results
    score = models.FloatField(null=True, blank=True)

    ai_feedback = models.TextField(blank=True)

    class Meta:
        unique_together = ('assignment', 'student')

    def __str__(self):
        return f"{self.student} - {self.assignment.title}"


class QuizQuestion(models.Model):
    OPTION_A = "A"
    OPTION_B = "B"
    OPTION_C = "C"
    OPTION_D = "D"
    OPTION_CHOICES = (
        (OPTION_A, "Option A"),
        (OPTION_B, "Option B"),
        (OPTION_C, "Option C"),
        (OPTION_D, "Option D"),
    )

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="quiz_questions"
    )
    question = models.TextField()
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)
    correct_answer = models.CharField(
        max_length=1,
        choices=OPTION_CHOICES
    )

    def __str__(self):
        return f"Q: {self.question[:40]}"


class QuizAnswer(models.Model):
    question = models.ForeignKey(
        QuizQuestion,
        on_delete=models.CASCADE,
        related_name="answers"
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="quiz_answers"
    )
    selected_option = models.CharField(
        max_length=1,
        choices=QuizQuestion.OPTION_CHOICES
    )
    answered_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("question", "student")

    def __str__(self):
        return f"{self.student} - {self.question_id}"


class CodeSubmission(models.Model):
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="code_submissions"
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="code_submissions"
    )
    code = models.TextField()
    language = models.CharField(max_length=30, default="python")
    submitted_at = models.DateTimeField(auto_now=True)
    score = models.FloatField(null=True, blank=True)
    ai_feedback = models.TextField(blank=True)

    class Meta:
        unique_together = ("assignment", "student")

    def __str__(self):
        return f"{self.student} - {self.assignment.title}"

    @property
    def feedback(self):
        return self.ai_feedback

    @feedback.setter
    def feedback(self, value):
        self.ai_feedback = value


class QuizResult(models.Model):
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="quiz_results"
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="quiz_results"
    )
    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    score = models.FloatField(default=0)
    feedback = models.TextField(blank=True)
    evaluated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("assignment", "student")

    def __str__(self):
        return f"{self.student} - {self.assignment.title} ({self.score})"


class PerformanceRecord(models.Model):
    EVALUATION_TYPE_MANUAL = "manual"
    EVALUATION_TYPE_AI = "ai"
    EVALUATION_TYPE_AUTO = "auto"
    EVALUATION_TYPE_CHOICES = (
        (EVALUATION_TYPE_MANUAL, "Manual"),
        (EVALUATION_TYPE_AI, "AI"),
        (EVALUATION_TYPE_AUTO, "Auto"),
    )

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="performance_records",
    )
    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performance_records",
    )
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performance_records",
    )
    original_assignment_id = models.PositiveBigIntegerField(db_index=True)
    assignment_title = models.CharField(max_length=255)
    assignment_type = models.CharField(
        max_length=10,
        choices=Assignment.ASSIGNMENT_TYPE_CHOICES,
        default=Assignment.ASSIGNMENT_TYPE_FILE,
    )
    score = models.FloatField(null=True, blank=True)
    max_score = models.FloatField(default=100)
    submitted_at = models.DateTimeField(null=True, blank=True)
    due_date_snapshot = models.DateTimeField(null=True, blank=True)
    was_on_time = models.BooleanField(default=True)
    evaluation_type = models.CharField(
        max_length=10,
        choices=EVALUATION_TYPE_CHOICES,
        default=EVALUATION_TYPE_MANUAL,
    )
    feedback = models.TextField(blank=True)
    is_deleted_assignment = models.BooleanField(default=False)
    recorded_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("student", "original_assignment_id")
        indexes = [
            models.Index(fields=["classroom", "student"]),
            models.Index(fields=["student", "submitted_at"]),
            models.Index(fields=["classroom", "assignment_type"]),
        ]

    def __str__(self):
        return f"{self.student} - {self.assignment_title} ({self.score})"


# -----------------------------
# CHAT MESSAGE
# -----------------------------
class ChatMessage(models.Model):

    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.CASCADE,
        related_name="messages"
    )

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    message = models.TextField()

    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender}: {self.message[:30]}"


# -----------------------------
# TEACHER PROFILE
# -----------------------------
class TeacherProfile(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="teacher_profile"
    )

    profile_picture = models.ImageField(
        upload_to="teacher_profiles/",
        blank=True,
        null=True
    )

    full_name = models.CharField(max_length=120, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    department = models.CharField(max_length=120, blank=True)
    qualification = models.CharField(max_length=120, blank=True)
    years_experience = models.PositiveIntegerField(blank=True, null=True)
    bio = models.TextField(blank=True)
    address = models.TextField(blank=True)
    website = models.URLField(blank=True)
    linkedin = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile - {self.user.username}"
