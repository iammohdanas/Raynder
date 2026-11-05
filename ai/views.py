
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
from ai.services.evaluation.ragas_evaluation_service import (RagasEvaluationService)
import json
from ai.services.chat.answer_memory_service import AnswerMemoryService
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from api_gateway.models import Tender
from ai.models import EvaluationRun
from ai.tasks import run_document_pipeline, run_rag_evaluation,evaluate_live_rag_answer

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

    conversation = get_object_or_404(
        ChatConversation.objects.select_related("tender"),
        id=conversation_id,
        user=request.user,
    )

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

    tender_id = conversation.tender.tender_id

    previous_messages = list(
        ChatMessage.objects.filter(
            conversation=conversation,
        ).order_by("-created_at")[:10]
    )
    previous_messages.reverse()

    conversation_history = [
        {"role": message.role, "content": message.content}
        for message in previous_messages
        if message.role in (
            ChatMessage.Role.USER,
            ChatMessage.Role.ASSISTANT,
        )
    ]

    # Save the user's message before calling the AI.
    with transaction.atomic():
        user_message = ChatMessage.objects.create(
            conversation=conversation,
            role=ChatMessage.Role.USER,
            content=content,
        )

        if conversation.title == "New chat":
            conversation.title = (
                content[:197] + "..." if len(content) > 200 else content
            )[:200]

        conversation.updated_at = timezone.now()
        conversation.save(update_fields=["title", "updated_at"])

    try:
        result = AnswerGenerationService().answer(
            tender_id=tender_id,
            question=content,
            limit=5,
            conversation_history=conversation_history,
        )

        assistant_content = result["answer"]
        citations = result.get("citations", [])
        insufficient_evidence = result.get("insufficient_evidence", False)

        # Save the answer before scheduling background evaluation.
        with transaction.atomic():
            assistant_message = ChatMessage.objects.create(
                conversation=conversation,
                role=ChatMessage.Role.ASSISTANT,
                content=assistant_content,
                citations=citations,
                metadata={
                    "insufficient_evidence": insufficient_evidence,
                    "tender_id": tender_id,
                    "ragas_evaluation": {"status": "queued"},
                },
            )

            conversation.updated_at = timezone.now()
            conversation.save(update_fields=["updated_at"])

            # The callback runs after the outermost transaction commits.
            def enqueue_ragas():
                try:
                    evaluate_live_rag_answer.delay(
                        assistant_message_id=str(assistant_message.id),
                        question=content,
                        answer=assistant_content,
                        retrieved_contexts=result.get(
                            "retrieved_contexts", []
                        ),
                    )
                except Exception as exc:
                    logger.exception(
                        "Could not queue Ragas evaluation for message %s",
                        assistant_message.id,
                    )

                    # Update only the Ragas field while preserving other
                    # metadata keys. This uses a fresh database value.
                    try:
                        with transaction.atomic():
                            message = ChatMessage.objects.select_for_update().get(
                                id=assistant_message.id
                            )
                            metadata = message.metadata or {}
                            metadata["ragas_evaluation"] = {
                                "status": "failed",
                                "error": type(exc).__name__,
                            }
                            message.metadata = metadata
                            message.save(update_fields=["metadata"])
                    except Exception:
                        logger.exception(
                            "Could not save Ragas enqueue failure for %s",
                            assistant_message.id,
                        )

            transaction.on_commit(enqueue_ragas)

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


