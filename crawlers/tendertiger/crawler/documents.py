from bs4 import BeautifulSoup

class TenderTigerDocuments:

    def __init__(self, auth):
        self.session = auth.session
        self.BASE_URL = auth.BASE_URL

    def get_documents(
        self,
        tc_no,
        tender_proc_id,
        closing_date,
        free_tender=0,
        whatsapp=0,
    ):

        response = self.session.get(
            f"{self.BASE_URL}/TenderDetail/GetTenderDocs",
            params={
                "hdnTcNo": tc_no,
                "hdntenderprocId": tender_proc_id,
                "hdnClosingDate": closing_date,
                "hdnfreetender": free_tender,
                "hdnwhatsapp": whatsapp,
            },
            headers={
                "Referer": f"{self.BASE_URL}/TenderDetail/Tenderinformation",
                "X-Requested-With": "XMLHttpRequest",
            },
        )

        print("Status:", response.status_code)

        return response.text
    
    def parse_documents(self, html):

        soup = BeautifulSoup(html, "html.parser")

        count = int(
            soup.find(id="hdnTenderDocsCount")["value"]
        )

        if count == 0:
            return []

        documents = []

        for link in soup.select("a[href*='filePath=']"):

            documents.append(
                {
                    "name": link.get_text(strip=True),
                    "url": self.BASE_URL + link["href"],
                }
            )

        return documents