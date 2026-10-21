class DocumentChunkingService:
    CHUNK_SIZE=1500
    CHUNK_OVERLAP=200

    @classmethod
    def chunk(cls,pages):
        chunks=[]

        for page in pages:
            text=page["text"]

            start=0

            while start<len(text):
                end=start+cls.CHUNK_SIZE
                content=text[start:end].strip()

                if content:
                    chunks.append({
                        "content":content,
                        "page_number":page["page_number"],
                    })

                start=end-cls.CHUNK_OVERLAP

                if start>=len(text):
                    break

        return chunks