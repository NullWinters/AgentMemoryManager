from src.llm.provider import LLMProvider


class SessionSummarizer:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def summarize(self, messages: list[dict]) -> str | None:
        conversation = "\n".join(
            f"{m['role']}: {m['content']}" for m in messages
        )
        system_msg = (
            "你是记忆管理助手。请用1-3句话总结以下对话的关键信息。"
            "只输出摘要，不要额外解释。"
        )
        result = await self.provider.chat(
            [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"对话：\n{conversation}"},
            ],
        )
        return result
