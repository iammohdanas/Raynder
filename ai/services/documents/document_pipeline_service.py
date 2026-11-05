#the final pipeline service that will be used to process the documents, storing chunks into DB and converting them into embeddings and storing it into vector DB
#this will be final service which will be working as an api so that whenever the documents is uploaded it will be processed and stored into vector DB for future use
#It will make chatbot functional, and help to inntegrate the other features as well


from ai.services.documents.document_processor import (
    DocumentProcessingService,
)
from ai.services.documents.vector_index_service import VectorIndexService


class DocumentPipelineService:

    @classmethod
    def run(cls, tender):
        results = []

        # Step 1: Extract and create chunks for documents
        # that do not already have chunks.
        for document in tender.documents.all():

            if document.chunks.exists():
                results.append({
                    "document_id": document.id,
                    "status": "skipped",
                    "reason": "Chunks already exist",
                })
                continue

            result = DocumentProcessingService.process(document)

            results.append({
                "document_id": document.id,
                "status": "processed",
                **result,
            })

        # Step 2: Index chunks in Qdrant
        indexing_result = VectorIndexService().index_tender(tender)

        return {
            "tender_id": tender.tender_id,
            "documents": results,
            "indexing": indexing_result,
        }