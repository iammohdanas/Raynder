from sentence_transformers import SentenceTransformer

class EmbeddingService:
    MODEL_NAME="Qwen/Qwen3-Embedding-0.6B"
    _model=None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            cls._model=SentenceTransformer(cls.MODEL_NAME)
        return cls._model

    @classmethod
    def embed(cls,text):
        model=cls.get_model()
        return model.encode(
            text,
            normalize_embeddings=True
        ).tolist()

    @classmethod
    def embed_batch(cls,texts):
        model=cls.get_model()
        return model.encode(
            texts,
            normalize_embeddings=True
        ).tolist()