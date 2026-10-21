from api_gateway.models import DocumentChunk

class DocumentRetrievalService:
    @staticmethod
    def search(tender,query,limit=5):
        query=query.strip().lower()
        terms=[x for x in query.split() if x]
        chunks=DocumentChunk.objects.filter(document__tender=tender)
        results=[]

        for chunk in chunks:
            content=chunk.content.lower()
            score=0

            if query in content:
                score+=10

            for term in terms:
                score+=content.count(term)

            if score:
                results.append((score,chunk))

        results.sort(key=lambda x:x[0],reverse=True)

        return [
            {
                "score":score,
                "document":chunk.document.original_filename,
                "document_id":chunk.document_id,
                "page":chunk.page_number,
                "chunk_index":chunk.chunk_index,
                "content":chunk.content,
            }
            for score,chunk in results[:limit]
        ]