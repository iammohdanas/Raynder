#1st step: Retrieve relevant document passages using the DocumentRetrievalService.
import logging

from openai import OpenAI
from pydantic import BaseModel, Field

from Raynder import settings
from ai.services.documents.document_retrieval_service import (
    DocumentRetrievalService,
)

logger = logging.getLogger(__name__)


class PQCriterion(BaseModel):
    criterion: str
    requirement: str

    operator: str | None = None
    required_value: float | None = None
    unit: str | None = None
    currency: str | None = None
    financial_years: int | None = None
    completion_status: str | None = None

    source_document: str
    page_number: int | None = None
    chunk_id: str
    evidence_quote: str


class PQExtractionResult(BaseModel):
    financial_criteria: list[PQCriterion] = Field(default_factory=list)
    technical_criteria: list[PQCriterion] = Field(default_factory=list)
    other_criteria: list[PQCriterion] = Field(default_factory=list)


class PQExtractionService:

    RETRIEVAL_QUERIES = [
        "Minimum average annual turnover, annual turnover and financial eligibility criteria",
        "Net worth, net profit, working capital and financial capability requirements",
        "Similar work experience, completed projects, project capacity and contract value requirements",
        "Technical eligibility, EPC experience, project execution and technical qualification criteria",
        "Bidder eligibility, certifications, consortium, joint venture and other prequalification requirements",
    ]

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            base_url=(
                f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}"
                "/openai/v1/"
            ),
        )

        self.deployment = settings.AZURE_OPENAI_DEPLOYMENT_NAME
        self.retrieval = DocumentRetrievalService()

    def retrieve_pq_contexts(self, tender_id):

        unique_chunks = {}

        for query in self.RETRIEVAL_QUERIES:
            results = self.retrieval.search(
                tender_id=tender_id,
                query=query,
                limit=8,
            )

            for result in results:
                chunk_id = result.get("chunk_id")

                if not chunk_id:
                    continue

                existing = unique_chunks.get(chunk_id)

                current_score = result.get(
                    "rerank_score",
                    result.get("score", 0),
                )

                existing_score = (
                    existing.get("rerank_score", existing.get("score", 0))
                    if existing else -1
                )

                if existing is None or current_score > existing_score:
                    unique_chunks[chunk_id] = result

        return list(unique_chunks.values())

    def extract(self, tender_id):

        contexts = self.retrieve_pq_contexts(tender_id)

        if not contexts:
            return {
                "tender_id": tender_id,
                "financial_criteria": [],
                "technical_criteria": [],
                "other_criteria": [],
                "insufficient_evidence": True,
            }

        source_passages = []

        for index, item in enumerate(contexts, start=1):
            source_passages.append(
                f"[S{index}]\n"
                f"Document: {item.get('document')}\n"
                f"Page: {item.get('page')}\n"
                f"Chunk ID: {item.get('chunk_id')}\n"
                f"Passage:\n{item.get('text')}"
            )

        instructions = """
You are a tender pre-qualification (PQ) criteria extraction assistant.

Extract all explicitly stated bidder eligibility and pre-qualification
requirements from the supplied tender-document passages.

Classify requirements into:
1. Financial criteria
2. Technical criteria
3. Other criteria

Financial criteria may include turnover, net worth, profitability,
working capital and financial capability.

Technical criteria may include similar work experience, project capacity,
completed projects, contract value and execution experience.

Other criteria may include certifications, bidder eligibility,
consortium/JV conditions and other qualification requirements.

Rules:
- Use only the supplied passages.
- Do not invent or assume any requirement.
- Preserve the actual requirement and its conditions.
- Extract numeric values wherever explicitly available.
- Use null for fields that are not explicitly stated.
- Do not confuse EMD, tender fees or bid security with PQ eligibility.
- Do not treat general tender information as a qualification criterion.
- Every extracted criterion must have a supporting source.
- evidence_quote must be a short, contiguous, verbatim quote.
- Preserve the exact document name, page number and chunk ID.
- Do not combine separate requirements into one criterion.
- Do not omit conditions such as financial years or completion status.
"""

        response = self.client.responses.parse(
            model=self.deployment,
            input=[
                {
                    "role": "system",
                    "content": instructions,
                },
                {
                    "role": "user",
                    "content": (
                        f"Tender ID: {tender_id}\n\n"
                        "Tender document passages:\n\n"
                        + "\n\n".join(source_passages)
                    ),
                },
            ],
            text_format=PQExtractionResult,
        )

        parsed = response.output_parsed

        if parsed is None:
            raise RuntimeError(
                "LLM did not return structured PQ extraction."
            )

        result = parsed.model_dump()

        return {
            "tender_id": tender_id,
            **result,
            "insufficient_evidence": not any(
                result.get(key)
                for key in (
                    "financial_criteria",
                    "technical_criteria",
                    "other_criteria",
                )
            ),
        }
