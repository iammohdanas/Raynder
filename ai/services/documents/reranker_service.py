
from sentence_transformers import CrossEncoder

class RerankerService:
    MODEL_NAME="cross-encoder/ms-marco-MiniLM-L-6-v2"
    _model=None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            cls._model=CrossEncoder(cls.MODEL_NAME,max_length=512)
        return cls._model

    @classmethod
    def rerank(cls,query,results,limit=5):
        if not results:
            return []

        pairs=[
            (query,result["text"])
            for result in results
        ]
        scores=cls.get_model().predict(pairs,batch_size=16)

        reranked=[]
        for result,score in zip(results,scores):
            item=result.copy()
            item["rerank_score"]=round(float(score),4)
            reranked.append(item)

        return sorted(
            reranked,
            key=lambda item:item["rerank_score"],
            reverse=True
        )[:limit]
