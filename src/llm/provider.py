import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class LLMProvider:
    _semaphore = asyncio.Semaphore(5)

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str = "gpt-4o-mini",
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        raw = (base_url or "https://api.openai.com").rstrip("/")
        if raw.endswith("/v1"):
            raw = raw[:-3]
        self.base_url = raw
        self.model = model
        self.timeout = timeout

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 500,
        response_format: dict | None = None,
    ) -> str | None:
        async with LLMProvider._semaphore:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    body: dict = {
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                    if response_format:
                        body["response_format"] = response_format

                    resp = await client.post(
                        f"{self.base_url}/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=body,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
            except Exception as e:
                logger.warning("LLM chat call failed: %s", e)
                return None
