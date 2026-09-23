
from ai.services.tender_discovery import TenderDiscoveryService
from ai.services.tender_research import TenderResearchService
from api_gateway.mappers.ai_discovery import AITenderMapper

def fetch_ai_tenders(location="India"):
    service=TenderResearchService()
    result=service.research(location=location)

    tenders=[AITenderMapper.map(tender) for tender in result]

    return {
        "source":"ai_discovery",
        "tenders":tenders,
        "total_fetched":len(tenders),
        "unique_tenders":len(tenders),
    }