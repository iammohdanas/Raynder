from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance,VectorParams

class QdrantService:
    COLLECTION_NAME="tender_documents"

    def __init__(self):
        self.client=QdrantClient(host="localhost",port=6333)

    def create_collection(self):
        collections=self.client.get_collections().collections

        if self.COLLECTION_NAME in [c.name for c in collections]:
            return "Collection already exists"

        self.client.create_collection(
            collection_name=self.COLLECTION_NAME,
            vectors_config=VectorParams(
                size=1024,
                distance=Distance.COSINE
            )
        )

        return "Collection created"

    def search(self,vector,limit=5,query_filter=None):
        return self.client.query_points(
            collection_name=self.COLLECTION_NAME,
            query=vector,
            query_filter=query_filter,
            limit=limit
        ).points


    def hybrid_search(self,vector,query_text,limit=5,query_filter=None,prefetch_limit=30):
        results=self.client.query_points(
            collection_name=self.COLLECTION_NAME,
            prefetch=[
                models.Prefetch(
                    query=vector,
                    limit=prefetch_limit
                ),
                models.Prefetch(
                    query=models.Document(
                        text=query_text,
                        model="Qdrant/bm25"
                    ),
                    using="sparse",
                    limit=prefetch_limit
                )
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=query_filter,
            limit=limit,
            with_payload=True
        )
        return results.points