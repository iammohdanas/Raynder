
import asyncio

from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import Faithfulness, ContextRelevance

from Raynder import settings


class RagasEvaluationService:
    """Evaluate live RAG answers against retrieved tender evidence."""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            base_url=(
                f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}"
                "/openai/v1/"
            ),
            timeout=60.0,
            max_retries=1,
        )

        self.judge_llm = llm_factory(
            settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            client=self.client,
            temperature=1.0,
            max_tokens=4096,
        )
        self.judge_llm.model_args = self.judge_llm._map_openai_params()

        # Ensure GPT-5.1-compatible request parameters.
        self.judge_llm.model_args.pop("top_p", None)

        if "max_tokens" in self.judge_llm.model_args:
            self.judge_llm.model_args["max_completion_tokens"] = (
                self.judge_llm.model_args.pop("max_tokens")
            )

        self.judge_llm.model_args["temperature"] = 1.0

        self.faithfulness = Faithfulness(llm=self.judge_llm)
        self.context_relevance = ContextRelevance(llm=self.judge_llm)

    async def _evaluate(self, question, answer, retrieved_contexts):
        contexts = retrieved_contexts or []

        if not contexts:
            return {
                "faithfulness": None,
                "context_relevance": 0.0,
                "evaluation_note": "No contexts retrieved",
            }

        faithfulness_result = await self.faithfulness.ascore(
            user_input=question,
            response=answer,
            retrieved_contexts=contexts,
        )

        relevance_result = await self.context_relevance.ascore(
            user_input=question,
            retrieved_contexts=contexts,
        )

        return {
            "faithfulness": faithfulness_result.value,
            "context_relevance": relevance_result.value,
        }

    
    def evaluate(self, question, answer, retrieved_contexts):
        """Evaluate and close the async client in the same event loop."""

        async def run_evaluation():
            try:
                return await self._evaluate(
                    question=question,
                    answer=answer,
                    retrieved_contexts=retrieved_contexts,
                )
            finally:
                await self.client.close()

        return asyncio.run(run_evaluation())

    def close(self):
        """Client cleanup is handled inside evaluate()."""
        pass

