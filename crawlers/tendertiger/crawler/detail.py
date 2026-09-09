from bs4 import BeautifulSoup


class TenderTigerDetail:

    def __init__(self, auth):
        self.auth = auth
        self.session = auth.session

    def get_detail_page(self, url):
        """
        Downloads the tender detail page.
        """

        response = self.session.get(url)

        print("Detail Status :", response.status_code)

        if response.status_code != 200:
            raise Exception("Unable to fetch tender detail.")

        return response.text
    
    def download_document(
        self,
        file_path,
        tender_no,
        country,
        free_tender,
        whatsapp
    ):
        url = self.BASE_URL + "/TenderDetail/DownloadFile"

        params = {
            "filePath": file_path,
            "hdnTenderNo": tender_no,
            "mode": "",
            "hdncountry": country,
            "hdnfreetender": free_tender,
            "hdnwhatsapp": whatsapp,
        }

        r = self.session.get(url, params=params)

        print(r.status_code)
        print(r.text)

        return r.json()