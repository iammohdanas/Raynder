
from ai.services.documents.embedding_service import EmbeddingService
from ai.services.documents.qdrant_service import QdrantService
from qdrant_client.models import Filter,FieldCondition,MatchValue
from ai.services.documents.reranker_service import RerankerService

class DocumentRetrievalService:
    def __init__(self):
        self.qdrant=QdrantService()

    
    def search(self,tender_id,query,limit=5):
        vector=EmbeddingService.embed(query)
        results=self.qdrant.hybrid_search(
            vector=vector,
            query_text=query,
            limit=30,
            prefetch_limit=50,
            query_filter=Filter(must=[
                FieldCondition(
                    key="tender_id",
                    match=MatchValue(value=str(tender_id))
                )
            ])
        )

        candidates=[{
            "score":round(result.score,4),
            "tender_id":result.payload["tender_id"],
            "document":result.payload["filename"],
            "page":result.payload["page_number"],
            "chunk_id":result.payload["chunk_id"],
            "text":result.payload["text"]
        } for result in results]

        return RerankerService.rerank(
            query=query,
            results=candidates,
            limit=limit
        )
