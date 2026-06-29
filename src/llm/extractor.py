import json
from typing import TypedDict

from src.llm.provider import LLMProvider


class MemoryFragmentData(TypedDict):
    type: str
    content: str
    importance: float


class ProfileUpdate(TypedDict):
    v: str
    c: float


class ExtractionResult(TypedDict):
    fragments: list[MemoryFragmentData]
    profile_updates: dict[str, ProfileUpdate]


class MemoryExtractor:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def extract(self, messages: list[dict]) -> ExtractionResult:
        conversation = "\n".join(
            f"{m['role']}: {m['content']}" for m in messages
        )
        system_msg = (
            "你是记忆管理助手。分析以下对话，提取关于用户的关键信息。\n"
            '输出格式（JSON）：{"fragments": [{"type":"preference/fact","content":"...","importance":0.0-1.0}],'
            '"profile_updates": {"key":{"v":"value","c":0.0-1.0}}}'
        )
        result = await self.provider.chat(
            [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"对话：\n{conversation}\n请只输出JSON，不要额外内容。"},
            ],
            response_format={"type": "json_object"},
        )
        if result:
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return {"fragments": [], "profile_updates": {}}
        return {"fragments": [], "profile_updates": {}}
