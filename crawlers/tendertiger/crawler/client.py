from .auth import TenderTigerAuth
from .search import TenderTigerSearch
from .detail import TenderTigerDetail


class TenderTigerClient:

    def __init__(self, auth):
        self.auth = auth

        self.search_service = TenderTigerSearch(auth)
        self.detail_service = TenderTigerDetail(auth)

    def search(self, keyword, rescount=50):
        return self.search_service.search(keyword, rescount)

    def get_detail(self, url):
        return self.detail_service.get_detail_page(url)