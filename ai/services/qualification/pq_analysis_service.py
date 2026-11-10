#3rd step: Analyze the extracted criteria and compare them with company credentials.
import logging

from ai.services.qualification.pq_extraction_service import (
    PQExtractionService,
)
from ai.services.qualification.pq_comparison_service import (
    PQComparisonService,
)

logger = logging.getLogger(__name__)


class PQAnalysisService:

    @classmethod
    def analyze(cls, tender_id):

        logger.info(
            "Starting PQ analysis | tender_id=%s",
            tender_id,
        )

        # 1. Extract PQ criteria from tender documents.
        extraction = PQExtractionService().extract(tender_id)

        if extraction.get("insufficient_evidence"):
            return {
                "tender_id": tender_id,
                "status": "INSUFFICIENT_EVIDENCE",
                "extraction": extraction,
                "comparison": None,
            }

        # 2. Compare extracted requirements with company credentials.
        comparison = PQComparisonService().compare(extraction)

        logger.info(
            "PQ analysis completed | tender_id=%s | status=%s",
            tender_id,
            comparison.get("overall_status"),
        )

        return {
            "tender_id": tender_id,
            "status": comparison.get("overall_status"),
            "extraction": extraction,
            "comparison": comparison,
        }
