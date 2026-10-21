from ai.services.documents.document_extraction import DocumentExtractionService
from ai.services.documents.document_chunking import DocumentChunkingService
from api_gateway.models import DocumentChunk


class DocumentProcessingService:
    @classmethod
    def process(cls,document):
        pages=DocumentExtractionService.extract(
            document.file.path
        )

        chunks=DocumentChunkingService.chunk(pages)

        DocumentChunk.objects.filter(
            document=document
        ).delete()

        DocumentChunk.objects.bulk_create([
            DocumentChunk(
                document=document,
                chunk_index=index,
                content=chunk["content"],
                page_number=chunk["page_number"],
                metadata={
                    "page_number":chunk["page_number"]
                }
            )
            for index,chunk in enumerate(chunks)
        ])

        return {
            "document_id":document.id,
            "pages":len(pages),
            "chunks":len(chunks),
        }

class TenderDocumentProcessingService:
    @classmethod
    def process_tender(cls,tender):
        results=[]
        for document in tender.documents.all():
            results.append(
                DocumentProcessingService.process(document)
            )
        return results