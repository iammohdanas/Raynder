
import json

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from api_gateway.models import Tender

from .models import ChatConversation, ChatMessage
import logging
from ai.services.documents.answer_generation_service import (
    AnswerGenerationService,
)

logger = logging.getLogger(__name__)

def _conversation_to_dict(conversation, include_messages=False):
    data = {
        "id": str(conversation.id),
        "title": conversation.title,
        "scope": conversation.scope,
        "tender_id": (
            conversation.tender.tender_id
            if conversation.tender_id
            else None
        ),
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }

    if include_messages:
        data["messages"] = [
            {
                "id": str(message.id),
                "role": message.role,
                "content": message.content,
                "citations": message.citations,
                "metadata": message.metadata,
                "created_at": message.created_at.isoformat(),
            }
            for message in conversation.messages.all()
        ]

    return data


def _get_json_body(request):
    try:
        body = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    return body if isinstance(body, dict) else None


@require_http_methods(["GET", "POST"])
def conversations(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=401)

    if request.method == "GET":
        queryset = ChatConversation.objects.filter(
            user=request.user
        ).select_related("tender")

        return JsonResponse({
            "conversations": [
                _conversation_to_dict(item)
                for item in queryset
            ]
        })

    
    body = _get_json_body(request)
    if body is None:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    title = str(body.get("title", "New chat")).strip() or "New chat"
    scope = body.get("scope", ChatConversation.Scope.ALL_TENDERS)
    tender_id = str(body.get("tender_id", "")).strip()

    if scope not in ChatConversation.Scope.values:
        return JsonResponse({"error": "Invalid conversation scope."}, status=400)

    tender = None

    if scope == ChatConversation.Scope.TENDER:
        if not tender_id:
            return JsonResponse(
                {"error": "tender_id is required for tender-specific chat."},
                status=400,
            )

        try:
            tender = Tender.objects.get(tender_id=tender_id)
        except Tender.DoesNotExist:
            return JsonResponse(
                {"error": f"Tender '{tender_id}' was not found."},
                status=404,
            )

    conversation = ChatConversation.objects.create(
        user=request.user,
        title=title[:200],
        scope=scope,
        tender=tender,
    )

    return JsonResponse(
        {"conversation": _conversation_to_dict(conversation)},
        status=201,
    )



@require_http_methods(["GET", "DELETE"])
def conversation_detail(request, conversation_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=401)

    conversation = get_object_or_404(
        ChatConversation.objects.select_related("tender"),
        id=conversation_id,
        user=request.user,
    )

    if request.method == "DELETE":
        conversation.delete()
        return JsonResponse({"deleted": True})

    return JsonResponse({
        "conversation": _conversation_to_dict(
            conversation,
            include_messages=True,
        )
    })


@require_http_methods(["POST"])
def send_message(request, conversation_id):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Authentication required."},
            status=401,
        )

    body = _get_json_body(request)
    if body is None:
        return JsonResponse(
            {"error": "Invalid JSON body."},
            status=400,
        )

    content = body.get("content")

    if not isinstance(content, str) or not content.strip():
        return JsonResponse(
            {"error": "Message content is required."},
            status=400,
        )

    content = content.strip()

    if len(content) > 20000:
        return JsonResponse(
            {"error": "Message is too long (maximum 20,000 characters)."},
            status=400,
        )

    # Fetch only a conversation owned by the current user.
    conversation = get_object_or_404(
        ChatConversation.objects.select_related("tender"),
        id=conversation_id,
        user=request.user,
    )

    # The existing retrieval service requires a specific tender.
    if conversation.tender is None:
        return JsonResponse(
            {
                "error": (
                    "This conversation is not linked to a specific tender. "
                    "Tender-specific RAG is available, but all-tenders chat "
                    "is not implemented yet."
                )
            },
            status=400,
        )

    # Use the internal string ID, e.g. '220926-8218',
    # not the database's integer primary key.
    tender_id = conversation.tender.tender_id

    # Save the user's message first so it survives AI/API failures.
    with transaction.atomic():
        user_message = ChatMessage.objects.create(
            conversation=conversation,
            role=ChatMessage.Role.USER,
            content=content,
        )

        if conversation.title == "New chat":
            conversation.title = (
                content[:197] + "..."
                if len(content) > 200
                else content
            )[:200]

        conversation.updated_at = timezone.now()
        conversation.save(update_fields=["title", "updated_at"])

    # Generate a grounded answer using the existing RAG pipeline.
    try:
        answer_service = AnswerGenerationService()
        result = answer_service.answer(
            tender_id=tender_id,
            question=content,
            limit=5,
        )

        assistant_content = result["answer"]
        citations = result.get("citations", [])
        insufficient_evidence = result.get(
            "insufficient_evidence",
            False,
        )

        # Persist the assistant's response and its citations.
        with transaction.atomic():
            assistant_message = ChatMessage.objects.create(
                conversation=conversation,
                role=ChatMessage.Role.ASSISTANT,
                content=assistant_content,
                citations=citations,
                metadata={
                    "insufficient_evidence": insufficient_evidence,
                    "tender_id": tender_id,
                },
            )

            conversation.updated_at = timezone.now()
            conversation.save(update_fields=["updated_at"])

        return JsonResponse(
            {
                "message": {
                    "id": str(user_message.id),
                    "role": user_message.role,
                    "content": user_message.content,
                    "citations": user_message.citations,
                    "created_at": user_message.created_at.isoformat(),
                },
                "reply": {
                    "id": str(assistant_message.id),
                    "role": assistant_message.role,
                    "content": assistant_message.content,
                    "citations": assistant_message.citations,
                    "metadata": assistant_message.metadata,
                    "created_at": assistant_message.created_at.isoformat(),
                },
                "status": "answered",
            },
            status=201,
        )

    except Exception:
        logger.exception(
            "RAG answer generation failed for conversation %s",
            conversation_id,
        )

        return JsonResponse(
            {
                "error": (
                    "Your message was saved, but the AI could not generate "
                    "an answer right now. Please try again."
                ),
                "status": "answer_generation_failed",
                "message": {
                    "id": str(user_message.id),
                    "role": user_message.role,
                    "content": user_message.content,
                    "citations": user_message.citations,
                    "created_at": user_message.created_at.isoformat(),
                },
            },
            status=502,
        )
