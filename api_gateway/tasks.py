from celery import shared_task,chord
from api_gateway.sources.ai_discovery import fetch_ai_tenders
from api_gateway.sources.tendertiger import fetch_tendertiger_tenders
from api_gateway.services.all_tenders_sync import AllTenderSyncService

@shared_task
def sync_tendertiger():
    return fetch_tendertiger_tenders()


@shared_task
def sync_ai_discovery():
    return fetch_ai_tenders()


@shared_task
def process_source_results(results):
    tenders=[]
    for result in results:
        tenders.extend(result.get("tenders",[]))
    print(f"Total source tenders: {len(tenders)}")
    return AllTenderSyncService().process(tenders)


def sync_all_sources():
    return chord([
        sync_tendertiger.s(),
        sync_ai_discovery.s(),
    ])(process_source_results.s())