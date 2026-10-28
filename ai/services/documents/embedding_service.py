
import torch
from sentence_transformers import SentenceTransformer


class EmbeddingService:
    MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"

    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"Loading embedding model on: {device}")

            cls._model = SentenceTransformer(
                cls.MODEL_NAME,
                device=device,
            )

            print(f"Embedding model loaded on: {cls._model.device}")

        return cls._model

    @classmethod
    def embed(cls, text):
        model = cls.get_model()

        return model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).tolist()

    @classmethod
    def embed_batch(cls, texts):
        model = cls.get_model()

        return model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=16,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).tolist()
