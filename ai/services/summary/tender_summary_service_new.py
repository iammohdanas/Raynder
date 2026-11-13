
import json
import logging
import re
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from Raynder import settings

from ai.services.documents.document_retrieval_service import (
    DocumentRetrievalService,
)
from ai.services.summary.summary_keywords import SUMMARY_KEYWORDS


logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# PYDANTIC RESPONSE SCHEMAS
# ---------------------------------------------------------

class SummaryCitation(BaseModel):
    source_id: str
    quote: str


class SummarySectionAnswer(BaseModel):
    sr_no: int
    answer: str
    status: Literal["found", "not_found", "unclear", "conflicting"]
    citations: list[SummaryCitation] = Field(default_factory=list)

class ExecutiveSummaryResponse(BaseModel):
    executive_summary: str

class SummaryBatchResponse(BaseModel):
    sections: list[SummarySectionAnswer] = Field(default_factory=list)

class ExpandedHeadingQuery(BaseModel):
    sr_no: int
    queries: list[str] = Field(default_factory=list)


class QueryExpansionResponse(BaseModel):
    headings: list[ExpandedHeadingQuery] = Field(default_factory=list)

# ---------------------------------------------------------
# TENDER SUMMARY SERVICE
# ---------------------------------------------------------

class TenderSummaryService:

    def __init__(self):

        self.retrieval = DocumentRetrievalService()

        self.client = OpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            base_url=(
                f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}"
                "/openai/v1/"
            ),
        )

        self.deployment = settings.AZURE_OPENAI_DEPLOYMENT_NAME

    # -----------------------------------------------------
    # TEXT NORMALIZATION
    # -----------------------------------------------------

    @staticmethod
    def normalize_text(text):
        return re.sub(r"\s+", " ", text or "").strip()

    # -----------------------------------------------------
    # STEP 1: RETRIEVE EVIDENCE FOR ALL 74 HEADINGS
    # -----------------------------------------------------

    def retrieve_summary_evidence(self, tender_id, limit=8):

        summary_evidence = []

        for item in SUMMARY_KEYWORDS:

            keyword = item["keyword"]

            heading = {
                "sr_no": item["sr_no"],
                "category": item["category"],
                "key_point": item["key_point"],
                "keyword": keyword,
                "chunks": [],
                "status": "pending",
            }

            try:

                results = self.retrieval.search(
                    tender_id=tender_id,
                    query=keyword,
                    limit=limit,
                )

                heading["chunks"] = results or []
                heading["status"] = (
                    "retrieved" if results else "no_evidence"
                )

            except Exception:

                logger.exception(
                    "Retrieval failed for tender=%s, heading=%s",
                    tender_id,
                    keyword,
                )

                heading["status"] = "retrieval_failed"

            summary_evidence.append(heading)

        logger.info(
            "Summary retrieval completed: tender=%s, headings=%s, "
            "with_evidence=%s",
            tender_id,
            len(summary_evidence),
            sum(bool(item["chunks"]) for item in summary_evidence),
        )

        return summary_evidence

    def generate_alternative_queries(self, headings):
        """
        Generate alternative search queries for tender headings
        where the initial retrieval did not find sufficient evidence.
        """

        if not headings:
            return {}

        heading_payload = [
            {
                "sr_no": item["sr_no"],
                "category": item.get("category"),
                "key_point": item.get("key_point"),
                "keyword": item["keyword"],
            }
            for item in headings
        ]

        system_prompt = """
    You are an expert in Indian government and renewable energy
    tender documents.

    Your task is to generate alternative semantic search queries
    for the given tender headings.

    Instructions:

    1. Generate 3 to 5 alternative queries for each heading.
    2. Preserve the exact meaning of the original heading.
    3. Use relevant synonyms and alternative terminology.
    4. Consider terminology commonly used in RFP, RfS, NIT,
    PPA and government tender documents.
    5. Include relevant abbreviations where appropriate.
    6. Do not generate answers.
    7. Do not invent tender-specific values or requirements.
    8. Do not change or combine heading meanings.
    9. Avoid repeating the original keyword exactly.
    10. Return the original sr_no for every heading.
    """

        user_prompt = (
            "Generate alternative search queries for these headings:\n\n"
            + json.dumps(heading_payload, ensure_ascii=False)
        )

        response = self.client.responses.parse(
            model=self.deployment,
            input=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            text_format=QueryExpansionResponse,
        )

        parsed = response.output_parsed

        if parsed is None:
            raise RuntimeError(
                "AI query expansion returned an empty response."
            )

        expanded_queries = {}

        for item in parsed.headings:

            # Accept only heading IDs that were actually requested.
            if item.sr_no not in {
                heading["sr_no"] for heading in headings
            }:
                continue

            # Remove empty and duplicate queries.
            queries = list(dict.fromkeys(
                query.strip()
                for query in item.queries
                if query and query.strip()
            ))

            # Limit the number of queries per heading.
            expanded_queries[item.sr_no] = queries[:5]

        return expanded_queries


    def retry_heading_retrieval(
        self,
        tender_id,
        heading,
        alternative_queries,
        limit=8,
    ):
        """
        Retry retrieval using alternative queries and merge
        the results with the original heading evidence.
        """

        if not alternative_queries:
            return heading

        # Keep existing chunks.
        chunks_by_id = {
            chunk["chunk_id"]: chunk
            for chunk in heading.get("chunks", [])
            if chunk.get("chunk_id") is not None
        }

        for query in alternative_queries:

            try:

                results = self.retrieval.search(
                    tender_id=tender_id,
                    query=query,
                    limit=limit,
                )

                for chunk in results or []:

                    chunk_id = chunk.get("chunk_id")

                    if chunk_id is None:
                        continue

                    # Avoid adding the same chunk multiple times.
                    chunks_by_id[chunk_id] = chunk

            except Exception:

                logger.exception(
                    "Alternative retrieval failed | tender=%s | "
                    "heading=%s | query=%s",
                    tender_id,
                    heading["sr_no"],
                    query,
                )

        # Update the original heading evidence.
        heading["chunks"] = list(chunks_by_id.values())

        heading["status"] = (
            "retrieved" if heading["chunks"] else "no_evidence"
        )

        logger.info(
            "Retry retrieval completed | tender=%s | heading=%s | "
            "total_chunks=%s",
            tender_id,
            heading["sr_no"],
            len(heading["chunks"]),
        )

        return heading
    # -----------------------------------------------------
    # STEP 2: PREPARE HEADING-SPECIFIC EVIDENCE
    # -----------------------------------------------------

    def _prepare_batch(self, batch):

        source_lookup = {}
        allowed_sources = {}
        batch_payload = []

        for heading in batch:

            sr_no = heading["sr_no"]
            heading_sources = []
            heading_evidence = []

            for index, chunk in enumerate(
                heading.get("chunks", []),
                start=1,
            ):

                source_id = f"H{sr_no}_S{index}"

                source_text = chunk.get("text", "")

                if not source_text:
                    continue

                source_lookup[source_id] = chunk
                heading_sources.append(source_id)

                heading_evidence.append({
                    "source_id": source_id,
                    "document": chunk.get("document"),
                    "page": chunk.get("page"),
                    "text": source_text,
                })

            allowed_sources[sr_no] = heading_sources

            batch_payload.append({
                "sr_no": sr_no,
                "category": heading.get("category"),
                "key_point": heading.get("key_point"),
                "keyword": heading["keyword"],
                "allowed_source_ids": heading_sources,
                "evidence": heading_evidence,
            })

        return batch_payload, source_lookup, allowed_sources

    # -----------------------------------------------------
    # STEP 3: GPT BATCH GENERATION
    # -----------------------------------------------------

    def _generate_single_batch(
        self,
        batch,
    ):

        (
            batch_payload,
            source_lookup,
            allowed_sources,
        ) = self._prepare_batch(batch)

        system_prompt = """
You are Raynder, an expert tender document analysis assistant.

Generate independent answers for the supplied tender summary headings.

STRICT INSTRUCTIONS:

1. Answer every heading independently using its sr_no.
2. Never combine multiple headings into one answer.
3. Use only the evidence provided for that specific heading.
4. Never use evidence belonging to another heading.
5. Do not use external knowledge or assumptions.
6. Never invent dates, amounts, capacities, names, percentages,
   contractual conditions or other information.
7. Preserve important numbers, units, deadlines and conditions.
8. If no relevant evidence is available, use status 'not_found'.
9. If evidence is incomplete or ambiguous, use status 'unclear'.
10. If source documents contradict each other, use status 'conflicting'.
11. Use status 'found' only when the evidence supports the answer.
12. Every factual answer must have supporting citations.
13. A citation source_id must belong to the current heading's
    allowed_source_ids.
14. Quotes must be short, exact and contiguous excerpts from
    the corresponding source passage.
15. Never fabricate a citation, source ID or quotation.
16. Return exactly one section for each requested sr_no.

Answer style:
- Concise but informative.
- Suitable for a tender evaluation and bid team.
- Mention all relevant values and conditions.
- Do not omit important qualifications or exceptions.
- Do not write generic explanations when the document does
  not contain the required information.
"""

        user_prompt = (
            "Generate independent answers for these tender headings.\n"
            "Each heading has its own evidence. Do not mix evidence.\n\n"
            + json.dumps(batch_payload, ensure_ascii=False)
        )

        response = self.client.responses.parse(
            model=self.deployment,
            input=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            text_format=SummaryBatchResponse,
        )

        parsed = response.output_parsed

        if parsed is None:
            raise RuntimeError(
                "GPT returned an empty structured response."
            )

        expected_ids = {
            heading["sr_no"] for heading in batch
        }

        answers_by_id = {}

        for section in parsed.sections:

            sr_no = section.sr_no

            # Ignore unexpected and duplicate heading IDs.
            if sr_no not in expected_ids:
                logger.warning(
                    "GPT returned unexpected heading ID: %s",
                    sr_no,
                )
                continue

            if sr_no in answers_by_id:
                logger.warning(
                    "GPT returned duplicate heading ID: %s",
                    sr_no,
                )
                continue

            valid_citations = []

            for citation in section.citations:

                source_id = citation.source_id

                # Citation must belong to this heading.
                if source_id not in allowed_sources.get(sr_no, []):
                    continue

                source_chunk = source_lookup[source_id]

                source_text = self.normalize_text(
                    source_chunk.get("text", "")
                )

                quote = self.normalize_text(citation.quote)

                # Verify the quotation against its source.
                if not quote or quote not in source_text:
                    logger.warning(
                        "Invalid citation quote for heading=%s, "
                        "source=%s",
                        sr_no,
                        source_id,
                    )
                    continue

                valid_citations.append({
                    "source_id": source_id,
                    "document": source_chunk.get("document"),
                    "page": source_chunk.get("page"),
                    "chunk_id": source_chunk.get("chunk_id"),
                    "quote": citation.quote,
                })

            answer = section.answer.strip()
            status = section.status

            # A factual answer without a verified citation
            # cannot be accepted as a supported answer.
            if status == "found" and not valid_citations:

                answer = (
                    "Insufficient verified evidence found "
                    "in the tender documents."
                )

                status = "not_found"

            answers_by_id[sr_no] = {
                "sr_no": sr_no,
                "answer": answer,
                "status": status,
                "citations": valid_citations,
            }

        # Ensure every requested heading gets a result.
        for heading in batch:

            sr_no = heading["sr_no"]

            if sr_no not in answers_by_id:

                answers_by_id[sr_no] = {
                    "sr_no": sr_no,
                    "answer": (
                        "No reliable answer could be generated."
                    ),
                    "status": "unclear",
                    "citations": [],
                }

        return answers_by_id

    # -----------------------------------------------------
    # STEP 4: GENERATE ALL ANSWERS IN BATCHES
    # -----------------------------------------------------

    def generate_batch_answers(
        self,
        evidence,
        batch_size=8,
    ):

        if batch_size < 1:
            raise ValueError("batch_size must be at least 1.")

        answers_by_id = {}

        # Headings without evidence do not need GPT calls.
        valid_evidence = []

        for heading in evidence:

            if heading.get("chunks"):

                valid_evidence.append(heading)

            else:

                answers_by_id[heading["sr_no"]] = {
                    "sr_no": heading["sr_no"],
                    "answer": (
                        "No relevant evidence found in the "
                        "indexed tender documents."
                    ),
                    "status": "not_found",
                    "citations": [],
                }

        # Process only headings with retrieved evidence.
        for start in range(0, len(valid_evidence), batch_size):

            batch = valid_evidence[start:start + batch_size]

            batch_start_sr = batch[0]["sr_no"]

            try:

                batch_answers = self._generate_single_batch(batch)

                # Commit the batch only after successful completion.
                answers_by_id.update(batch_answers)

                logger.info(
                    "Summary batch completed: tender headings %s-%s",
                    batch[0]["sr_no"],
                    batch[-1]["sr_no"],
                )

            except Exception:

                logger.exception(
                    "Summary batch generation failed. "
                    "Starting heading=%s",
                    batch_start_sr,
                )

                # Preserve every heading if this batch fails.
                for heading in batch:

                    sr_no = heading["sr_no"]

                    answers_by_id[sr_no] = {
                        "sr_no": sr_no,
                        "answer": (
                            "Summary generation failed for this section."
                        ),
                        "status": "unclear",
                        "citations": [],
                    }

        # Return answers in the original hardcoded order.
        final_answers = []

        for item in SUMMARY_KEYWORDS:

            sr_no = item["sr_no"]

            final_answers.append(
                answers_by_id.get(
                    sr_no,
                    {
                        "sr_no": sr_no,
                        "answer": "No answer generated.",
                        "status": "unclear",
                        "citations": [],
                    },
                )
            )

        return final_answers

    
    

    def generate_summary(self, tender_id, retrieval_limit=8, batch_size=8,):
        """
        Generate one independent, evidence-grounded summary
        for every entry in SUMMARY_KEYWORDS.

        Headings are taken directly from SUMMARY_KEYWORDS.
        The LLM is responsible only for generating summary content,
        status, and citations.
        """

        logger.info(
            "Starting tender summary generation: tender_id=%s",
            tender_id,
        )

        # STEP 1: Initial retrieval for all 74 headings.
        evidence = self.retrieve_summary_evidence(
            tender_id=tender_id,
            limit=retrieval_limit,
        )


        # STEP 2: Identify headings where no chunks were retrieved.
        missing_evidence = [
            item
            for item in evidence
            if not item["chunks"]
        ]


        # STEP 3: Generate alternative queries using AI.
        if missing_evidence:

            logger.info(
                "Generating alternative queries for %s headings",
                len(missing_evidence),
            )

            try:

                alternative_queries = self.generate_alternative_queries(
                    missing_evidence
                )

                # Retry retrieval for each heading.
                for heading in missing_evidence:

                    queries = alternative_queries.get(
                        heading["sr_no"],
                        [],
                    )

                    self.retry_heading_retrieval(
                        tender_id=tender_id,
                        heading=heading,
                        alternative_queries=queries,
                        limit=retrieval_limit,
                    )

            except Exception:

                logger.exception(
                    "AI query expansion failed for tender=%s",
                    tender_id,
                )


        # STEP 4: Generate answers using initial + retry evidence.
        answers = self.generate_batch_answers(
            evidence=evidence,
            batch_size=batch_size,
        )
        # STEP 5: Find headings that still need better evidence.
        answers_by_id = {
            item["sr_no"]: item
            for item in answers
        }

        evidence_by_id = {
            item["sr_no"]: item
            for item in evidence
        }

        unresolved_headings = [
            evidence_by_id[item["sr_no"]]
            for item in answers
            if (
                item["status"] in ("not_found", "unclear")
                and evidence_by_id[item["sr_no"]].get("chunks")
            )
        ]


        # STEP 6: Expand queries and retry unresolved headings.
        if unresolved_headings:

            logger.info(
                "Retrying retrieval for %s unresolved headings",
                len(unresolved_headings),
            )

            try:

                alternative_queries = self.generate_alternative_queries(
                    unresolved_headings
                )

                for heading in unresolved_headings:

                    queries = alternative_queries.get(
                        heading["sr_no"],
                        [],
                    )

                    self.retry_heading_retrieval(
                        tender_id=tender_id,
                        heading=heading,
                        alternative_queries=queries,
                        limit=retrieval_limit,
                    )

                # Only regenerate answers for unresolved headings.
                retry_answers = self.generate_batch_answers(
                    evidence=unresolved_headings,
                    batch_size=batch_size,
                )

                # Replace only the answers that were retried.
                retry_ids = {
                    item["sr_no"]
                    for item in unresolved_headings
                }

                for item in retry_answers:

                    sr_no = item["sr_no"]

                    if sr_no in retry_ids:
                        answers_by_id[sr_no] = item

                # Rebuild the answer list in the original order.
                answers = [
                    answers_by_id[item["sr_no"]]
                    for item in SUMMARY_KEYWORDS
                ]

            except Exception:

                logger.exception(
                    "Second retrieval retry failed for tender=%s",
                    tender_id,
                )

        # Create lookup dictionaries using sr_no.
        answers_lookup = {
            item["sr_no"]: item
            for item in answers
        }

        evidence_lookup = {
            item["sr_no"]: item
            for item in evidence
        }

        # STEP 3: Build sections using the original keywords.
        sections = []

        for item in SUMMARY_KEYWORDS:
            sr_no = item["sr_no"]

            # Never allow the LLM to modify the heading.
            heading = item["keyword"]

            generated = answers_lookup.get(sr_no, {})
            retrieved = evidence_lookup.get(sr_no, {})

            sections.append({
                "sr_no": sr_no,

                # Exact heading from summary_keywords.py.
                "heading": heading,

                # Original metadata from summary_keywords.py.
                "category": item.get("category"),
                "key_point": item.get("key_point"),

                # LLM-generated content.
                "summary": generated.get("answer") or (
                    "No relevant information found in the tender documents."
                ),

                "status": generated.get("status", "unclear"),

                "retrieval_status": retrieved.get(
                    "status",
                    "not_processed",
                ),

                "citations": generated.get("citations", []),
            })

        # STEP 4: Validate section count and ordering.
        expected_count = len(SUMMARY_KEYWORDS)

        if len(sections) != expected_count:
            raise ValueError(
                f"Expected {expected_count} summary sections, "
                f"but generated {len(sections)}."
            )

        expected_sr_nos = [
            item["sr_no"] for item in SUMMARY_KEYWORDS
        ]

        actual_sr_nos = [
            section["sr_no"] for section in sections
        ]

        if actual_sr_nos != expected_sr_nos:
            raise ValueError(
                "Summary sections are missing or incorrectly ordered."
            )

        # STEP 5: Calculate summary statistics.
        valid_statuses = (
            "found",
            "not_found",
            "unclear",
            "conflicting",
        )

        statistics = {
            status: sum(
                1
                for section in sections
                if section["status"] == status
            )
            for status in valid_statuses
        }
        executive_summary = self.generate_executive_summary(
            sections=sections
        )

        # STEP 6: Construct final response.
        result = {
            "tender_id": str(tender_id),
            "total_sections": expected_count,
            "statistics": statistics,
            "sections": sections,
            "executive_summary": executive_summary,
        }

        logger.info(
            "Tender summary completed | tender_id=%s | "
            "total_sections=%s | statistics=%s",
            tender_id,
            expected_count,
            statistics,
        )

        return result

        
    def generate_executive_summary(self, sections):
        """
        Generate a short overall tender summary using the
        already-generated individual section answers.
        """
        # Only use sections with meaningful information.
        relevant_sections = [
            {
                "sr_no": section["sr_no"],
                "heading": section["heading"],
                "summary": section["summary"],
                "status": section["status"],
            }
            for section in sections
            if section["status"] in ("found", "conflicting", "unclear")
            and section.get("summary")
        ]

        if not relevant_sections:
            return (
                "The available tender documents did not provide "
                "sufficient verified information to generate an "
                "overall executive summary."
            )

        system_prompt = """
                You are a senior tender analyst preparing an executive summary
                for a company's bidding and management team.

                Generate one concise paragraph summarizing the overall tender.

                Instructions:

                1. Keep the summary between 80 and 100 words.
                2. Write only one paragraph.
                3. Summarize the overall tender opportunity.
                4. Prioritize important information such as:
                - Project scope and nature of work
                - Project capacity or major specifications
                - Procuring authority
                - Financial requirements and EMD
                - Eligibility requirements
                - Important deadlines
                - Major contractual conditions and risks
                5. Include only information available in the supplied summaries.
                6. Do not invent missing values, dates, capacities or conditions.
                7. Do not list all 74 headings individually.
                8. Do not repeat the same information.
                9. If important information is unavailable, do not assume it.
                10. Write in professional, clear business English.
                11. Do not include a heading or bullet points.
                12. Return only the executive_summary field.
                """

        user_prompt = (
            "Prepare a concise executive summary from these "
            "individual tender analysis results:\n\n"
            + json.dumps(relevant_sections, ensure_ascii=False)
        )

        try:

            response = self.client.responses.parse(
                model=self.deployment,
                input=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ],
                text_format=ExecutiveSummaryResponse,
            )

            parsed = response.output_parsed

            if parsed is None or not parsed.executive_summary.strip():
                raise RuntimeError(
                    "Executive summary generation returned an empty response."
                )

            return parsed.executive_summary.strip()

        except Exception:

            logger.exception(
                "Executive summary generation failed."
            )

            return (
                "The individual tender analysis is available below. "
                "An overall executive summary could not be generated."
            )

