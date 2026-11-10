import logging
import re

from openai import OpenAI
from pydantic import BaseModel, Field

from ai.services.documents.document_retrieval_service import DocumentRetrievalService
from Raynder import settings


logger = logging.getLogger(__name__)


class SourceCitation(BaseModel):
    source_id: str
    quote: str


class GroundedAnswer(BaseModel):
    answer: str
    citations: list[SourceCitation] = Field(default_factory=list)
    insufficient_evidence: bool = False


class AnswerGenerationService:
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

    @staticmethod
    def normalize(text):
        """Normalize whitespace and casing for simple phrase matching."""
        return re.sub(r"\s+", " ", text or "").strip().lower()

    def contextualize_question(self, question, conversation_history):
        """Resolve follow-up questions into standalone retrieval queries."""
        if not conversation_history:
            return question

        history_text = "\n".join(
            f"{message['role']}: {message['content']}"
            for message in conversation_history
            if message.get("role") in ("user", "assistant")
            and message.get("content")
        )

        try:
            response = self.client.responses.create(
                model=self.deployment,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "Rewrite the latest user question as a standalone "
                            "search query for retrieving tender-document evidence. "
                            "Use conversation history only to resolve references "
                            "such as 'it', 'that', or 'what about the deadline'. "
                            "Do not answer the question. Do not add facts that "
                            "are not present in the question or history. "
                            "Return only the rewritten query. If no clarification "
                            "is needed, return the original question."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Conversation history:\n{history_text}\n\n"
                            f"Latest question:\n{question}"
                        ),
                    },
                ],
            )
            return response.output_text.strip() or question

        except Exception:
            # Retrieval should still work if query contextualization fails.
            logger.exception("Question contextualization failed")
            return question

    def is_answer_not_found(self, parsed):
        """
        Return True only when the generated response indicates that
        the requested information could not be found or verified.
        """
        if parsed.insufficient_evidence:
            return True

        answer = self.normalize(parsed.answer)

        not_found_phrases = (
            "is not stated in any of the provided passages",
            "is not stated in the provided passages",
            "is not stated in the provided excerpts",
            "not stated in the provided excerpts",
            "not stated in the provided passages",
            "is not mentioned in the provided passages",
            "is not mentioned in the provided excerpts",
            "cannot be determined from these sources",
            "cannot be determined from the provided passages",
            "could not be determined from these sources",
            "indexed documents did not provide enough evidence",
            "did not provide enough evidence to verify this answer",
            "not enough evidence to verify this answer",
            "not enough evidence to answer",
            "could not find relevant evidence",
            "insufficient evidence",
        )

        return any(phrase in answer for phrase in not_found_phrases)

    @staticmethod
    def _build_retrieved_sources(results):
        """Return source metadata in the response format used by the API."""
        return [
            {
                "document": result.get("document"),
                "page": result.get("page"),
                "chunk_id": result.get("chunk_id"),
            }
            for result in results
        ]

    def answer(
        self,
        tender_id,
        question,
        limit=15,
        conversation_history=None,
    ):
        conversation_history = conversation_history or []

        # 1. Resolve follow-up questions before retrieval.
        retrieval_query = self.contextualize_question(
            question,
            conversation_history,
        )

        # 2. Retrieve relevant tender-document chunks once.
        results = self.retrieval.search(
            tender_id=tender_id,
            query=retrieval_query,
            limit=limit,
        )

        logger.info(
            "RAG RETRIEVAL | tender_id=%s | original_question=%r "
            "| retrieval_query=%r | result_count=%d",
            tender_id,
            question,
            retrieval_query,
            len(results),
        )

        for rank, item in enumerate(results, start=1):
            logger.info(
                "RAG RESULT #%d | document=%s | page=%s "
                "| chunk_id=%s | score=%s | text=%r",
                rank,
                item.get("document"),
                item.get("page"),
                item.get("chunk_id"),
                item.get("score"),
                item.get("text", "")[:500],
            )

        # No retrieved chunks means there is nothing useful to retry against.
        if not results:
            return {
                "answer": (
                    "I could not find relevant evidence in this "
                    "tender's indexed documents."
                ),
                "citations": [],
                "insufficient_evidence": True,
                "retrieved_contexts": [],
                "retrieved_sources": [],
            }

        # 3. Prepare labelled source passages for the answer-generation model.
        source_text = []

        source_lookup = {
            f"S{index}": {
                "document": result.get("document"),
                "page": result.get("page"),
                "chunk_id": result.get("chunk_id"),
            }
            for index, result in enumerate(results, start=1)
        }

        for index, result in enumerate(results, start=1):
            source_id = f"S{index}"

            source_text.append(
                f"[{source_id}]\n"
                f"Document: {result.get('document', 'Unknown')}\n"
                f"Page: {result.get('page', 'Unknown')}\n"
                f"Chunk ID: {result.get('chunk_id', 'Unknown')}\n"
                f"Passage:\n{result.get('text', '')}"
            )

        instructions = (
            "You are Raynder, a tender-document assistant. "
            "Answer the user's question using only the supplied source passages. "
            "Do not use outside knowledge or invent facts. "
            "If the sources do not establish the answer, clearly say that the "
            "information was not found in the provided passages and set "
            "insufficient_evidence=true. "
            "Distinguish related clauses that refer to different requirements "
            "or time periods. "
            "Cite supporting sources in the answer using labels such as [S1]. "
            "Return citations only for sources that directly support the answer. "
            "For every citation, provide a short, contiguous, verbatim quote "
            "copied exactly from the supplied passage. Do not use ellipses, "
            "paraphrase, or join separate parts of a passage into one quote. "
            "Do not invent document names, pages, or quotations. "
            "If insufficient_evidence is true, return an empty citations list. "
            "Conversation history may help interpret follow-up questions, "
            "but it is not evidence. Only the supplied source passages may "
            "support factual answers."
        )

        generation_input = [
            {
                "role": "system",
                "content": instructions,
            },
            *[
                {
                    "role": message["role"],
                    "content": message["content"],
                }
                for message in conversation_history
                if message.get("role") in ("user", "assistant")
                and message.get("content")
            ],
            {
                "role": "user",
                "content": (
                    f"Tender ID: {tender_id}\n"
                    f"Current question: {question}\n\n"
                    "Source passages:\n\n"
                    + "\n\n".join(source_text)
                ),
            },
        ]

        # 4. Generate the initial answer.
        response = self.client.responses.parse(
            model=self.deployment,
            input=generation_input,
            text_format=GroundedAnswer,
        )

        parsed = response.output_parsed

        if parsed is None:
            raise RuntimeError(
                "The LLM did not return a structured answer."
            )

        # 5. Retry only when the response indicates that the answer was not found.
        if self.is_answer_not_found(parsed):
            logger.info(
                "ANSWER NOT FOUND - RETRYING ONCE | tender_id=%s | question=%r",
                tender_id,
                question,
            )

            retry_instructions = (
                instructions
                + "\n\n"
                + "RETRY INSTRUCTION: Your previous response indicated that "
                "the requested information was not found. Re-examine every "
                "supplied source passage carefully. Look for the requested "
                "information even if it uses different terminology, an "
                "abbreviation, a related heading, a table, or a financial "
                "section. Do not assume the information is missing merely "
                "because the exact wording of the question is absent. If the "
                "information is present, answer the original question and "
                "cite the supporting passage. If it genuinely cannot be "
                "established from these passages, state that clearly and set "
                "insufficient_evidence=true with an empty citations list."
            )

            retry_input = [
                {
                    "role": "system",
                    "content": retry_instructions,
                },
                *generation_input[1:],
            ]

            try:
                retry_response = self.client.responses.parse(
                    model=self.deployment,
                    input=retry_input,
                    text_format=GroundedAnswer,
                )

                retry_parsed = retry_response.output_parsed

                if retry_parsed is not None:
                    parsed = retry_parsed
                else:
                    logger.warning(
                        "Retry returned no structured answer; "
                        "keeping the initial not-found response. "
                        "tender_id=%s",
                        tender_id,
                    )

            except Exception:
                # Preserve the initial not-found answer if the retry fails.
                logger.exception(
                    "Answer retry failed | tender_id=%s",
                    tender_id,
                )

        # 6. Return the final answer (initial or retry result).
        return {
            "answer": parsed.answer,

            "citations": [
                {
                    "source_id": citation.source_id,
                    "document": source_lookup.get(
                        citation.source_id, {}
                    ).get("document"),
                    "page": source_lookup.get(
                        citation.source_id, {}
                    ).get("page"),
                    "chunk_id": source_lookup.get(
                        citation.source_id, {}
                    ).get("chunk_id"),
                    "quote": citation.quote,
                }
                for citation in parsed.citations
                if citation.source_id in source_lookup
            ],

            "insufficient_evidence": parsed.insufficient_evidence,

            "retrieved_contexts": [
                result.get("text", "") for result in results
            ],

            "retrieved_sources": self._build_retrieved_sources(results),
        }