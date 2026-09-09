from django.db import transaction

from api_gateway.models import Tender
from api_gateway.services.tendertiger_mapper import TenderTigerMapper

from authenticator.services.tendertiger_auth_manager import TenderTigerAuthManager
from crawlers.tendertiger.crawler.auth import TenderTigerAuth
from crawlers.tendertiger.crawler.search import TenderTigerSearch
import json


from crawlers.tendertiger.crawler.config import (EMAIL, PASSWORD)


class TenderSyncService:

    def __init__(self):
        self.auth = None
        self.search_client = None

    def authenticate_tendertiger(self):
        self.auth = TenderTigerAuthManager()
        self.search_client = TenderTigerSearch(
            self.auth
        )

    @transaction.atomic
    def save_tender(self, tender_data, keyword):
        data = TenderTigerMapper.map(
            tender_data,
            keyword=keyword
        )
        external_id = data["external_id"]
        if not external_id:
            return None, False
        tender, created = Tender.objects.update_or_create(
            source="tendertiger",
            external_id=external_id,
            defaults=data
        )
        return tender, created

    def sync_tendertiger(self, keywords):
        self.authenticate_tendertiger()
        created_count = 0
        updated_count = 0
        for keyword in keywords:
            print(f"Searching TenderTiger: {keyword}")
            result = self.search_client.search(keyword)
            if isinstance(result, str):
                result = json.loads(result)
            tenders = result.get(
                "TenderList",
                []
            )


            for tender_data in tenders:
                tender, created = self.save_tender(
                    tender_data,
                    keyword
                )

                if tender is None:
                    continue

                if created:
                    created_count += 1
                else:
                    updated_count += 1

        return {
            "source": "tendertiger",
            "created": created_count,
            "updated": updated_count,
            "total_processed": (
                created_count + updated_count
            ),
        }