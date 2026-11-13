#2nd step: PQ Comparison Service: Compare the extracted PQ criteria against the company's credentials to determine qualification status.
import logging

from openai import OpenAI
from pydantic import BaseModel, Field

from Raynder import settings
from ai.services.qualification.company_credentials import COMPANY_CREDENTIALS

logger = logging.getLogger(__name__)


class PQComparisonItem(BaseModel):
    criterion: str
    category: str

    status: str
    tender_requirement: str
    company_evidence: str
    explanation: str

    source_document: str
    page_number: int | None = None
    chunk_id: str
    evidence_quote: str


class PQComparisonResult(BaseModel):
    financial_results: list[PQComparisonItem] = Field(default_factory=list)
    technical_results: list[PQComparisonItem] = Field(default_factory=list)
    other_results: list[PQComparisonItem] = Field(default_factory=list)

    overall_status: str
    summary: str
    critical_gaps: list[str] = Field(default_factory=list)


class PQComparisonService:

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            base_url=(
                f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}"
                "/openai/v1/"
            ),
        )
        self.deployment = settings.AZURE_OPENAI_DEPLOYMENT_NAME

    def compare(self, extraction_result):

        instructions = """
You are a tender pre-qualification comparison assistant.

Compare the tender's extracted PQ criteria against the supplied
company credentials.

For every criterion:
1. Determine whether the company satisfies the requirement.
2. Use only the supplied tender criteria and company credentials.
3. Do not assume missing company information means the requirement
   is satisfied.
4. Do not invent project experience, financial figures or certifications.
5. Explain the comparison clearly.
6. Preserve the tender's original requirement and source references.

Allowed criterion statuses:
- MEETS: Available company evidence clearly satisfies the requirement.
- DOES_NOT_MEET: Available company evidence clearly fails the requirement.
- PARTIALLY_MEETS: Some, but not all, parts of the requirement are met.
- INSUFFICIENT_INFORMATION: Available credentials do not establish
  whether the requirement is met.

Overall status must be one of:
- QUALIFIED: All mandatory criteria are clearly met.
- NOT_QUALIFIED: At least one mandatory criterion clearly fails.
- NEEDS_REVIEW: Information is missing, ambiguous or partially sufficient.

Important:
- Do not mark the company NOT_QUALIFIED merely because information
  is missing.
- Do not assume a criterion is mandatory unless the extracted
  requirement establishes that.
- If mandatory status is unclear, user NEEDS_REVIEW.
- List only material eligibility gaps under critical_gaps.
- This is an AI-assisted assessment, not a legal qualification decision.
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
                        "COMPANY CREDENTIALS:\n"
                        f"{COMPANY_CREDENTIALS}\n\n"
                        "EXTRACTED TENDER PQ CRITERIA:\n"
                        f"{extraction_result}"
                    ),
                },
            ],
            text_format=PQComparisonResult,
        )

        parsed = response.output_parsed

        if parsed is None:
            raise RuntimeError(
                "LLM did not return structured PQ comparison."
            )

        return parsed.model_dump()