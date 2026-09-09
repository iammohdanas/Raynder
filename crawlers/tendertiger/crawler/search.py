from ast import keyword
import json

class TenderTigerSearch:

    def __init__(self, auth):
        """
        auth = Logged in TenderTigerAuth object
        """
        self.auth = auth
        self.session = auth.session
        self.base_url = auth.BASE_URL
        
    def search(self, keyword, rescount=2):
        """
        Search tenders by keyword.
        """
        payload = {
            "profilequery": "undefined",
            "sub_no": str(self.auth.subscription["SubNo"]),
            "subscribetype": "all",
            "searchkeyword": keyword,
            "seosearchlocation": "search",
            "tabindex": "1",
            "maintabindex": "0",
            "total": "200",
            "loc_type": "",
            "tender_typewise": "live",
            "hdn_status": "0",
            "rescount": str(rescount),
            "categoryflag": "1",
            "orderbytype": "null",
            "querytype": "undefined",
            "last_rescount": "20",
            "isunfilter": "0",
            "sortingScore": "0",
            "maxScore": "1.4653072",
            "agentKeyword": "undefined",
            "excludeKeyword": "undefined",
        }

        response = self.session.post(
            f"{self.base_url}/TenderAI/GetTendersList",
            data=payload,
            headers={
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/",
                "X-Requested-With": "XMLHttpRequest",
            },
        )

        print("Status :", response.status_code)

        data = response.json()

        if isinstance(data, str):
            data = json.dumps(data)
        # data = json.dumps(data, indent=4)
        return data