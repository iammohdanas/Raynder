import json
from django.db.models.aggregates import Sum
from dotenv import load_dotenv
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models.aggregates import Sum
from ai.services.tender_discovery import TenderDiscoveryService
from ai.services.tender_research import KEYWORDS
from api_gateway.models import MyTender, Tender, TenderDecision, TenderDocument
from api_gateway.serializers import TenderDocumentSerializer, TenderSerializer
from api_gateway.services.all_tenders_sync import AllTenderSyncService
from api_gateway.utils.filter_keywords import get_search_keywords
from authenticator.decorators import role_required, role_required_api
from authenticator.services.tendertiger_auth_manager import TenderTigerAuthManager
from api_gateway.services.tendertiger_mapper import TenderTigerMapper
from crawlers.tendertiger.crawler.auth import TenderTigerAuth
from crawlers.tendertiger.crawler.search import TenderTigerSearch
from Raynder.settings import TENDERTIGER_EMAIL, TENDERTIGER_PASSWORD
from django.db.models import Q
from django.core.paginator import Paginator
from rest_framework import status
from django.shortcuts import get_object_or_404
from api_gateway.models import Tender
from api_gateway.models import Tender, TenderPriority
from api_gateway.services.tender_priority import TenderPriorityService
from django.db import transaction
from uuid import uuid4
from Raynder import settings
from rest_framework.response import Response
from rest_framework import status
from api_gateway.services.all_tenders_sync import AllTenderSyncService
from api_gateway.tasks import sync_all_sources
import uuid
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from api_gateway.models import Tender
from ai.models import ChatConversation, ChatMessage
import logging
logger = logging.getLogger(__name__)
load_dotenv()
import copy
from api_gateway.models import TenderExecution, ExecutionActivity
from api_gateway.services.execution_workflow.execution_service import (
    calculate_execution_progress,configure_task_approvers,submit_task_approval, add_task_attachment,
    delete_task_attachment, update_custom_task,create_execution_plan,
)
from django.core.exceptions import ValidationError
from django.http import Http404
from api_gateway.models import TenderExecution
from api_gateway.services.execution_workflow.execution_service import ( set_task_applicability, add_custom_task, set_task_assignees, update_task_status, add_task_comment, update_task_remarks, calculate_execution_progress,)
from django.contrib.auth import get_user_model
from authenticator.permissions import (is_system_admin,is_approved_employee, get_approved_employee_profiles, can_assign_to_employee,)
from authenticator.permissions import ( get_reporting_tree_profiles, is_system_admin, is_approved_employee, can_assign_to_employee,)


@api_view(["POST"])
def sync_tenders(request):
    try:
        if settings.CELERY_ENABLED:
            task=sync_all_sources()

            return Response({
                "success":True,
                "message":"Tender synchronization started.",
                "task_id":task.id,
                "mode":"celery",
            },status=status.HTTP_202_ACCEPTED)

        result=AllTenderSyncService().sync()

        return Response({
            "success":True,
            "message":"Tender synchronization completed.",
            "mode":"synchronous",
            "result":result,
        },status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            "success":False,
            "error":str(e),
        },status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
