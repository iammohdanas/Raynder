class TenderParser:

    IMPORTANT_FIELDS = {
        "tenderrefno",
        "tcno",
        "tenderprocid",
        "tendersbriefnew",
        "companyname",
        "countryname",
        "statename",
        "cityname",
        "subindustryname",
        "keywordname",
        "publicationdate",
        "openingdate",
        "closingdate",
        "earnestmoney",
        "quantity",
        "tendervalue",
        "descriptionlink",
        "isdocument",
        "isgem",
        "scorePercentage",
        "tendersbrief",
        "tenderdate"
    }

    @staticmethod
    def parse(tender: dict):

        metadata = {}

        for key, value in tender.items():
            if key not in TenderParser.IMPORTANT_FIELDS:
                metadata[key] = value

        return {
            "reference_no": tender.get("tenderrefno"),
            "tc_no": tender.get("tcno"),
            "tender_id": tender.get("tenderprocid"),
            "title": tender.get("tendersbriefnew"),
            "company": tender.get("companyname"),
            "country": tender.get("countryname"),
            "state": tender.get("statename"),
            "city": tender.get("cityname"),
            "industry": tender.get("subindustryname"),
            "keywords": tender.get("keywordname"),
            "published_date": tender.get("publicationdate"),
            "opening_date": tender.get("openingdate"),
            "closing_date": tender.get("closingdate"),
            "emd": tender.get("earnestmoney"),
            "quantity": tender.get("quantity"),
            "tender_value": tender.get("tendervalue"),
            "description_url": tender.get("descriptionlink"),
            "is_document": tender.get("isdocument") == "1",
            "is_gem": tender.get("isgem") == "1",
            "score": tender.get("scorePercentage"),
            "metadata": metadata,
        }