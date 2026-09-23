from datetime import date
from decimal import Decimal
import hashlib
from urllib.parse import urlparse
from datetime import date
from decimal import Decimal
import re


class AITenderMapper:

    @staticmethod
    def parse_date(value):
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except (ValueError,TypeError):
            return None

    @staticmethod
    def parse_decimal(value):
        if value in (None,"","null"):
            return None
        try:
            return Decimal(str(value))
        except (ValueError,TypeError,ArithmeticError):
            return None

    @staticmethod
    def parse_url(value):
        if not value:
            return None
        value=str(value).strip()
        try:
            parsed=urlparse(value)
            if parsed.scheme in ("http","https") and parsed.netloc:
                return value
        except Exception:
            pass

        return None

    @staticmethod
    def generate_source_tender_id(tender):
        source=(tender.source or "").strip()
        company=(tender.company_name or "").strip()
        ref=(tender.tender_ref_no or "").strip()

        value="|".join([source,company,ref]).lower()
        digest=hashlib.sha256(value.encode()).hexdigest()[:24]

        company_slug=re.sub(r"[^a-zA-Z0-9]+","-",company).strip("-")[:50]

        return f"AI-{company_slug}-{digest}"[:50]

    @classmethod
    def map(cls,tender):
        has_external_id=any([
            tender.source_tender_id,
            tender.tenderprocid,
            tender.tcno,
            tender.tender_ref_no,
        ])

        source_tender_id=(
            tender.source_tender_id
            or tender.tenderprocid
            or tender.tcno
            or tender.tender_ref_no
            or cls.generate_source_tender_id(tender)
        )

        raw_data=tender.raw_data.model_dump()

        raw_data.update({
            "discovery_source":tender.source,
            "generated_source_tender_id":not has_external_id,
            "official_tender_url":tender.official_tender_url,
            "tender_document_url":tender.tender_document_url,
            "live_status":tender.live_status,
            "status_text":tender.status_text,
            "evidence":[e.model_dump() for e in tender.evidence],
        })

        return {
            "source":tender.source or "AI Discovery",
            "source_tender_id":source_tender_id,
            "tender_ref_no":tender.tender_ref_no,
            "tcno":tender.tcno,
            "tenderprocid":tender.tenderprocid,
            "title":tender.title,
            "description":tender.description,
            "company_name":tender.company_name,
            "state":tender.state,
            "city":tender.city,
            "address":tender.address,
            "tender_value":cls.parse_decimal(tender.tender_value),
            "earnest_money":cls.parse_decimal(tender.earnest_money),
            "tender_date":cls.parse_date(tender.tender_date),
            "opening_date":cls.parse_date(tender.opening_date),
            "closing_date":cls.parse_date(tender.closing_date),
            "description_url":cls.parse_url(tender.description_url),
            "original_source":cls.parse_url(tender.original_source),
            "document_available":tender.document_available or False,
            "raw_data":raw_data,
        }