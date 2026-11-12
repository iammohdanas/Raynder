from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging

from django.conf import settings
from openai import OpenAI
from pydantic import BaseModel, Field

from api_gateway.models import DocumentChunk, Tender

logger = logging.getLogger(__name__)

# --- Schemas remain the same ---
class SummaryFact(BaseModel):
    section: str
    label: str
    value: str
    source_id: str
    quote: str

class BatchExtraction(BaseModel):
    facts: list[SummaryFact] = Field(default_factory=list)

class SummarySection(BaseModel):
    title: str
    content: str
    source_ids: list[str] = Field(default_factory=list)

class SummaryCitation(BaseModel):
    source_id: str
    document: str
    page: int | None = None
    chunk_id: str
    quote: str

class TenderSummaryOutput(BaseModel):
    executive_summary: str
    tender_overview: list[SummarySection] = Field(default_factory=list)
    scope_of_work: list[SummarySection] = Field(default_factory=list)
    key_dates: list[SummarySection] = Field(default_factory=list)
    financial_details: list[SummarySection] = Field(default_factory=list)
    project_details: list[SummarySection] = Field(default_factory=list)
    eligibility_highlights: list[SummarySection] = Field(default_factory=list)
    important_conditions: list[SummarySection] = Field(default_factory=list)
    important_notes: list[SummarySection] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    citations: list[SummaryCitation] = Field(default_factory=list)


