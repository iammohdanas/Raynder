
import uuid

from django.conf import settings
from django.db import models


class ChatConversation(models.Model):
    class Scope(models.TextChoices):
        ALL_TENDERS = "all_tenders", "All Tenders"
        TENDER = "tender", "Specific Tender"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_chat_conversations",
    )

    title = models.CharField(
        max_length=200,
        default="New chat",
    )

    scope = models.CharField(
        max_length=20,
        choices=Scope.choices,
        default=Scope.ALL_TENDERS,
    )

    tender = models.ForeignKey(
        "api_gateway.Tender",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_chat_conversations",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.user_id})"


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
    )

    content = models.TextField()

    # Stores verified citations returned by the answer-generation service.
    citations = models.JSONField(default=list, blank=True)

    # Optional metadata for errors, model details, and future features.
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:60]}"



import uuid

from django.db import models


class EvaluationTestCase(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VALIDATED = "validated", "Validated"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    tender = models.ForeignKey(
        "api_gateway.Tender",
        on_delete=models.CASCADE,
        related_name="evaluation_test_cases",
    )

    question = models.TextField()
    expected_answer = models.TextField()

    # Example:
    # [{"document": "Volume-I.pdf", "pages": [47]}]
    expected_sources = models.JSONField(default=list)

    required_terms = models.JSONField(default=list)

    expected_insufficient_evidence = models.BooleanField(
        default=False
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    generation_model = models.CharField(
        max_length=100,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["tender", "status"],
                name="eval_tender_status_idx",
            ),
        ]

    def __str__(self):
        return f"{self.tender.tender_id}: {self.question[:80]}"



class EvaluationRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    tender = models.ForeignKey(
        "api_gateway.Tender",
        on_delete=models.CASCADE,
        related_name="evaluation_runs",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
    )

    total_cases = models.PositiveIntegerField(default=0)
    completed_cases = models.PositiveIntegerField(default=0)
    passed_cases = models.PositiveIntegerField(default=0)
    failed_cases = models.PositiveIntegerField(default=0)

    error_message = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["tender", "-created_at"],
                name="evalrun_tender_created_idx",
            ),
        ]

    @property
    def pass_rate(self):
        if not self.completed_cases:
            return 0.0
        return round(
            self.passed_cases / self.completed_cases * 100,
            2,
        )

    def __str__(self):
        return f"Evaluation {self.id} - {self.status}"


class EvaluationResult(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    run = models.ForeignKey(
        EvaluationRun,
        on_delete=models.CASCADE,
        related_name="results",
    )

    test_case = models.ForeignKey(
        EvaluationTestCase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluation_results",
    )

    question = models.TextField()
    expected_answer = models.TextField(blank=True)
    actual_answer = models.TextField(blank=True)

    answer_pass = models.BooleanField(default=False)
    missing_terms = models.JSONField(default=list)

    citation_pass = models.BooleanField(default=False)
    citations = models.JSONField(default=list)

    insufficient_evidence = models.BooleanField(default=False)
    insufficient_evidence_pass = models.BooleanField(default=False)

    overall_pass = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    ragas_scores = models.JSONField(default=dict, blank=True)
    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["run", "overall_pass"],
                name="evalresult_run_pass_idx",
            ),
        ]

    def __str__(self):
        return f"Result for evaluation {self.run_id}"



class TenderPQAnalysis(models.Model):

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class OverallStatus(models.TextChoices):
        QUALIFIED = "qualified", "Qualified"
        NOT_QUALIFIED = "not_qualified", "Not Qualified"
        NEEDS_REVIEW = "needs_review", "Needs Review"
        INSUFFICIENT_EVIDENCE = (
            "insufficient_evidence",
            "Insufficient Evidence",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    tender = models.ForeignKey(
        "api_gateway.Tender",
        on_delete=models.CASCADE,
        related_name="pq_analyses",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )

    overall_status = models.CharField(
        max_length=30,
        choices=OverallStatus.choices,
        blank=True,
    )

    # Complete extraction output from PQExtractionService
    extraction_result = models.JSONField(
        default=dict,
        blank=True,
    )

    # Complete comparison output from PQComparisonService
    comparison_result = models.JSONField(
        default=dict,
        blank=True,
    )

    total_criteria = models.PositiveIntegerField(default=0)
    requirements_met = models.PositiveIntegerField(default=0)
    critical_gaps = models.PositiveIntegerField(default=0)

    error_message = models.TextField(blank=True)

    celery_task_id = models.CharField(
        max_length=255,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["tender", "-created_at"],
                name="pq_tender_created_idx",
            ),
            models.Index(
                fields=["tender", "status"],
                name="pq_tender_status_idx",
            ),
        ]

    def __str__(self):
        return f"PQ Analysis {self.id} - {self.tender.tender_id}"
