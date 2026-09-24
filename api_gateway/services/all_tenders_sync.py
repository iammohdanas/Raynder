
from api_gateway.sources.ai_discovery import fetch_ai_tenders
from api_gateway.sources.tendertiger import fetch_tendertiger_tenders
from django.db import transaction
from api_gateway.models import Tender
from api_gateway.serializers import  TenderSerializer
from api_gateway.models import Tender
from api_gateway.models import Tender, TenderPriority
from api_gateway.services.tender_priority import TenderPriorityService
from django.db import transaction
import time


class AllTenderSyncService:
    def sync(self):
        tenders=[]
        start_time = time.perf_counter()
        tendertiger=fetch_tendertiger_tenders()
        elapsed = time.perf_counter() - start_time
        print(f"TenderTiger tenders: {len(tendertiger['tenders'])}")
        print(f"time taken: {elapsed}")
        tenders.extend(tendertiger["tenders"])

        print("Fetching AI Discovery tenders...")
        ai=fetch_ai_tenders()
        elapsed = time.perf_counter() - start_time
        print(f"time taken: {elapsed}")
        print(f"AI Discovery tenders: {len(ai['tenders'])}")
        tenders.extend(ai["tenders"])

        return self._process_tenders(tenders)

    @transaction.atomic
    def _process_tenders(self,tenders):
        created=0
        updated=0
        failed=0

        for tender_data in tenders:
            source=tender_data.get("source")
            source_tender_id=tender_data.get("source_tender_id")

            existing_tender=Tender.objects.filter(
                source=source,
                source_tender_id=source_tender_id,
            ).first()

            serializer=(
                TenderSerializer(existing_tender,data=tender_data)
                if existing_tender
                else TenderSerializer(data=tender_data)
            )

            if not serializer.is_valid():
                failed+=1
                print(
                    "Tender validation failed:",
                    serializer.errors,
                    tender_data.get("title"),
                )
                continue

            tender_obj=serializer.save()

            priority_data=TenderPriorityService.analyze(tender_data)

            if priority_data["is_high_priority"]:
                TenderPriority.objects.update_or_create(
                    tender=tender_obj,
                    defaults={
                        "capacity_mw":priority_data["capacity_mw"],
                        "amount_crore":priority_data["amount_crore"],
                    },
                )
            else:
                TenderPriority.objects.filter(
                    tender=tender_obj
                ).delete()

            if existing_tender:
                updated+=1
            else:
                created+=1

        return {
            "total":len(tenders),
            "created":created,
            "updated":updated,
            "failed":failed,
        }