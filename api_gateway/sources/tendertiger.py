from api_gateway.utils.filter_keywords import get_search_keywords
from authenticator.services.tendertiger_auth_manager import TenderTigerAuthManager
from api_gateway.services.tendertiger_mapper import TenderTigerMapper
from crawlers.tendertiger.crawler.search import TenderTigerSearch

KEYWORDS=[
    "solar","wind","BESS","Green Hydrogen",
    "33 KV","66 KV","132 KV","110 KV",
    "765 KV","800 KV","220 KV","400 KV",
    "765/400 KV","Substations","Transmission Lines","VRFB"
]

def fetch_tendertiger_tenders():
    auth=TenderTigerAuthManager().get_auth()
    search=TenderTigerSearch(auth)
    mapper=TenderTigerMapper()
    keywords=get_search_keywords(KEYWORDS)

    tenders=[]
    processed_ids=set()
    total_fetched=0

    for keyword in keywords:
        result=search.search(keyword=keyword,rescount=6)
        tender_list=result.get("TenderList",[])
        total_fetched+=len(tender_list)

        for tender in tender_list:
            tender_id=tender.get("tenderprocid")
            if not tender_id or tender_id in processed_ids:
                continue
            processed_ids.add(tender_id)
            tenders.append(mapper.map(tender))

    return {
        "source":"tendertiger",
        "tenders":tenders,
        "keywords":keywords,
        "total_fetched":total_fetched,
        "unique_tenders":len(tenders),
    }