@require_http_methods(["POST"])
def start_rag_evaluation(request):
    """Create an evaluation run and enqueue its Celery task."""

    try:
        body = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "Invalid JSON request body."},
            status=400,
        )

    tender_id = body.get("tender_id")

    if not tender_id:
        return JsonResponse(
            {"error": "tender_id is required."},
            status=400,
        )

    tender = Tender.objects.filter(tender_id=tender_id).first()

    if tender is None:
        return JsonResponse(
            {"error": "Tender not found."},
            status=404,
        )

    # Create the evaluation run even if validated test cases do not exist.
    # The Celery task will generate and validate test cases when needed.
    run = EvaluationRun.objects.create(tender=tender)

    try:
        task = run_rag_evaluation.delay(str(run.id))

        run.celery_task_id = task.id or ""
        run.save(update_fields=["celery_task_id"])

    except Exception as exc:
        run.status = EvaluationRun.Status.FAILED
        run.error_message = str(exc)
        run.finished_at = __import__(
            "django.utils.timezone", fromlist=["now"]
        ).now()
        run.save(
            update_fields=[
                "status",
                "error_message",
                "finished_at",
            ]
        )

        return JsonResponse(
            {"error": "Could not enqueue evaluation task."},
            status=503,
        )

    return JsonResponse(
        {
            "run_id": str(run.id),
            "status": run.status,
            "message": "Evaluation queued successfully.",
        },
        status=202,
    )


@require_http_methods(["GET"])
def rag_evaluation_status(request, run_id):
    """Return the current evaluation status and progress."""

    run = EvaluationRun.objects.filter(id=run_id).first()

    if run is None:
        return JsonResponse(
            {"error": "Evaluation run not found."},
            status=404,
        )

    return JsonResponse({
        "run_id": str(run.id),
        "tender_id": run.tender.tender_id,
        "status": run.status,
        "total_cases": run.total_cases,
        "completed_cases": run.completed_cases,
        "passed_cases": run.passed_cases,
        "failed_cases": run.failed_cases,
        "pass_rate": run.pass_rate,
        "error": run.error_message,
        "created_at": run.created_at.isoformat(),
        "started_at": (
            run.started_at.isoformat() if run.started_at else None
        ),
        "finished_at": (
            run.finished_at.isoformat() if run.finished_at else None
        ),
    })


@require_http_methods(["GET"])
def rag_evaluation_results(request, run_id):
    """Return individual results for an evaluation run."""

    run = EvaluationRun.objects.filter(id=run_id).first()

    if run is None:
        return JsonResponse(
            {"error": "Evaluation run not found."},
            status=404,
        )

    results = run.results.all()

    return JsonResponse({
        "run_id": str(run.id),
        "status": run.status,
        "results": [
            {
                "id": str(result.id),
                "question": result.question,
                "expected_answer": result.expected_answer,
                "actual_answer": result.actual_answer,
                "answer_pass": result.answer_pass,
                "missing_terms": result.missing_terms,
                "citation_pass": result.citation_pass,
                "citations": result.citations,
                "insufficient_evidence": result.insufficient_evidence,
                "insufficient_evidence_pass": (
                    result.insufficient_evidence_pass
                ),
                "overall_pass": result.overall_pass,
                "error": result.error_message,
            }
            for result in results
        ],
    })


@require_http_methods(["POST"])
def start_document_pipeline(request, tender_id):
    """Queue document processing and vector indexing for a tender."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=401)

    tender = Tender.objects.filter(tender_id=tender_id).first()
    print(tender)
    print(tender_id)
    if tender is None:
        return JsonResponse({"error": "Tender not found."}, status=404)

    try:
        task = run_document_pipeline.delay(tender.tender_id)
    except Exception:
        logger.exception("Could not enqueue document pipeline for tender %s", tender_id)
        return JsonResponse({"error": "Could not queue document pipeline."}, status=503)

    return JsonResponse(
        {
            "success": True,
            "tender_id": tender.tender_id,
            "task_id": task.id,
            "status": "queued",
            "message": "Document pipeline queued successfully.",
        },
        status=202,
    )


from celery import current_app
from ai.tasks import run_document_pipeline


@require_http_methods(["GET"])
def document_pipeline_status(request, task_id):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Authentication required."},
            status=401
        )
    task = run_document_pipeline.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "status": task.state,
    }
    if task.successful():
        response["result"] = task.result
    elif task.failed():
        response["error"] = str(task.result)
    return JsonResponse(response)
