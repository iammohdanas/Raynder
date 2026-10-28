
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

logger = logging.getLogger(__name__)

class SourceCitation(BaseModel):
    source_id: str
    quote: str


class GroundedAnswer(BaseModel):
    answer: str
    citations: list[SourceCitation]
    insufficient_evidence: bool


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

        response=self.client.responses.parse(
            model=self.deployment,
            
        input=[
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
        ],

            text_format=GroundedAnswer
        )

        parsed=response.output_parsed
        if parsed is None:
            raise RuntimeError("The LLM did not return a structured answer.")

        
        citations = []
        citation_debug = []

        for citation in parsed.citations:
            result = sources.get(citation.source_id)

            if not result:
                citation_debug.append({
                    "source_id": citation.source_id,
                    "status": "invalid_source_id",
                })
                continue

            quote = citation.quote.strip()

            if not quote:
                citation_debug.append({
                    "source_id": citation.source_id,
                    "status": "empty_quote",
                })
                continue

            if self.normalize(quote) not in self.normalize(result["text"]):
                citation_debug.append({
                    "source_id": citation.source_id,
                    "status": "quote_not_found",
                    "document": result["document"],
                    "page": result["page"],
                    "quote": quote,
                })
                continue

            citations.append({
                "source_id": citation.source_id,
                "document": result["document"],
                "page": result["page"],
                "chunk_id": result["chunk_id"],
                "quote": quote,
            })

            citation_debug.append({
                "source_id": citation.source_id,
                "status": "valid",
                "document": result["document"],
                "page": result["page"],
                "chunk_id": result["chunk_id"],
            })
        # Do not return citations when the answer is marked
        # as unsupported by the available evidence.
        if parsed.insufficient_evidence:
            citations = []
        return {
            "answer": parsed.answer,
            "citations": citations,
            "insufficient_evidence": parsed.insufficient_evidence,
            "citation_debug": citation_debug,
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