def get_tenders(request):
    """
    Server-side DataTables API.

    Supports:
    - Pagination
    - Search
    - Ordering
    """
    try:
        start = int(request.GET.get("start", 0))
        length = int(request.GET.get("length", 10))
        if length <= 0:
            length = 10
        if length > 100:
            length = 100

        search_value = request.GET.get("search[value]", "").strip()
        queryset = Tender.objects.all()
        records_total = queryset.count()
        # Only tenders which exist in TenderPriority
        recommended_tender_queryset = TenderPriority.objects.select_related("tender")
        recommended_tenders = recommended_tender_queryset.count()

        if search_value:
            search_filter = (
                Q(tender_id__icontains=search_value)
                | Q(source_tender_id__icontains=search_value)
                | Q(tender_ref_no__icontains=search_value)
                | Q(tcno__icontains=search_value)
                | Q(title__icontains=search_value)
                | Q(description__icontains=search_value)
                | Q(company_name__icontains=search_value)
                | Q(state__icontains=search_value)
                | Q(city__icontains=search_value)
                | Q(address__icontains=search_value)
            )
            # Search using Django model's primary key
            if search_value.isdigit():
                search_filter |= Q(pk=int(search_value))
            queryset = queryset.filter(search_filter)

        records_filtered = queryset.count()
        queryset = queryset.order_by("-created_at")
        paginator = Paginator(queryset, length)
        page_number = (start // length) + 1
        page = paginator.get_page(page_number)
        serializer = TenderSerializer(page.object_list, many=True)

        data = []
        for tender, serialized in zip(page.object_list, serializer.data):
            location_parts = [val for val in [tender.city, tender.state] if val]
            data.append({
                "id": tender.id,
                "tender_id": tender.tender_id,
                "title": tender.title,
                "tender_ref_no": tender.tender_ref_no,
                "due_date": tender.closing_date.strftime("%d-%m-%Y") if tender.closing_date else None,
                "authority": tender.company_name,
                "location": ", ".join(location_parts) or "Pan India",
                "capacity_mw": None,
                "is_paid": None,
                "fit_score": 0,
                "recommendation": None,
                "view_url": f"/tenders/{tender.id}/",
                "tender": serialized,
            })

        return Response(
            {
                "draw": int(request.GET.get("draw", 1)),
                "recordsTotal": records_total,
                "recordsFiltered": records_filtered,
                "data": data,
                "stats": {
                    "total_tenders": records_total,
                    "recommended_count": recommended_tenders,
                    "total_capacity_mw": 0,
                    "last_sync": None,
                },
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {
                "success": False,
                "error": str(e),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        
@api_view(["GET"])
def get_tender_detail(request, tender_id):
    try:
        tender = get_object_or_404(
            Tender.objects.prefetch_related("documents"),
            id=tender_id,
        )

        tender_serializer = TenderSerializer(tender)

        document_serializer = TenderDocumentSerializer(
            tender.documents.all(),
            many=True,
            context={"request": request},
        )

        data = tender_serializer.data

        # Add documents to tender response
        data["documents"] = document_serializer.data
        try:
            my_tender = tender.my_tender
            data["my_tender"] = {
                "status": my_tender.status,
                "status_display": my_tender.get_status_display(),
                "remarks": my_tender.remarks,
                "added_at": my_tender.added_at.isoformat(),
                "updated_at": my_tender.updated_at.isoformat(),
            }

        except MyTender.DoesNotExist:
            data["my_tender"] = None

        return Response(
            {
                "success": True,
                "data": data,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {
                "success": False,
                "error": str(e),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
 
 
@api_view(["GET"])
def get_priority_tenders(request):
    """
    Server-side DataTables API for high-priority tenders.

    Supports:
    - Pagination
    - Search
    - Ordering
    """
    try:
        start = int(request.GET.get("start", 0))
        length = max(1, min(int(request.GET.get("length", 10)), 100))
        search_value = request.GET.get("search[value]", "").strip()

        # Only tenders which exist in TenderPriority
        queryset = TenderPriority.objects.select_related("tender")
        records_total = queryset.count()

        # Search
        # Search
        if search_value:
            search_filter = (
                Q(tender__tender_id__icontains=search_value)
                | Q(tender__source_tender_id__icontains=search_value)
                | Q(tender__tender_ref_no__icontains=search_value)
                | Q(tender__tcno__icontains=search_value)
                | Q(tender__title__icontains=search_value)
                | Q(tender__description__icontains=search_value)
                | Q(tender__company_name__icontains=search_value)
                | Q(tender__state__icontains=search_value)
                | Q(tender__city__icontains=search_value)
                | Q(tender__address__icontains=search_value)
            )

            # Search by Tender model's actual primary key
            if search_value.isdigit():
                search_filter |= Q(tender__pk=int(search_value))

            queryset = queryset.filter(search_filter)

        records_filtered = queryset.count()
        queryset = queryset.order_by("-id")

        paginator = Paginator(queryset, length)
        page_number = (start // length) + 1
        page = paginator.get_page(page_number)

        data = []
        for priority in page.object_list:
            tender = priority.tender
            location_parts = [v for v in [tender.city, tender.state] if v]

            data.append({
                "id": tender.id,
                "priority_id": priority.id,
                "tender_id": tender.tender_id,
                "title": tender.title,
                "tender_ref_no": tender.tender_ref_no,
                "due_date": tender.closing_date.strftime("%d-%m-%Y") if tender.closing_date else None,
                "authority": tender.company_name,
                "location": ", ".join(location_parts) if location_parts else "Pan India",
                "capacity_mw": float(priority.capacity_mw) if priority.capacity_mw is not None else None,
                "amount_crore": float(priority.amount_crore) if priority.amount_crore is not None else None,
                "is_paid": None,
                "fit_score": 0,
                "recommendation": None,
                "view_url": f"/tenders/{tender.id}/",
            })
        # Statistics

        return Response(
            {
                "draw": int(request.GET.get("draw", 1)),
                "recordsTotal": records_total,
                "recordsFiltered": records_filtered,
                "data": data,
                "stats": {
                    "total_tenders": records_total,
                    "recommended_count": records_total,
                    "total_capacity_mw": 0,
                    "last_sync": None,
                },
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )       
        
#this api will be used to fetch the priority tenders as it filters out the tenders whose submission dates passed

# @api_view(["GET"])
# def get_priority_tenders(request):
#     """
#     Server-side DataTables API for high-priority tenders.

#     Supports:
#     - Pagination
#     - Search
#     - Ordering
#     - Excludes expired tenders
#     - Includes tenders without deadlines for up to 3 months
#     """
#     try:
#         start = max(0, int(request.GET.get("start", 0)))
#         length = max(1, min(int(request.GET.get("length", 10)), 100))
#         search_value = request.GET.get("search[value]", "").strip()

#         today = timezone.localdate()
#         three_months_ago = today - timedelta(days=90)

#         # Base queryset
#         queryset = TenderPriority.objects.select_related("tender")

#         # Deadline filtering:
#         # 1. Closing date is today or in the future.
#         # 2. If closing date is NULL, show only tenders
#         #    created within the last 3 months.
#         queryset = queryset.filter(
#             Q(tender__closing_date__gte=today)
#             |
#             Q(
#                 tender__closing_date__isnull=True,
#                 tender__created_at__date__gte=three_months_ago,
#             )
#         )

#         # Total records after deadline filtering
#         records_total = queryset.count()

#         # Search
#         if search_value:
#             queryset = queryset.filter(
#                 Q(tender__tender_id__icontains=search_value)
#                 | Q(tender__source_tender_id__icontains=search_value)
#                 | Q(tender__tender_ref_no__icontains=search_value)
#                 | Q(tender__tcno__icontains=search_value)
#                 | Q(tender__title__icontains=search_value)
#                 | Q(tender__description__icontains=search_value)
#                 | Q(tender__company_name__icontains=search_value)
#                 | Q(tender__state__icontains=search_value)
#                 | Q(tender__city__icontains=search_value)
#                 | Q(tender__address__icontains=search_value)
#             )

#         records_filtered = queryset.count()

#         # Ordering
#         queryset = queryset.order_by("-id")

#         # Pagination
#         paginator = Paginator(queryset, length)
#         page_number = (start // length) + 1
#         page = paginator.get_page(page_number)

#         data = []

#         for priority in page.object_list:
#             tender = priority.tender

#             location_parts = [
#                 v for v in [tender.city, tender.state] if v
#             ]

#             data.append({
#                 "id": tender.id,
#                 "priority_id": priority.id,
#                 "tender_id": tender.tender_id,
#                 "title": tender.title,
#                 "tender_ref_no": tender.tender_ref_no,
#                 "due_date": (
#                     tender.closing_date.strftime("%d-%m-%Y")
#                     if tender.closing_date else None
#                 ),
#                 "authority": tender.company_name,
#                 "location": (
#                     ", ".join(location_parts)
#                     if location_parts else "Pan India"
#                 ),
#                 "capacity_mw": (
#                     float(priority.capacity_mw)
#                     if priority.capacity_mw is not None else None
#                 ),
#                 "amount_crore": (
#                     float(priority.amount_crore)
#                     if priority.amount_crore is not None else None
#                 ),
#                 "is_paid": None,
#                 "fit_score": 0,
#                 "recommendation": None,
#                 "view_url": f"/tenders/{tender.id}/",
#             })

#         return Response(
#             {
#                 "draw": int(request.GET.get("draw", 1)),
#                 "recordsTotal": records_total,
#                 "recordsFiltered": records_filtered,
#                 "data": data,
#                 "stats": {
#                     "total_tenders": records_total,
#                     "recommended_count": records_total,
#                     "total_capacity_mw": 0,
#                     "last_sync": None,
#                 },
#             },
#             status=status.HTTP_200_OK,
#         )

#     except Exception as e:
#         return Response(
#             {"success": False, "error": str(e)},
#             status=status.HTTP_500_INTERNAL_SERVER_ERROR,
#         )


@api_view(["POST"])
def create_tender(request):
    """
    Create a tender manually with optional multiple documents.
    """
    try:
        with transaction.atomic():

            tender_data = request.data.copy()
            tender_data["source"] = "other"
            tender_data.pop("document_available", None)
            tender_data.pop("documents", None)
            tender_data["source_tender_id"] = f"manual-{uuid4().hex}"
            serializer = TenderSerializer(data=tender_data)
            if not serializer.is_valid():
                return Response(
                    {
                        "success": False,
                        "errors": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            tender = serializer.save()
            documents = [
                document
                for document in request.FILES.getlist("documents")
                if document and document.name
            ]

            created_documents = []

            for document in documents:
                tender_document = TenderDocument.objects.create(
                    tender=tender,
                    file=document,
                    original_filename=document.name,
                )

                created_documents.append(tender_document)

            tender.document_available = bool(created_documents)
            tender.save(update_fields=["document_available", "updated_at"])

            return Response(
                {
                    "success": True,
                    "message": "Tender created successfully.",
                    "data": TenderSerializer(tender).data,
                    "documents_count": len(created_documents),
                },
                status=status.HTTP_201_CREATED,
            )
    except Exception as e:
        return Response(
            {
                "success": False,
                "error": str(e),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@api_view(["POST"])
def upload_tender_documents(request, tender_id):
    try:
        tender = get_object_or_404(Tender, id=tender_id)

        documents = [
            document
            for document in request.FILES.getlist("documents")
            if document and document.name
        ]

        if not documents:
            return Response(
                {
                    "success": False,
                    "error": "No documents were uploaded.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            created_documents = []

            for document in documents:
                tender_document = TenderDocument.objects.create(
                    tender=tender,
                    file=document,
                    original_filename=document.name,
                )

                created_documents.append(tender_document)

            # document_available is derived from actual documents
            tender.document_available = TenderDocument.objects.filter(
                tender=tender
            ).exists()

            tender.save(
                update_fields=[
                    "document_available",
                    "updated_at",
                ]
            )

        document_serializer = TenderDocumentSerializer(
            created_documents,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "success": True,
                "message": f"{len(created_documents)} document(s) uploaded successfully.",
                "documents": document_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        return Response(
            {
                "success": False,
                "error": str(e),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@role_required_api(["admin", "manager"])
@api_view(["DELETE"])
def delete_tender_document(request, document_id):
    try:
        document = get_object_or_404(
            TenderDocument.objects.select_related("tender"),
            id=document_id,
        )
        tender = document.tender
        with transaction.atomic():
            document.delete()
            tender.document_available = TenderDocument.objects.filter(
                tender=tender
            ).exists()

            tender.save(
                update_fields=[
                    "document_available",
                    "updated_at",
                ]
            )
        return Response(
            {
                "success": True,
                "message": "Document deleted successfully.",
                "document_id": document_id,
                "document_available": tender.document_available,
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {
                "success": False,
                "error": str(e),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@api_view(["PATCH"])
@role_required(["admin", "manager"])
def update_tender(request, tender_id):
    try:
        tender = get_object_or_404(Tender, id=tender_id)
        editable_fields = {
            "tender_ref_no", "tcno", "title", "description", "company_name",
            "state", "city", "address", "tender_value", "earnest_money",
            "tender_date", "opening_date", "closing_date", "description_url",
            "original_source",
        }

        submitted_fields = set(request.data.keys())
        invalid_fields = submitted_fields - editable_fields

        if not submitted_fields:
            return Response(
                {"success": False, "error": "No fields were provided for update."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if invalid_fields:
            return Response(
                {
                    "success": False,
                    "error": "These fields cannot be edited.",
                    "fields": sorted(invalid_fields),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TenderSerializer(tender, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            tender = serializer.save()

        return Response(
            {
                "success": True,
                "message": "Tender updated successfully.",
                "data": TenderSerializer(tender).data,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )



def _conversation_payload(conversation):
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "scope": conversation.scope,
        "tender_id": conversation.tender_id,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }


def _message_payload(message):
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "citations": message.citations,
        "created_at": message.created_at.isoformat(),
    }


@api_view(["GET"])
def chat_history(request):
    if not request.user.is_authenticated:
        return Response(
            {"success": False, "error": "Authentication required."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    conversations = ChatConversation.objects.filter(
        user=request.user
    ).select_related("tender").order_by("-updated_at")

    return Response({
        "success": True,
        "conversations": [
            _conversation_payload(item)
            for item in conversations[:100]
        ],
    })


@api_view(["GET"])
def chat_conversation_detail(request, conversation_id):
    if not request.user.is_authenticated:
        return Response(
            {"success": False, "error": "Authentication required."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        conversation_uuid = uuid.UUID(str(conversation_id))
    except (ValueError, TypeError, AttributeError):
        return Response(
            {"success": False, "error": "Invalid conversation ID."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    conversation = ChatConversation.objects.filter(
        id=conversation_uuid,
        user=request.user,
    ).first()

    if conversation is None:
        return Response(
            {"success": False, "error": "Conversation not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    messages = conversation.messages.order_by("created_at")

    return Response({
        "success": True,
        "conversation": _conversation_payload(conversation),
        "messages": [
            _message_payload(message)
            for message in messages
        ],
    })


@api_view(["DELETE"])
def delete_chat_conversation(request, conversation_id):
    if not request.user.is_authenticated:
        return Response(
            {"success": False, "error": "Authentication required."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        conversation_uuid = uuid.UUID(str(conversation_id))
    except (ValueError, TypeError, AttributeError):
        return Response(
            {"success": False, "error": "Invalid conversation ID."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    deleted_count, _ = ChatConversation.objects.filter(
        id=conversation_uuid,
        user=request.user,
    ).delete()

    if not deleted_count:
        return Response(
            {"success": False, "error": "Conversation not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response({
        "success": True,
        "message": "Conversation deleted.",
    })




@api_view(["POST"])
def send_chat_message(request):
    if not request.user.is_authenticated:
        return Response(
            {"success": False, "error": "Authentication required."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    message_text = request.data.get("message", "")
    conversation_id = request.data.get("conversation_id")
    scope = request.data.get("scope", "all_tenders")
    tender_pk = request.data.get("tender_pk")

    if not isinstance(message_text, str) or not message_text.strip():
        return Response(
            {"success": False, "error": "Message cannot be empty."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    message_text = message_text.strip()

    if len(message_text) > 10000:
        return Response(
            {"success": False, "error": "Message is too long."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Universal retrieval will be implemented separately.
    if scope == "all_tenders":
        return Response(
            {
                "success": False,
                "error": (
                    "Universal mode is not connected yet. "
                    "Select a specific tender to ask document questions."
                ),
                "code": "UNIVERSAL_MODE_NOT_READY",
            },
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    if scope != "tender":
        return Response(
            {"success": False, "error": "Invalid chat scope."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if conversation_id:
        try:
            conversation_uuid = uuid.UUID(str(conversation_id))
        except (ValueError, TypeError, AttributeError):
            return Response(
                {"success": False, "error": "Invalid conversation ID."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        conversation = ChatConversation.objects.filter(
            id=conversation_uuid,
            user=request.user,
        ).first()

        if conversation is None:
            return Response(
                {"success": False, "error": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if conversation.scope != ChatConversation.Scope.TENDER:
            return Response(
                {"success": False, "error": "This conversation is not tender-scoped."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tender = conversation.tender
        if tender is None:
            return Response(
                {"success": False, "error": "The linked tender no longer exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if tender_pk and str(tender_pk) != str(tender.pk):
            return Response(
                {"success": False, "error": "Tender does not match this conversation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    else:
        if not tender_pk:
            return Response(
                {
                    "success": False,
                    "error": "tender_pk is required for tender-specific chat.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        tender = Tender.objects.filter(pk=tender_pk).first()
        if tender is None:
            return Response(
                {"success": False, "error": "Tender not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        conversation = ChatConversation.objects.create(
            user=request.user,
            title=message_text[:200],
            scope=ChatConversation.Scope.TENDER,
            tender=tender,
        )

    # Save the user's message before calling the AI service.
    user_message = ChatMessage.objects.create(
        conversation=conversation,
        role=ChatMessage.Role.USER,
        content=message_text,
    )

    try:
        # Import lazily so existing endpoints do not load the AI model.
        from ai.services.documents.answer_generation_service import (
            AnswerGenerationService,
        )

        service = AnswerGenerationService()
        result = service.answer(
            tender_id=tender.tender_id,
            question=message_text,
        )

        answer_text = result.get(
            "answer",
            "I couldn't generate an answer for this question.",
        )
        citations = result.get("citations", [])
        insufficient_evidence = result.get(
            "insufficient_evidence",
            False,
        )

        assistant_message = ChatMessage.objects.create(
            conversation=conversation,
            role=ChatMessage.Role.ASSISTANT,
            content=answer_text,
            citations=citations,
            metadata={
                "insufficient_evidence": insufficient_evidence,
            },
        )

        conversation.updated_at = timezone.now()
        conversation.save(update_fields=["updated_at"])

        return Response(
            {
                "success": True,
                "conversation": _conversation_payload(conversation),
                "user_message": _message_payload(user_message),
                "assistant_message": _message_payload(assistant_message),
                "insufficient_evidence": insufficient_evidence,
            },
            status=status.HTTP_200_OK,
        )

    except Exception:
        # Log the full exception server-side before production deployment.
        return Response(
            {
                "success": False,
                "error": (
                    "The message was saved, but the AI service "
                    "could not generate a response. Please try again."
                ),
                "conversation_id": str(conversation.id),
                "user_message_id": str(user_message.id),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )


@role_required_api(["admin", "manager"])
@api_view(["POST"])
def make_tender_decision(request, tender_id):
    decision = request.data.get("decision")
    remarks = request.data.get("remarks", "")

    valid_decisions = [
        TenderDecision.Decision.GO,
        TenderDecision.Decision.NO_GO,
        TenderDecision.Decision.HOLD,
    ]

    if decision not in valid_decisions:
        return Response({
            "success": False,
            "error": "Invalid decision. Choose GO, NO_GO or HOLD."
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            tender = get_object_or_404(
                Tender.objects.select_for_update(),
                pk=tender_id
            )

            # Record management decision
            TenderDecision.objects.create(
                tender=tender,
                decision=decision,
                remarks=remarks,
                decided_by=request.user
            )

            my_tender = None
            execution = None
            execution_created = False

            # GO: Add to My Tenders and create execution workflow
            if decision == TenderDecision.Decision.GO:
                my_tender, _ = MyTender.objects.get_or_create(
                    tender=tender
                )

                execution, execution_created = create_execution_plan(
                    my_tender=my_tender,
                    created_by=request.user
                )

            return Response({
                "success": True,
                "message": f"Tender decision recorded: {decision}",
                "decision": decision,
                "tender_id": tender.id,
                "my_tender_id": my_tender.id if my_tender else None,
                "added_to_my_tenders": my_tender is not None,
                "execution_id": execution.id if execution else None,
                "execution_created": execution_created,
                "workspace_url": (
                    f"/my-tenders/{my_tender.id}/execution/"
                    if execution else None
                )
            }, status=status.HTTP_200_OK)

    except Exception:
        logger.exception("Failed to record tender decision.")
        return Response({
            "success": False,
            "error": "Unable to process tender decision."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["GET"])
def get_my_tenders(request):
    """
    Server-side DataTables API for management-approved tenders.

    Supports:
    - Pagination
    - Search
    - My Tender lifecycle statistics
    """
    try:
        start = max(0, int(request.GET.get("start", 0)))
        length = max(1, min(int(request.GET.get("length", 10)), 100))
        search_value = request.GET.get("search[value]", "").strip()

        # Only tenders added to My Tenders
        queryset = MyTender.objects.select_related("tender", "tender__priority")
        records_total = queryset.count()

        # Search across original tender details and lifecycle status
        if search_value:
            search_filter = (
                Q(tender__tender_id__icontains=search_value)
                | Q(tender__source_tender_id__icontains=search_value)
                | Q(tender__tender_ref_no__icontains=search_value)
                | Q(tender__title__icontains=search_value)
                | Q(tender__description__icontains=search_value)
                | Q(tender__company_name__icontains=search_value)
                | Q(tender__state__icontains=search_value)
                | Q(tender__city__icontains=search_value)
                | Q(status__icontains=search_value)
            )
            if search_value.isdigit():
                search_filter |= Q(tender__pk=int(search_value)) | Q(pk=int(search_value))

            queryset = queryset.filter(search_filter)

        records_filtered = queryset.count()
        queryset = queryset.order_by("-added_at")

        # Pagination
        paginator = Paginator(queryset, length)
        page_number = (start // length) + 1
        page = paginator.get_page(page_number)

        data = []
        for my_tender in page.object_list:
            tender = my_tender.tender
            # TenderPriority is optional
            priority = getattr(tender, "priority", None)
            location_parts = [value for value in [tender.city, tender.state] if value]

            data.append({
                "id": tender.id,
                "my_tender_id": my_tender.id,
                "tender_id": tender.tender_id,
                "title": tender.title,
                "tender_ref_no": tender.tender_ref_no,
                "authority": tender.company_name,
                "location": ", ".join(location_parts) if location_parts else "Pan India",
                "capacity_mw": float(priority.capacity_mw) if priority and priority.capacity_mw is not None else None,
                "amount_crore": float(priority.amount_crore) if priority and priority.amount_crore is not None else None,
                "tender_value": float(tender.tender_value) if tender.tender_value is not None else None,
                "due_date": tender.closing_date.strftime("%d-%m-%Y") if tender.closing_date else None,
                "closing_date": tender.closing_date.isoformat() if tender.closing_date else None,
                "status": my_tender.status,
                "status_label": my_tender.get_status_display(),
                "added_at": my_tender.added_at.isoformat(),
                # Workspace URL will be connected in the next step
                "view_url": f"/tenders/{tender.id}/",
                "workspace_url": f"/my-tenders/{my_tender.id}/execution/",
            })

        # Statistics across all My Tenders, not just the current page
        today = timezone.localdate()
        all_my_tenders = MyTender.objects.all()
        total_count = all_my_tenders.count()

        active_count = all_my_tenders.exclude(
            status__in=[
                MyTender.Status.WON,
                MyTender.Status.LOST,
                MyTender.Status.CLOSED,
            ]
        ).count()

        submitted_count = all_my_tenders.filter(status=MyTender.Status.SUBMITTED).count()
        won_count = all_my_tenders.filter(status=MyTender.Status.WON).count()
        lost_count = all_my_tenders.filter(status=MyTender.Status.LOST).count()
        upcoming_deadlines = all_my_tenders.filter(tender__closing_date__gte=today).count()
        capacity_total = all_my_tenders.aggregate(total=Sum("tender__priority__capacity_mw"))["total"]

        return Response(
            {
                "draw": int(request.GET.get("draw", 1)),
                "recordsTotal": records_total,
                "recordsFiltered": records_filtered,
                "data": data,
                "stats": {
                    "total_tenders": total_count,
                    "active_tenders": active_count,
                    "submitted_count": submitted_count,
                    "won_count": won_count,
                    "lost_count": lost_count,
                    "upcoming_deadlines": upcoming_deadlines,
                    "total_capacity_mw": float(capacity_total) if capacity_total is not None else 0,
                },
            },
            status=status.HTTP_200_OK,
        )
    except Exception:
        logger.exception("Failed to retrieve My Tenders.")
        return Response(
            {"success": False, "error": "Unable to retrieve My Tenders."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def execution_api_error(exc):
    if isinstance(exc, Http404):
        return Response({
            "success": False,
            "error": "Execution plan not found."
        }, status=status.HTTP_404_NOT_FOUND)

    if isinstance(exc, ValidationError):
        return Response({
            "success": False,
            "error": exc.messages
        }, status=status.HTTP_400_BAD_REQUEST)

    logger.exception("Execution API error")
    return Response({
        "success": False,
        "error": "Unable to process execution request."
    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def require_approved_employee(request):
    if not request.user.is_authenticated:
        return Response({
            "success": False,
            "error": "Authentication required."
        }, status=status.HTTP_401_UNAUTHORIZED)

    if not (
        is_system_admin(request.user)
        or is_approved_employee(request.user)
    ):
        return Response({
            "success": False,
            "error": "Approved employee access required."
        }, status=status.HTTP_403_FORBIDDEN)

    return None

def require_task_management_permission(request):
    """
    Allow Admin and approved employees at Levels 2, 3 and 4
    to manage all tasks within a tender execution.
    """
    access_error = require_approved_employee(request)
    if access_error:
        return access_error
    if is_system_admin(request.user):
        return None
    profile = request.user.profile
    if profile.level not in (2, 3, 4):
        return Response(
            {
                "success": False,
                "error": "You do not have permission to manage execution tasks."
            },
            status=status.HTTP_403_FORBIDDEN
        )
    return None


@api_view(["GET"])
def get_tender_execution_workspace(request, my_tender_id):
    """
    Retrieve complete Tender Execution Workspace data.
    """
    if not request.user.is_authenticated:
        return Response(
            {
                "success": False,
                "error": "Authentication required.",
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )
    access_error = require_approved_employee(request)
    if access_error:
        return access_error

    try:
        execution = (
            TenderExecution.objects
            .select_related(
                "my_tender__tender",
                "template",
            )
            .filter(my_tender_id=my_tender_id)
            .first()
        )

        if not execution:
            return Response(
                {
                    "success": False,
                    "error": "Execution plan not found for this tender.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        my_tender = execution.my_tender
        tender = my_tender.tender

        # Calculate progress dynamically.
        progress = calculate_execution_progress(execution)

        # Copy JSON so response formatting doesn't modify stored data.
        workflow_data = copy.deepcopy(execution.workflow_data)

        # Do not expose internal storage paths.
        for phase in workflow_data.get("phases", []):
            for task in phase.get("tasks", []):
                for attachment in task.get("attachments", []):
                    attachment.pop("file_path", None)

        # Fetch recent execution activities.
        activities = (
            ExecutionActivity.objects
            .filter(execution=execution)
            .select_related("performed_by")
            .order_by("-created_at")[:100]
        )

        activity_data = [
            {
                "id": activity.id,
                "task_id": activity.task_id,
                "activity_type": activity.activity_type,
                "description": activity.description,
                "metadata": activity.metadata,
                "performed_by": (
                    {
                        "id": activity.performed_by_id,
                        "username": activity.performed_by.get_username(),
                    }
                    if activity.performed_by else None
                ),
                "created_at": activity.created_at.isoformat(),
            }
            for activity in activities
        ]

        data = {
            "execution": {
                "id": execution.id,
                "template_id": execution.template_id,
                "template_name": (
                    execution.template.name
                    if execution.template else None
                ),
                "template_version": (
                    execution.template.version
                    if execution.template else None
                ),
                "started_at": execution.started_at.isoformat(),
                "updated_at": execution.updated_at.isoformat(),
            },

            "tender": {
                "id": tender.id,
                "tender_id": tender.tender_id,
                "title": tender.title,
                "reference_number": tender.tender_ref_no,
                "organization": tender.company_name,
                "location": ", ".join(
                    value for value in [tender.city, tender.state]
                    if value
                ),
                "tender_value": (
                    float(tender.tender_value)
                    if tender.tender_value is not None else None
                ),
                "closing_date": (
                    tender.closing_date.isoformat()
                    if tender.closing_date else None
                ),
            },

            "my_tender": {
                "id": my_tender.id,
                "status": my_tender.status,
                "status_display": my_tender.get_status_display(),
                "remarks": my_tender.remarks,
            },

            "progress": progress,

            "workflow_data": workflow_data,

            "activities": activity_data,
        }

        return Response(
            {
                "success": True,
                "data": data,
            },
            status=status.HTTP_200_OK,
        )

    except Exception:
        logger.exception(
            "Failed to retrieve execution workspace for MyTender %s",
            my_tender_id,
        )

        return Response(
            {
                "success": False,
                "error": "Unable to retrieve tender execution workspace.",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def get_execution_for_api(my_tender_id):
    return get_object_or_404(
        TenderExecution.objects.select_related("my_tender"),
        my_tender_id=my_tender_id
    )


def execution_api_error(exc):
    if isinstance(exc, ValidationError):
        return Response({
            "success": False,
            "error": exc.messages
        }, status=status.HTTP_400_BAD_REQUEST)

    logger.exception("Execution API error")
    return Response({
        "success": False,
        "error": "Unable to process execution request."
    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["POST"])
def update_execution_task_applicability(request, my_tender_id, task_id):
    if not request.user.is_authenticated:
        return Response(
            {"success": False, "error": "Authentication required."},
            status=status.HTTP_401_UNAUTHORIZED
        )
    access_error = require_task_management_permission(request)
    if access_error:
        return access_error

    if "is_applicable" not in request.data:
        return Response({
            "success": False,
            "error": "is_applicable is required."
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        execution = get_execution_for_api(my_tender_id)

        set_task_applicability(
            execution_id=execution.id,
            task_id=str(task_id),
            is_applicable=request.data["is_applicable"],
            performed_by=request.user,
            remarks=request.data.get("remarks", "")
        )

        return Response({
            "success": True,
            "message": "Task applicability updated successfully."
        })

    except ValidationError as exc:
        return execution_api_error(exc)
    except Exception as exc:
        return execution_api_error(exc)

@api_view(["POST"])
def create_execution_custom_task(request, my_tender_id):
    if not request.user.is_authenticated:
        return Response(
            {"success": False, "error": "Authentication required."},
            status=status.HTTP_401_UNAUTHORIZED
        )
    access_error = require_task_management_permission(request)
    if access_error:
        return access_error

    required_fields = ["phase_code", "title"]

    missing_fields = [
        field for field in required_fields
        if not request.data.get(field)
    ]

    if missing_fields:
        return Response({
            "success": False,
            "error": f"Required fields: {', '.join(missing_fields)}"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        execution = get_execution_for_api(my_tender_id)

        task = add_custom_task(
            execution_id=execution.id,
            phase_code=request.data["phase_code"],
            title=request.data["title"],
            description=request.data.get("description", ""),
            department=request.data.get("department", ""),
            priority=request.data.get("priority", "MEDIUM"),
            due_date=request.data.get("due_date"),
            dependencies=request.data.get("dependencies", []),
            created_by=request.user
        )

        return Response({
            "success": True,
            "message": "Custom task created successfully.",
            "data": task
        }, status=status.HTTP_201_CREATED)

    except ValidationError as exc:
        return execution_api_error(exc)
    except Exception as exc:
        return execution_api_error(exc)


@api_view(["POST"])
def update_execution_custom_task(request, my_tender_id, task_id):
    if not request.user.is_authenticated:
        return Response(
            {
                "success": False,
                "error": "Authentication required."
            },
            status=status.HTTP_401_UNAUTHORIZED
        )
    access_error = require_task_management_permission(request)
    if access_error:
        return access_error

    required_fields = ["title"]

    missing_fields = [
        field for field in required_fields
        if not request.data.get(field)
    ]

    if missing_fields:
        return Response(
            {
                "success": False,
                "error": f"Required fields: {', '.join(missing_fields)}"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        execution = get_execution_for_api(my_tender_id)

        execution, task = update_custom_task(
            execution_id=execution.id,
            task_id=str(task_id),
            title=request.data["title"],
            description=request.data.get("description", ""),
            department=request.data.get("department", ""),
            priority=request.data.get("priority", "MEDIUM"),
            due_date=request.data.get("due_date"),
            dependencies=request.data.get("dependencies", []),
            updated_by=request.user,
        )

        return Response({
            "success": True,
            "message": "Custom task updated successfully.",
            "data": task
        })

    except ValidationError as exc:
        return execution_api_error(exc)

    except Exception as exc:
        return execution_api_error(exc)


@api_view(["POST"])
def assign_execution_task(request, my_tender_id, task_id):

    access_error = require_approved_employee(request)
    if access_error:
        return access_error

    # Only Admin and Levels 2-4 can assign tasks.
    if not is_system_admin(request.user):
        if request.user.profile.level not in (2, 3, 4):
            return Response({
                "success": False,
                "error": "You do not have permission to assign tasks."
            }, status=status.HTTP_403_FORBIDDEN)

    assignee_ids = request.data.get("assignee_ids")

    if not isinstance(assignee_ids, list):
        return Response({
            "success": False,
            "error": "assignee_ids must be a list."
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        execution = get_execution_for_api(my_tender_id)

        User = get_user_model()

        selected_users = User.objects.filter(
            pk__in=assignee_ids,
            is_active=True
        ).select_related("profile")

        selected_user_map = {
            str(user.pk): user
            for user in selected_users
        }

        normalized_ids = list(dict.fromkeys(
            str(user_id)
            for user_id in assignee_ids
        ))

        for user_id in normalized_ids:
            target_user = selected_user_map.get(user_id)

            if not target_user:
                return Response({
                    "success": False,
                    "error": f"Invalid or inactive employee: {user_id}"
                }, status=status.HTTP_400_BAD_REQUEST)

            if not can_assign_to_employee(request.user, target_user):
                return Response({
                    "success": False,
                    "error": (
                        "You are not authorized to assign tasks to this employee. "
                        "You can only assign tasks within your permitted "
                        "organizational hierarchy."
                    )
                }, status=status.HTTP_403_FORBIDDEN)

        set_task_assignees(
            execution_id=execution.id,
            task_id=str(task_id),
            assignee_ids=assignee_ids,
            performed_by=request.user
        )

        return Response({
            "success": True,
            "message": "Task assignees updated successfully."
        }, status=status.HTTP_200_OK)

    except (ValidationError, Http404) as exc:
        return execution_api_error(exc)

    except Exception as exc:
        return execution_api_error(exc)

    
@api_view(["POST"])
def update_execution_task_status(request, my_tender_id, task_id):
    if not request.user.is_authenticated:
        return Response(
            {"success": False, "error": "Authentication required."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    new_status = request.data.get("status")

    if not new_status:
        return Response({
            "success": False,
            "error": "status is required."
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        execution = get_execution_for_api(my_tender_id)
        task, access_error = require_task_access(request, execution, task_id)
        if access_error:
            return access_error

        update_task_status(
            execution_id=execution.id,
            task_id=str(task_id),
            new_status=new_status,
            performed_by=request.user,
            remarks=request.data.get("remarks", "")
        )

        return Response({
            "success": True,
            "message": "Task status updated successfully.",
            "progress": calculate_execution_progress(execution)
        })

    except ValidationError as exc:
        return execution_api_error(exc)
    except Exception as exc:
        return execution_api_error(exc)

@api_view(["POST"])
def add_execution_task_comment(request, my_tender_id, task_id):
    if not request.user.is_authenticated:
        return Response(
            {"success": False, "error": "Authentication required."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    comment = request.data.get("comment", "").strip()

    if not comment:
        return Response({
            "success": False,
            "error": "Comment cannot be empty."
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        execution = get_execution_for_api(my_tender_id)
        task, access_error = require_task_access(request, execution, task_id)
        if access_error:
            return access_error

        add_task_comment(
            execution_id=execution.id,
            task_id=str(task_id),
            comment=comment,
            performed_by=request.user
        )

        return Response({
            "success": True,
            "message": "Comment added successfully."
        }, status=status.HTTP_201_CREATED)

    except ValidationError as exc:
        return execution_api_error(exc)
    except Exception as exc:
        return execution_api_error(exc)

@api_view(["POST"])
def update_execution_task_remarks(request, my_tender_id, task_id):
    if not request.user.is_authenticated:
        return Response(
            {"success": False, "error": "Authentication required."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    if "remarks" not in request.data:
        return Response({
            "success": False,
            "error": "remarks is required."
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        execution = get_execution_for_api(my_tender_id)
        task, access_error = require_task_access(request, execution, task_id)
        if access_error:
            return access_error

        update_task_remarks(
            execution_id=execution.id,
            task_id=str(task_id),
            remarks=request.data["remarks"],
            performed_by=request.user
        )

        return Response({
            "success": True,
            "message": "Task remarks updated successfully."
        })

    except ValidationError as exc:
        return execution_api_error(exc)
    except Exception as exc:
        return execution_api_error(exc)


@api_view(["POST"])
def configure_execution_task_approvers(request, my_tender_id, task_id):
    if not request.user.is_authenticated:
        return Response({
            "success": False,
            "error": "Authentication required."
        }, status=status.HTTP_401_UNAUTHORIZED)
    access_error = require_task_management_permission(request)
    if access_error:
        return access_error
    approver_ids = request.data.get("approver_ids")
    approval_mode = request.data.get("approval_mode", "ALL")

    if not isinstance(approver_ids, list) or not approver_ids:
        return Response({
            "success": False,
            "error": "approver_ids must be a non-empty list."
        }, status=status.HTTP_400_BAD_REQUEST)

    if approval_mode not in ["ALL", "ANY"]:
        return Response({
            "success": False,
            "error": "approval_mode must be ALL or ANY."
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        execution = get_execution_for_api(my_tender_id)

        configure_task_approvers(
            execution_id=execution.id,
            task_id=str(task_id),
            approver_ids=approver_ids,
            approval_mode=approval_mode,
            performed_by=request.user
        )

        return Response({
            "success": True,
            "message": "Task approvers configured successfully.",
            "data": {
                "approver_ids": approver_ids,
                "approval_mode": approval_mode
            }
        }, status=status.HTTP_200_OK)

    except (ValidationError, Http404) as exc:
        return execution_api_error(exc)
    except Exception as exc:
        return execution_api_error(exc)

@api_view(["POST"])
def submit_execution_task_approval(request, my_tender_id, task_id):
    if not request.user.is_authenticated:
        return Response({
            "success": False,
            "error": "Authentication required."
        }, status=status.HTTP_401_UNAUTHORIZED)

    decision = request.data.get("decision", "").upper()
    remarks = request.data.get("remarks", "")

    if decision not in ["APPROVED", "REJECTED"]:
        return Response({
            "success": False,
            "error": "decision must be APPROVED or REJECTED."
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        execution = get_execution_for_api(my_tender_id)

        submit_task_approval(
            execution_id=execution.id,
            task_id=str(task_id),
            decision=decision,
            approver=request.user,
            remarks=remarks
        )

        # Read the updated approval state from the execution snapshot.
        execution.refresh_from_db()

        task_data = next(
            (
                task
                for phase in execution.workflow_data.get("phases", [])
                for task in phase.get("tasks", [])
                if task.get("id") == str(task_id)
            ),
            None
        )

        if task_data is None:
            return Response({
                "success": False,
                "error": "Task not found."
            }, status=status.HTTP_404_NOT_FOUND)

        approval_data = {
            "approval_required": task_data.get("approval_required", False),
            "approval_status": task_data.get("approval_status"),
            "approval_mode": task_data.get("approval_mode"),
            "approval_round": task_data.get("approval_round"),
            "approver_ids": task_data.get("approver_ids", []),
            "approvals": task_data.get("approvals", [])
        }

        return Response({
            "success": True,
            "message": "Approval decision submitted successfully.",
            "data": approval_data
        }, status=status.HTTP_200_OK)

    except (ValidationError, Http404) as exc:
        return execution_api_error(exc)
    except Exception as exc:
        return execution_api_error(exc)

@api_view(["POST"])
def upload_execution_task_attachment(request, my_tender_id, task_id):
    if not request.user.is_authenticated:
        return Response({
            "success": False,
            "error": "Authentication required."
        }, status=status.HTTP_401_UNAUTHORIZED)

    uploaded_file = request.FILES.get("file")

    if not uploaded_file:
        return Response({
            "success": False,
            "error": "Please select a file to upload."
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        execution = get_execution_for_api(my_tender_id)
        task, access_error = require_task_access(request, execution, task_id)
        if access_error:
            return access_error

        attachment = add_task_attachment(
            execution_id=execution.id,
            task_id=str(task_id),
            uploaded_file=uploaded_file,
            uploaded_by=request.user
        )

        # Never expose the internal storage path.
        if isinstance(attachment, dict):
            attachment.pop("file_path", None)

        return Response({
            "success": True,
            "message": "Attachment uploaded successfully.",
            "data": attachment
        }, status=status.HTTP_201_CREATED)

    except (ValidationError, Http404) as exc:
        return execution_api_error(exc)
    except Exception as exc:
        return execution_api_error(exc)

@api_view(["DELETE"])
def delete_execution_task_attachment(request, my_tender_id, task_id, attachment_id):
    if not request.user.is_authenticated:
        return Response({
            "success": False,
            "error": "Authentication required."
        }, status=status.HTTP_401_UNAUTHORIZED)

    try:
        execution = get_execution_for_api(my_tender_id)
        task, access_error = require_task_access(request, execution, task_id)
        if access_error:
            return access_error

        delete_task_attachment(
            execution_id=execution.id,
            task_id=str(task_id),
            attachment_id=str(attachment_id),
            deleted_by=request.user
        )

        return Response({
            "success": True,
            "message": "Attachment deleted successfully."
        }, status=status.HTTP_200_OK)

    except (ValidationError, Http404) as exc:
        return execution_api_error(exc)
    except Exception as exc:
        return execution_api_error(exc)

@api_view(["GET"])
def download_execution_task_attachment(
    request,
    my_tender_id,
    task_id,
    attachment_id
):
    try:
        execution = get_execution_for_api(my_tender_id)

        # Find the requested task.
        task_data = None

        for phase in execution.workflow_data.get("phases", []):
            for task in phase.get("tasks", []):
                if task.get("id") == str(task_id):
                    task_data = task
                    break

            if task_data:
                break

        if not task_data:
            return Response({
                "success": False,
                "error": "Task not found."
            }, status=status.HTTP_404_NOT_FOUND)

        # Find the requested attachment.
        attachment = next(
            (
                item
                for item in task_data.get("attachments", [])
                if item.get("id") == str(attachment_id)
            ),
            None
        )

        if not attachment:
            return Response({
                "success": False,
                "error": "Attachment not found."
            }, status=status.HTTP_404_NOT_FOUND)

        file_path = attachment.get("file_path")

        if not file_path:
            return Response({
                "success": False,
                "error": "Attachment file reference is missing."
            }, status=status.HTTP_404_NOT_FOUND)

        # Check whether the file exists in configured storage.
        if not default_storage.exists(file_path):
            return Response({
                "success": False,
                "error": "Attachment file does not exist in storage."
            }, status=status.HTTP_404_NOT_FOUND)

        file_obj = default_storage.open(file_path, "rb")

        filename = (
            attachment.get("original_name")
            or attachment.get("file_name")
            or attachment.get("name")
            or "attachment"
        )

        content_type = attachment.get(
            "content_type",
            "application/octet-stream"
        )

        return FileResponse(
            file_obj,
            as_attachment=True,
            filename=filename,
            content_type=content_type
        )

    except Http404 as exc:
        return execution_api_error(exc)

    except Exception as exc:
        logger.exception(
            "Failed to download attachment %s for task %s",
            attachment_id,
            task_id
        )
        return Response({
            "success": False,
            "error": "Unable to download attachment."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["GET"])
def get_execution_activities(request, my_tender_id):
    try:
        execution = get_execution_for_api(my_tender_id)

        activities = (
            ExecutionActivity.objects
            .filter(execution=execution)
            .select_related("performed_by")
            .order_by("-created_at")
        )

        # Optional task-level filtering.
        task_id = request.query_params.get("task_id")

        if task_id:
            activities = activities.filter(task_id=task_id)

        # Get total count before applying the limit.
        total_count = activities.count()

        # Validate and apply response limit.
        try:
            limit = int(request.query_params.get("limit", 100))
        except (TypeError, ValueError):
            return Response({
                "success": False,
                "error": "limit must be a valid integer."
            }, status=status.HTTP_400_BAD_REQUEST)

        if limit < 1:
            return Response({
                "success": False,
                "error": "limit must be greater than zero."
            }, status=status.HTTP_400_BAD_REQUEST)

        limit = min(limit, 200)
        activities = activities[:limit]

        activity_data = [
            {
                "id": activity.id,
                "task_id": activity.task_id or None,
                "activity_type": activity.activity_type,
                "description": activity.description,
                "metadata": activity.metadata,
                "performed_by": (
                    {
                        "id": activity.performed_by_id,
                        "username": activity.performed_by.get_username()
                    }
                    if activity.performed_by else None
                ),
                "created_at": activity.created_at.isoformat(),
            }
            for activity in activities
        ]

        return Response({
            "success": True,
            "data": {
                "activities": activity_data,
                "count": total_count
            }
        }, status=status.HTTP_200_OK)

    except Http404 as exc:
        return execution_api_error(exc)

    except Exception:
        logger.exception(
            "Failed to retrieve execution activities for MyTender %s",
            my_tender_id
        )
        return Response({
            "success": False,
            "error": "Unable to retrieve execution activities."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(["GET"])
def get_execution_dashboard(request, my_tender_id):
    try:
        execution = get_execution_for_api(my_tender_id)

        progress = calculate_execution_progress(execution)

        workflow_data = execution.workflow_data or {}
        phases = workflow_data.get("phases", [])

        task_counts = {
            "PENDING": 0,
            "IN_PROGRESS": 0,
            "COMPLETED": 0,
            "BLOCKED": 0,
            "CANCELLED": 0,
            "NOT_APPLICABLE": 0,
            "UNDECIDED": 0,
        }

        # The progress service returns phases as a LIST.
        # Create a lookup using phase_code.
        progress_phases = {
            phase.get("phase_code"): phase
            for phase in progress.get("phases", [])
        }

        phase_data = []

        for phase in phases:
            tasks = phase.get("tasks", [])

            phase_counts = {
                "PENDING": 0,
                "IN_PROGRESS": 0,
                "COMPLETED": 0,
                "BLOCKED": 0,
                "CANCELLED": 0,
                "NOT_APPLICABLE": 0,
                "UNDECIDED": 0,
            }

            for task in tasks:
                task_status = task.get("status", "PENDING")

                # Handle optional/conditional tasks not yet decided.
                if (
                    task.get("is_applicable") is None
                    and (task.get("optional") or task.get("condition"))
                ):
                    task_status = "UNDECIDED"

                if task_status not in phase_counts:
                    task_status = "PENDING"

                phase_counts[task_status] += 1
                task_counts[task_status] += 1

            phase_progress = progress_phases.get(
                phase.get("code"), {}
            )

            phase_data.append({
                "code": phase.get("code"),
                "name": phase.get("name"),
                "sequence": phase.get("sequence"),
                "progress": phase_progress.get("progress", 0),
                "total_tasks": phase_progress.get("total_tasks", 0),
                "completed_tasks": phase_progress.get("completed_tasks", 0),
                "pending_tasks": phase_progress.get("pending_tasks", 0),
                "undecided_tasks": phase_progress.get("undecided_tasks", 0),
                "not_applicable_tasks": phase_progress.get(
                    "not_applicable_tasks", 0
                ),
                "task_counts": phase_counts,
            })

        return Response({
            "success": True,
            "data": {
                "overall_progress": progress.get("overall_progress", 0),

                # Applicable tasks only (excludes N/A and undecided).
                "total_tasks": progress.get("total_tasks", 0),

                # All tasks in the original workflow template.
                "all_workflow_tasks": sum(
                    len(phase.get("tasks", []))
                    for phase in phases
                ),

                "task_counts": task_counts,
                "phases": phase_data,
                "progress_details": progress,
            }
        }, status=status.HTTP_200_OK)

    except Http404 as exc:
        return execution_api_error(exc)

    except Exception:
        logger.exception(
            "Failed to retrieve execution dashboard for MyTender %s",
            my_tender_id
        )
        return Response({
            "success": False,
            "error": "Unable to retrieve execution dashboard."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




@api_view(["GET"])
def get_execution_available_users(request):
    """
    Return approved employees available for execution assignment.
    Employee search is organization-wide.
    """
    access_error = require_approved_employee(request)
    if access_error:
        return access_error

    if not is_system_admin(request.user):
        profile = request.user.profile

        if profile.level not in (2, 3, 4):
            return Response({
                "success": False,
                "error": "You do not have permission to assign tasks."
            }, status=status.HTTP_403_FORBIDDEN)

    profiles = get_approved_employee_profiles().order_by(
        "user__first_name",
        "user__last_name",
        "user__username"
    )

    user_data = [
        {
            "id": profile.user_id,
            "username": profile.user.username,
            "full_name": (
                profile.user.get_full_name()
                or profile.user.username
            ),
            "employee_id": profile.employee_id,
            "department": profile.department,
            "designation": profile.designation,
            "level": profile.level,
            "reporting_manager": (
                profile.reporting_manager.user.get_full_name()
                or profile.reporting_manager.user.username
                if profile.reporting_manager
                else None
            ),
        }
        for profile in profiles
    ]

    return Response({
        "success": True,
        "data": user_data
    }, status=status.HTTP_200_OK)


def get_execution_task(execution, task_id):
    """Find a task in the execution workflow snapshot."""
    for phase in execution.workflow_data.get("phases", []):
        for task in phase.get("tasks", []):
            if str(task.get("id")) == str(task_id):
                return task

    return None





def can_access_execution_task(user, task):
    """
    Access is granted to:
    - An assigned employee.
    - Any manager in that employee's reporting chain.
    - System administrators.
    """
    if is_system_admin(user):
        return True

    if not is_approved_employee(user):
        return False

    assignee_ids = {
        str(user_id)
        for user_id in task.get("assignees", [])
    }

    if not assignee_ids:
        return False

    # The assigned employee can access their own task.
    if str(user.pk) in assignee_ids:
        return True

    # Managers can access tasks assigned to employees below them.
    visible_profiles = get_reporting_tree_profiles(
        user,
        include_self=True
    )

    visible_user_ids = {
        str(profile.user_id)
        for profile in visible_profiles
    }

    return bool(assignee_ids.intersection(visible_user_ids))


def require_task_access(request, execution, task_id):
    """Return an API error if the user cannot access this task."""
    access_error = require_approved_employee(request)

    if access_error:
        return None, access_error

    task = get_execution_task(execution, task_id)

    if not task:
        return None, Response(
            {"success": False, "error": "Task not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if not can_access_execution_task(request.user, task):
        return None, Response(
            {
                "success": False,
                "error": "You do not have permission to access this task."
            },
            status=status.HTTP_403_FORBIDDEN
        )

    return task, None
