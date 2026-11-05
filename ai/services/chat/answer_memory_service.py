
import re
from django.db.models import Q
from ai.models import ChatMessage


class AnswerMemoryService:

    @staticmethod
    def normalize_question(question):
        question = question.lower().strip()
        question = re.sub(r"[^\w\s]", " ", question)
        return " ".join(question.split())

    @classmethod
    def find_answer(cls, tender_id, question):
        normalized_question = cls.normalize_question(question)

        messages = (
            ChatMessage.objects.filter(
                role=ChatMessage.Role.ASSISTANT,
                conversation__scope="tender",
                conversation__tender__tender_id=str(tender_id),
                metadata__verification_status="verified",
                metadata__normalized_question=normalized_question,
                metadata__insufficient_evidence=False,
            )
            .exclude(citations=[])
            .order_by("-created_at")[:200]
        )

        for message in messages:
            return {
                "answer": message.content,
                "citations": message.citations,
                "source_message_id": str(message.id),
            }

        return None
