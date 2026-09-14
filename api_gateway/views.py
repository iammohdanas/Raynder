import json
from django.db.models.aggregates import Sum
from dotenv import load_dotenv
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api_gateway.models import Tender
from api_gateway.utils.filter_keywords import get_search_keywords
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
from .serializers import TenderSerializer
from api_gateway.models import Tender, TenderPriority
from api_gateway.services.tender_priority import TenderPriorityService


load_dotenv()


@api_view(["POST"])
def sync_tenders(request):
    try:
        auth_manager = TenderTigerAuthManager()
        auth = auth_manager.get_auth()
        search = TenderTigerSearch(auth)

 
        keywords = ["solar", "wind", "BESS", "Green Hydrogen", "33 KV", "66 KV", "132 KV", "110 KV", "765 KV", "800 KV", "220 KV", "400 KV", "765/400 KV", "Substations", "Transmission Lines", "VRFB"]
        keywords = get_search_keywords(keywords)
        created_count = 0
        updated_count = 0
        mapper = TenderTigerMapper()
        processed_tender_ids = set()
        total_fetched = 0

        for keyword in keywords:
            search_result = search.search(keyword=keyword, rescount=60)
            tenders_list = search_result.get("TenderList", [])
            total_fetched += len(tenders_list)

            for tender in tenders_list:
                tender_id = tender.get("tenderprocid")
                if tender_id in processed_tender_ids:
                    continue
                processed_tender_ids.add(tender_id)

                tender_data = mapper.map(tender)
                existing_tender = Tender.objects.filter(
                    source="tendertiger",
                    source_tender_id=tender_id,
                ).first()

                serializer = (
                    TenderSerializer(existing_tender, data=tender_data)
                    if existing_tender
                    else TenderSerializer(data=tender_data)
                )

                if serializer.is_valid():
                    tender_obj = serializer.save()
                    priority_data = TenderPriorityService.analyze(tender)
                    if priority_data["is_high_priority"]:
                        TenderPriority.objects.update_or_create(
                            tender=tender_obj,
                            defaults={"capacity_mw": priority_data["capacity_mw"], "amount_crore": priority_data["amount_crore"]},
                        )
                    else:
                        TenderPriority.objects.filter(tender=tender_obj).delete()
                    if existing_tender:
                        updated_count += 1
                    else:
                        created_count += 1
                else:
                    print(
                        f"Tender validation failed for keyword '{keyword}':",
                        serializer.errors,
                    )

        return Response(
            {
                "success": True,
                "source": "tendertiger",
                "keywords": keywords,
                "total_fetched": total_fetched,
                "unique_tenders_processed": len(processed_tender_ids),
                "created": created_count,
                "updated": updated_count,
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
            queryset = queryset.filter(
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
        tender = get_object_or_404(Tender, id=tender_id)
        serializer = TenderSerializer(tender)
        print("Tender Detail:", json.dumps(serializer.data))
        return Response(
            {
                "success": True,
                "data": serializer.data,
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
        if search_value:
            queryset = queryset.filter(
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
        
@api_view(["POST"])
def create_tender(request):
    """
    Create a tender manually.
    """
    try:
        tender_data = request.data.copy()
        tender_data["source"] = "other"
        tender_data["source_tender_id"] = f"manual-{tender_data.get('tender_id', '')}"
        
        serializer = TenderSerializer(data=tender_data)
        if serializer.is_valid():
            tender = serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "Tender created successfully.",
                    "data": TenderSerializer(tender).data,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {
                "success": False,
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    except Exception as e:
        return Response(
            {
                "success": False,
                "error": str(e),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        
