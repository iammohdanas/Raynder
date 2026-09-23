import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Raynder.settings")
django.setup()

from ai.services.tender_research import TenderResearchService


def main():
    print("=" * 80)
    print("RAYNDER - AI TENDER RESEARCH TEST")
    print("=" * 80)

    service = TenderResearchService()

    print("\nStarting diversified tender research...")
    print("Multiple research tracks will be executed.\n")

    tenders = service.research(location="India")
    print(f"\nUNIQUE TENDERS AFTER DEDUPLICATION: {len(tenders)}")

    print("\n" + "=" * 80)
    print(f"TENDERS DISCOVERED: {len(tenders)}")
    print("=" * 80)

    for index, tender in enumerate(tenders, start=1):
        print(f"\n{'-' * 80}")
        print(f"TENDER #{index}")
        print(f"{'-' * 80}")
        print(f"Title          : {tender.title}")
        print(f"Source         : {tender.source}")
        print(f"Source ID      : {tender.source_tender_id}")
        print(f"Reference No   : {tender.tender_ref_no}")
        print(f"TCNO           : {tender.tcno}")
        print(f"Capacity MW    : {tender.capacity_mw}")
        print(f"Amount Crore   : {tender.amount_crore}")
        print(f"Tender Value   : {tender.tender_value}")
        print(f"EMD            : {tender.earnest_money}")
        print(f"Company        : {tender.company_name}")
        print(f"State          : {tender.state}")
        print(f"City           : {tender.city}")
        print(f"Tender Date    : {tender.tender_date}")
        print(f"Opening Date   : {tender.opening_date}")
        print(f"Closing Date   : {tender.closing_date}")
        print(f"Live Status    : {tender.live_status}")
        print(f"Status         : {tender.status_text}")
        print(f"Documents      : {tender.document_available}")
        print(f"Description URL: {tender.description_url}")
        print(f"Official URL   : {tender.official_tender_url}")
        print(f"Document URL   : {tender.tender_document_url}")
        print(f"Original Source: {tender.original_source}")

        print("\nDescription:")
        print(tender.description)


if __name__ == "__main__":
    main()