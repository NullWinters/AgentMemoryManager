import logging

import httpx

from src.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


class TextEmbedder:
    def __init__(
        self,
        provider: LLMProvider,
        embedding_model: str | None = None,
    ):
        self.provider = provider
        self.model = embedding_model or provider.model

    async def embed(self, text: str) -> list[float] | None:
        async with LLMProvider._semaphore:
            try:
                async with httpx.AsyncClient(timeout=self.provider.timeout) as client:
                    resp = await client.post(
                        f"{self.provider.base_url}/v1/embeddings",
                        headers={"Authorization": f"Bearer {self.provider.api_key}"},
                        json={"model": self.model, "input": text},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return data["data"][0]["embedding"]
            except Exception as e:
                logger.warning("Embedding call failed: %s", e)
                return None
