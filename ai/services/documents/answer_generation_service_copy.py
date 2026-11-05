
import os
import re
from openai import OpenAI
from pydantic import BaseModel
from ai.services.documents.document_retrieval_service import DocumentRetrievalService
from Raynder import settings
from Raynder.settings import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_DEPLOYMENT_NAME,
    BASE_DIR,
)
import logging
import re
from decimal import Decimal, InvalidOperation
logger = logging.getLogger(__name__)

class SourceCitation(BaseModel):
    source_id: str
    quote: str


class GroundedAnswer(BaseModel):
    answer: str
    citations: list[SourceCitation]
    insufficient_evidence: bool

class SemanticValidation(BaseModel):
    passed: bool
    unsupported_claims: list[str]
    contradictions: list[str]
    missing_information: list[str]
    explanation: str

class AnswerGenerationService:
    def __init__(self):
        self.client=OpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            base_url=(
                f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}"
                "/openai/v1/"
            )
        )
        self.deployment=settings.AZURE_OPENAI_DEPLOYMENT_NAME
        self.retrieval=DocumentRetrievalService()

    

    @staticmethod
    def normalize(text):
        return re.sub(r"\s+"," ",text).strip().lower()

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
            return question


    def answer(self,tender_id,question,limit=5, conversation_history=None,):
        conversation_history = conversation_history or []
        retrieval_query = self.contextualize_question(question, conversation_history,)
        results=self.retrieval.search(
            tender_id=tender_id,
            query=retrieval_query,
            limit=limit
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
                
        if not results:
            return {
                "answer": (
                    "I could not find relevant evidence in this "
                    "tender's indexed documents."
                ),
                "citations": [],
                "insufficient_evidence": True,
                "citation_debug": [],
                "citation_validation": {
                    "passed": True
                },
                "numerical_validation": {
                    "passed": True,
                    "unsupported_numbers": [],
                },
                "retrieved_contexts": [],
                "retrieved_sources": [],
            }


        sources={}
        source_text=[]

        for index,result in enumerate(results,1):
            source_id=f"S{index}"
            sources[source_id]=result
            source_text.append(
                f"[{source_id}]\n"
                f"Document: {result['document']}\n"
                f"Page: {result['page']}\n"
                f"Chunk ID: {result['chunk_id']}\n"
                f"Passage:\n{result['text']}"
            )

        instructions=(
            "You are Raynder, a tender-document assistant. "
            "Answer the user's question using only the supplied source passages. "
            "Do not use outside knowledge or invent facts. "
            "If the sources do not establish the answer, say so and set "
            "insufficient_evidence=true. Distinguish related clauses that "
            "refer to different requirements or time periods. "
            "Cite supporting sources in the answer using labels such as [S1]. "
            "Return citations only for sources that directly support the answer. "
            "For every citation, provide a short, contiguous, verbatim quote "
            "copied exactly from the supplied passage. Do not use ellipses, "
            "paraphrase, or join separate parts of a passage into one quote. "
            "Do not invent document names, pages, or quotations."
            " If insufficient_evidence is true, return an empty citations list. "
            "Do not cite passages that merely discuss a related topic but do not "
            "establish the requested fact. "
            "Use conversation history to interpret follow-up questions. "
            "Conversation history is context, not evidence. "
            "Only the supplied source passages may support factual answers. "
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
                    f"Source passages:\n\n" + "\n\n".join(source_text)
                ),
            },
        ]
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
        
        # STEP 1: Validate the first generated answer.
        validation = self.validate_generated_answer(parsed=parsed, question=question, sources=sources, results=results,)
        # STEP 2: Retry once if any validation fails.
        if not validation["passed"]:
            logger.warning(
                "RAG VALIDATION FAILED | tender_id=%s | "
                "citation=%s | numerical=%s | semantic=%s",
                tender_id,
                validation["citation_validation"],
                validation["numerical_validation"],
                validation["semantic_validation"],
            )
            retry_feedback = f"""
            Your previous answer failed factual validation.
            Generate a corrected answer using ONLY the supplied source passages.
            Previous validation results:
            Citation validation:
            {validation["citation_validation"]}
            Numerical validation:
            {validation["numerical_validation"]}
            Semantic validation:
            {validation["semantic_validation"]}
            Instructions:
            - Correct all unsupported claims.
            - Correct incorrect numerical associations.
            - Use only facts explicitly supported by the passages.
            - Include valid source citations with exact quotations.
            - If the evidence is insufficient, explicitly say so and set
            insufficient_evidence=true with an empty citations list.
            - Do not guess or invent missing information.
            """

            retry_input = [
                {   "role": "system",
                    "content": instructions + "\n\n" + retry_feedback,
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

                    retry_validation = self.validate_generated_answer(
                        parsed=retry_parsed,
                        question=question,
                        sources=sources,
                        results=results,
                    )

                    # Replace the original answer with the retry answer.
                    parsed = retry_parsed
                    validation = retry_validation

            except Exception:
                logger.exception(
                    "RAG answer retry failed | tender_id=%s",
                    tender_id,
                )

        # STEP 3: Final validation gate.
        if not validation["passed"]:
            logger.warning("RAG FINAL VALIDATION FAILED | tender_id=%s", tender_id,)
            return {
                "answer": (
                    "I could not confidently verify the answer against "
                    "the available tender documents. Please refer to the "
                    "original tender document for confirmation."
                ),
                "citations": [],
                "insufficient_evidence": True,
                "citation_debug": validation["citation_debug"],
                "citation_validation": validation["citation_validation"],
                "numerical_validation": validation["numerical_validation"],
                "semantic_validation": validation["semantic_validation"],
                "retrieved_contexts": [
                    result["text"] for result in results
                ],
                "retrieved_sources": [
                    {
                        "document": result["document"],
                        "page": result["page"],
                        "chunk_id": result["chunk_id"],
                    }
                    for result in results
                ],
            }
        # STEP 4: Return the validated answer.
        return {
            "answer": parsed.answer,
            "citations": (
                [] if parsed.insufficient_evidence
                else validation["citations"]
            ),
            "insufficient_evidence": parsed.insufficient_evidence,
            "citation_debug": validation["citation_debug"],
            "citation_validation": validation["citation_validation"],
            "numerical_validation": validation["numerical_validation"],
            "semantic_validation": validation["semantic_validation"],
            "retrieved_contexts": [
                result["text"] for result in results
            ],
            "retrieved_sources": [
                {
                    "document": result["document"],
                    "page": result["page"],
                    "chunk_id": result["chunk_id"],
                }
                for result in results
            ],
        }

    def validate_citations(self, parsed_citations, sources, insufficient_evidence=False):
        """
        Validate citations against retrieved source passages.
        Returns:
            {
                "passed": bool,
                "citations": list,
                "debug": list
            }
        """
        # An insufficient-evidence response does not require citations.
        if insufficient_evidence:
            return {
                "passed": not bool(parsed_citations),
                "citations": [],
                "debug": [],
            }
        valid_citations = []
        citation_debug = []
        source_map = sources

        for citation in parsed_citations:
            source_id = citation.source_id
            quote = citation.quote
            if source_id not in source_map:
                citation_debug.append({
                    "source_id": source_id,
                    "reason": "unknown_source_id",
                })
                continue
            if not quote or not quote.strip():
                citation_debug.append({
                    "source_id": source_id,
                    "reason": "empty_quote",
                })
                continue
            source_text = source_map[source_id]["text"]
            if self.normalize(quote) not in self.normalize(source_text):
                citation_debug.append({
                    "source_id": source_id,
                    "reason": "quote_not_found_in_source",
                })
                continue

            valid_citations.append({
                "source_id": source_id,
                "quote": quote,
            })
        passed = (
            bool(parsed_citations)
            and len(valid_citations) == len(parsed_citations)
        )
        if not parsed_citations:
            citation_debug.append({
                "reason": "missing_citations",
            })
        return {
            "passed": passed,
            "citations": valid_citations,
            "debug": citation_debug,
        }


    def extract_numbers(self, text):
        """
        Extract numeric values, including Indian and international
        comma-separated formats and decimals.
        """
        pattern = r"(?<![A-Za-z0-9.])\d[\d,]*(?:\.\d+)?(?![A-Za-z0-9.])"
        matches = re.findall(pattern, text)
        numbers = []
        for value in matches:
            try:
                numbers.append(
                    Decimal(value.replace(",", ""))
                )
            except InvalidOperation:
                continue
        return numbers


    def validate_numerical_consistency(self, answer, retrieved_contexts):
        """
        Check whether numeric values in the answer appear in the
        retrieved source contexts.
        """
        answer_numbers = self.extract_numbers(answer)
        context_numbers = set()
        for context in retrieved_contexts:
            context_numbers.update(self.extract_numbers(context))
        unsupported_numbers = [
            str(number)
            for number in answer_numbers
            if number not in context_numbers
        ]
        return {
            "passed": len(unsupported_numbers) == 0,
            "unsupported_numbers": unsupported_numbers,
        }

    def validate_semantically(self, question, answer, retrieved_contexts):
        """
        Validate whether the generated answer is supported by
        the retrieved tender-document passages.
        """
        if not retrieved_contexts:
            return {
                "passed": False,
                "unsupported_claims": [],
                "contradictions": [],
                "missing_information": [],
                "explanation": "No supporting source passages available.",
            }

        context_text = "\n\n".join(
            f"[SOURCE {index}]\n{context}"
            for index, context in enumerate(retrieved_contexts, 1)
        )

        instructions = """
        You are a strict factual validator for a tender-document RAG system.

        Evaluate the generated answer using ONLY the supplied source passages.

        Check the following:

        1. Are all factual claims supported by the passages?
        2. Does the answer contradict any source information?
        3. Is any important information required to answer the question missing?
        4. Are amounts, dates, capacities, percentages and other details
        represented accurately?

        Rules:
        - Do not use outside knowledge.
        - Do not assume information that is not explicitly established.
        - Treat different tender requirements as separate facts.
        - A number appearing somewhere in the sources does not prove
        that it is associated with the correct claim.
        - If the answer explicitly states that evidence is insufficient,
        consider that appropriate when the passages do not establish
        the requested fact.
        - Set passed=true only when the answer is adequately supported
        and contains no material contradiction.
        - Explain any failure clearly.
        """

        try:
            response = self.client.responses.parse(
                model=self.deployment,
                input=[
                    {"role": "system", "content": instructions},
                    {
                        "role": "user",
                        "content": (
                            f"Question:\n{question}\n\n"
                            f"Generated answer:\n{answer}\n\n"
                            f"Retrieved source passages:\n{context_text}"
                        ),
                    },
                ],
                text_format=SemanticValidation,
            )

            validation = response.output_parsed
            if validation is None:
                raise RuntimeError("Semantic validator returned no structured result.")

            return validation.model_dump()

        except Exception:
            logger.exception("Semantic validation failed")
            return {
                "passed": False,
                "unsupported_claims": [],
                "contradictions": [],
                "missing_information": [],
                "explanation": "Semantic validation could not be completed.",
            }

    def validate_generated_answer(self, parsed, question, sources, results):
        retrieved_contexts = [
            result["text"] for result in results
        ]
        citation_validation = self.validate_citations(
            parsed_citations=parsed.citations,
            sources=sources,
            insufficient_evidence=parsed.insufficient_evidence,
        )
        numerical_validation = self.validate_numerical_consistency(
            answer=parsed.answer,
            retrieved_contexts=retrieved_contexts,
        )
        semantic_validation = self.validate_semantically(
            question=question,
            answer=parsed.answer,
            retrieved_contexts=retrieved_contexts,
        )
        passed = all([
            citation_validation["passed"],
            numerical_validation["passed"],
            semantic_validation["passed"],
        ])
        return {
            "passed": passed,
            "citations": citation_validation["citations"],
            "citation_debug": citation_validation["debug"],
            "citation_validation": {
                "passed": citation_validation["passed"],
            },
            "numerical_validation": numerical_validation,
            "semantic_validation": semantic_validation,
        }