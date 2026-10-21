
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