class TenderSummaryService:
    MAX_CHUNKS_PER_BATCH = 30
    MAX_BATCH_CHARS = 40000
    MAX_CONCURRENT_WORKERS = 8  # Parallel requests to Azure OpenAI

    # High-signal tender sections / keywords to prioritize
    HIGH_SIGNAL_KEYWORDS = (
        "emd", "earnest money", "scope of work", "eligibility", "qualification",
        "turnover", "pbg", "performance bank guarantee", "bid submission",
        "completion period", "capacity", "commercial terms", "technical criteria"
    )

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            base_url=f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/v1/",
        )
        self.deployment = settings.AZURE_OPENAI_DEPLOYMENT_NAME

    def get_tender_chunks(self, tender_id):
        chunks = (
            DocumentChunk.objects
            .filter(document__tender__tender_id=tender_id)
            .select_related("document")
            .order_by("document_id", "chunk_index")
        )

        results = []
        source_lookup = {}

        for index, chunk in enumerate(chunks, start=1):
            source_id = f"S{index}"
            document_name = (
                chunk.document.original_filename
                or chunk.document.file.name
                or "Unknown document"
            )

            # --- Cost & Latency Saver: Pre-filtering noise ---
            # If section/content is pure boilerplate, drop it prior to batching
            content = chunk.content or ""
            section_lower = (chunk.section or "").lower()
            content_lower = content.lower()

            # Skip blank or low-density chunks (e.g., signature pages, indices)
            if len(content.strip()) < 50:
                continue

            results.append({
                "source_id": source_id,
                "document": document_name,
                "page": chunk.page_number,
                "chunk_id": str(chunk.id),
                "section": chunk.section or "General",
                "content": content,
            })

            source_lookup[source_id] = {
                "document": document_name,
                "page": chunk.page_number,
                "chunk_id": str(chunk.id),
            }

        return results, source_lookup

    def create_batches(self, chunks):
        batches = []
        current_batch = []
        current_chars = 0

        for chunk in chunks:
            chunk_size = len(chunk["content"])
            if current_batch and (
                len(current_batch) >= self.MAX_CHUNKS_PER_BATCH
                or current_chars + chunk_size > self.MAX_BATCH_CHARS
            ):
                batches.append(current_batch)
                current_batch = []
                current_chars = 0

            current_batch.append(chunk)
            current_chars += chunk_size

        if current_batch:
            batches.append(current_batch)

        return batches

    def extract_batch_facts(self, batch, tender_id):
        source_text = [
            f"[{item['source_id']}] Section: {item['section']} | Page: {item['page']}\n{item['content']}"
            for item in batch
        ]

        system_prompt = (
            "You are Raynder, an expert tender extraction engine. "
            "Extract critical commercial, technical, eligibility, financial (EMD, PBG, turnover), "
            "and milestone facts strictly from the provided passages. "
            "Every fact must include source_id and an exact verbatim quote. Do not assume or extrapolate."
        )

        try:
            response = self.client.beta.chat.completions.parse(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Tender ID: {tender_id}\n\n" + "\n\n---\n\n".join(source_text),
                    },
                ],
                response_format=BatchExtraction,
                temperature=0.0,
            )
            parsed = response.choices[0].message.parsed
            return parsed.facts if parsed else []
        except Exception as e:
            logger.error("Batch extraction failed on tender %s: %s", tender_id, e)
            return []

    def extract_all_batches_parallel(self, batches, tender_id):
        all_facts = []
        # Run batches concurrently using thread pool
        with ThreadPoolExecutor(max_workers=min(self.MAX_CONCURRENT_WORKERS, len(batches) or 1)) as executor:
            future_to_batch = {
                executor.submit(self.extract_batch_facts, batch, tender_id): idx
                for idx, batch in enumerate(batches, start=1)
            }
            for future in as_completed(future_to_batch):
                batch_idx = future_to_batch[future]
                try:
                    facts = future.result()
                    all_facts.extend(facts)
                    logger.info("Tender %s: Batch %d/%d extracted (%d facts)", tender_id, batch_idx, len(batches), len(facts))
                except Exception as exc:
                    logger.error("Tender %s: Batch %d generated an exception: %s", tender_id, batch_idx, exc)

        # Deduplicate facts on (section, label, value)
        unique_facts = []
        seen = set()
        for f in all_facts:
            key = (f.section.lower().strip(), f.label.lower().strip(), f.value.lower().strip())
            if key not in seen:
                seen.add(key)
                unique_facts.append(f)

        return unique_facts

    def generate_final_summary(self, tender, facts, source_lookup):
        if not facts:
            raise ValueError("No factual information extracted from tender chunks.")

        facts_payload = [fact.model_dump() for fact in facts]

        system_prompt = (
            "You are Raynder, a professional tender intelligence assistant. "
            "Synthesize the supplied structured facts into an executive tender summary. "
            "Highlight key dates, commercial eligibility, scope, guarantees, and risks. "
            "Reference valid source_ids and quotes for auditability."
        )

        user_content = (
            f"Tender ID: {tender.tender_id}\n"
            f"Title: {tender.title or 'N/A'}\n"
            f"Issuing Company: {tender.company_name or 'N/A'}\n\n"
            f"Extracted Facts:\n{json.dumps(facts_payload, ensure_ascii=False)}"
        )

        response = self.client.beta.chat.completions.parse(
            model=self.deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format=TenderSummaryOutput,
            temperature=0.1,
        )

        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("Final summary generation returned empty output.")

        result = parsed.model_dump()

        # Validate citations
        valid_citations = []
        supported_pairs = {(f.source_id, f.quote) for f in facts}

        for citation in result.get("citations", []):
            sid = citation.get("source_id")
            source = source_lookup.get(sid)
            if not source:
                continue

            # Ensure quote exists in extracted facts
            if (sid, citation.get("quote")) in supported_pairs:
                valid_citations.append({
                    "source_id": sid,
                    **source,
                    "quote": citation["quote"],
                })

        result["citations"] = valid_citations
        return result

    def generate(self, tender_id):
        tender = Tender.objects.get(tender_id=tender_id)
        chunks, source_lookup = self.get_tender_chunks(tender_id)

        if not chunks:
            raise ValueError("No valid document chunks available for this tender.")

        batches = self.create_batches(chunks)
        logger.info("Starting summary: tender_id=%s | chunks=%d | batches=%d", tender_id, len(chunks), len(batches))

        # Concurrent map stage
        all_facts = self.extract_all_batches_parallel(batches, tender_id)

        # Single synthesis reduce stage
        return self.generate_final_summary(tender, all_facts, source_lookup)