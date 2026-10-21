
import hashlib
import uuid

from qdrant_client.models import PointStruct
from api_gateway.models import DocumentChunk
from ai.services.documents.embedding_service import EmbeddingService
from ai.services.documents.qdrant_service import QdrantService


class VectorIndexService:
    BATCH_SIZE = 32

    def __init__(self):
        self.qdrant = QdrantService()

    @staticmethod
    def get_point_id(chunk):
        value = f"raynder:{chunk.document_id}:{chunk.chunk_index}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, value))
    
    def index_tender(self, tender):
        chunks = list(
            DocumentChunk.objects.filter(
                document__tender=tender
            ).select_related(
                "document",
                "document__tender"
            ).order_by("document_id", "chunk_index")
        )

        if not chunks:
            return {
                "tender_id": tender.tender_id,
                "chunks_found": 0,
                "indexed": 0,
                "message": "No document chunks found."
            }

        indexed = 0

        for start in range(0, len(chunks), self.BATCH_SIZE):
            batch = chunks[start:start + self.BATCH_SIZE]
            texts = [chunk.content for chunk in batch]
            vectors = EmbeddingService.embed_batch(texts)

            points = []

            for chunk, vector in zip(batch, vectors):
                document = chunk.document

                points.append(
                    PointStruct(
                        id=self.get_point_id(chunk),
                        vector=vector,
                        payload={
                            "tender_id": str(tender.tender_id),
                            "document_id": chunk.document_id,
                            "chunk_id": chunk.id,
                            "filename": document.original_filename,
                            "page_number": chunk.page_number,
                            "chunk_index": chunk.chunk_index,
                            "text": chunk.content,
                            "content_hash": hashlib.sha256(
                                chunk.content.encode("utf-8")
                            ).hexdigest(),
                            "source": "raynder",
                        }
                    )
                )

            self.qdrant.client.upsert(
                collection_name=self.qdrant.COLLECTION_NAME,
                points=points,
                wait=True
            )

            indexed += len(points)

        return {
            "tender_id": tender.tender_id,
            "chunks_found": len(chunks),
            "indexed": indexed,
            "batches": (
                len(chunks) + self.BATCH_SIZE - 1
            ) // self.BATCH_SIZE,
        }
