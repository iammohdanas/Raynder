from datetime import datetime
from decimal import Decimal


class TenderTigerMapper:

    @staticmethod
    def parse_date(value):
        if not value:
            return None
        try:
            date = datetime.strptime(value, "%d-%m-%Y").date()
            # TenderTiger sometimes returns this garbage date
            if date.year == 1899:
                return None
            return date
        except (ValueError, TypeError):
            return None

    @staticmethod
    def parse_decimal(value):
        if value in (None, "", "null"):
            return None

        try:
            return Decimal(str(value))
        except (ValueError, TypeError, ArithmeticError):
            return None

    @classmethod
    def map(cls, tender, keyword=None):
        return {
            "source": "tendertiger",
            "source_tender_id": str(
                tender.get("tenderprocid")
                or tender.get("tcno")
            ),
            "tender_ref_no": tender.get("tenderrefno"),
            "tcno": tender.get("tcno"),
            "tenderprocid": tender.get("tenderprocid"),
            "title": (
                tender.get("tendersbriefnew")
                or tender.get("tendersbrief")
            ),
            "description": tender.get("tendersbrief"),
            "company_name": tender.get("companyname"),
            "state": tender.get("statename"),

            "city": tender.get("cityname"),

            "address": tender.get("address"),
            "tender_value": cls.parse_decimal(
                tender.get("tendervalue")
            ),
            "earnest_money": cls.parse_decimal(
                tender.get("earnestmoney")
            ),
            "tender_date": cls.parse_date(
                tender.get("tenderdate")
            ),
            "opening_date": cls.parse_date(
                tender.get("openingdate")
            ),
            "closing_date": cls.parse_date(
                tender.get("closingdate")
            ),
            "description_url": tender.get("descriptionlink"),
            "original_source": tender.get("originalsource"),
            "document_available": (
                tender.get("isdocument") == "1"
            ),
            "raw_data": tender,
        }

    @staticmethod
    def convert_date(date_value):
        return TenderTigerMapper.parse_date(date_value)
    
    

