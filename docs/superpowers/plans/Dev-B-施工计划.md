# Dev B 施工计划

> **负责模块:** Agent & Skill API、LLM 模块、集成验证
> **关联:** `docs/superpowers/plans/总体施工计划.md`

---

## 依赖概览

```
Task 2 (Dev A) → Task 4 → Task 8 → Task 12
       (DB)       (API)    (LLM)    (验证)
```

- Task 4 依赖 Dev A 的 Task 2（数据库模型就绪）
- Task 8 可独立开发，与 Task 4 无耦合
- 等待 Task 2 期间：提前准备 Pydantic request/response schema

---

# Task 4: Agent & Skill API

**预估:** 3h | **依赖:** Task 2 (Dev A) 完成

## 4.1 创建 src/services/agent_service.py

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.database import Agent, Skill, SkillAgent

class AgentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_agent(self, agent_id: str, name: str,
                           persona: str = "", config: dict = None) -> Agent:
        agent = Agent(
            agent_id=agent_id, name=name, persona=persona,
            config=config or {}
        )
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def get_agent(self, agent_id: str) -> Agent | None:
        result = await self.db.execute(select(Agent).where(Agent.agent_id == agent_id))
        return result.scalar_one_or_none()

    async def update_agent(self, agent_id: str, **kwargs) -> Agent | None:
        agent = await self.get_agent(agent_id)
        if not agent:
            return None
        for key, value in kwargs.items():
            if value is not None:
                setattr(agent, key, value)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def add_skill_to_agent(self, agent_id: str, skill_id: str) -> SkillAgent:
        sa = SkillAgent(skill_id=skill_id, agent_id=agent_id)
        self.db.add(sa)
        await self.db.commit()
        return sa

    async def remove_skill_from_agent(self, agent_id: str, skill_id: str) -> bool:
        result = await self.db.execute(
            select(SkillAgent).where(
                SkillAgent.agent_id == agent_id,
                SkillAgent.skill_id == skill_id
            )
        )
        sa = result.scalar_one_or_none()
        if sa:
            await self.db.delete(sa)
            await self.db.commit()
            return True
        return False

    async def get_agent_skills(self, agent_id: str) -> list[Skill]:
        result = await self.db.execute(
            select(Skill).join(SkillAgent)
            .where(SkillAgent.agent_id == agent_id, SkillAgent.enabled == True)
        )
        return list(result.scalars().all())
```

## 4.2 创建 src/services/skill_service.py

```python
class SkillService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_skill(self, name: str, trigger_keys: list[str],
                           prompt_snippet: str = "") -> Skill:
        skill = Skill(name=name, trigger_keys=trigger_keys, prompt_snippet=prompt_snippet)
        self.db.add(skill)
        await self.db.commit()
        await self.db.refresh(skill)
        return skill

    async def list_skills(self) -> list[Skill]:
        result = await self.db.execute(select(Skill).order_by(Skill.created_at))
        return list(result.scalars().all())

    async def get_skill(self, skill_id: str) -> Skill | None:
        result = await self.db.execute(select(Skill).where(Skill.skill_id == skill_id))
        return result.scalar_one_or_none()

    async def update_skill(self, skill_id: str, **kwargs) -> Skill | None:
        skill = await self.get_skill(skill_id)
        if not skill:
            return None
        for key, value in kwargs.items():
            if value is not None:
                setattr(skill, key, value)
        await self.db.commit()
        await self.db.refresh(skill)
        return skill

    async def delete_skill(self, skill_id: str) -> bool:
        skill = await self.get_skill(skill_id)
        if skill:
            await self.db.delete(skill)
            await self.db.commit()
            return True
        return False
```

## 4.3 创建 Pydantic Schemas

在 `src/routers/agents.py` 和 `src/routers/skills.py` 中定义：

```python
from pydantic import BaseModel

class AgentCreate(BaseModel):
    agent_id: str
    name: str
    persona: str = ""
    config: dict = {}

class AgentUpdate(BaseModel):
    name: str | None = None
    persona: str | None = None
    config: dict | None = None
    status: str | None = None

class SkillCreate(BaseModel):
    name: str
    trigger_keys: list[str]
    prompt_snippet: str = ""

class SkillUpdate(BaseModel):
    name: str | None = None
    trigger_keys: list[str] | None = None
    prompt_snippet: str | None = None

class SkillBindRequest(BaseModel):
    skill_id: str
```

## 4.4 创建 src/routers/agents.py

实现端点（详细实现参考 `设计.md` §四）：

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/v1/agents` | 注册 Agent |
| GET | `/api/v1/agents/{agent_id}` | 获取 Agent 详情 |
| PATCH | `/api/v1/agents/{agent_id}` | 更新 Agent 配置/人设 |
| POST | `/api/v1/agents/{agent_id}/skills/{skill_id}` | 绑定 Skill 到 Agent |
| DELETE | `/api/v1/agents/{agent_id}/skills/{skill_id}` | 解绑 Skill |
| GET | `/api/v1/agents/{agent_id}/skills` | 查看已绑定 Skills |

## 4.5 创建 src/routers/skills.py

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/v1/skills` | 创建 Skill |
| GET | `/api/v1/skills` | 列出全部 Skills |
| GET | `/api/v1/skills/{skill_id}` | 获取单个 Skill |
| PATCH | `/api/v1/skills/{skill_id}` | 更新 Skill |
| DELETE | `/api/v1/skills/{skill_id}` | 删除 Skill |

---

# Task 8: LLM 模块

**预估:** 3h | **依赖:** 无

LLM 模块完全可选，设计为独立于其他模块的包。如果 `agents.config.llm` 未配置，所有功能自动降级。

## 8.1 创建 src/llm/__init__.py

```python
from src.llm.provider import LLMProvider
from src.llm.extractor import MemoryExtractor
from src.llm.summarizer import SessionSummarizer
from src.llm.embedder import TextEmbedder
```

## 8.2 创建 src/llm/provider.py

```python
import httpx
import logging

logger = logging.getLogger(__name__)

class LLMProvider:
    """OpenAI API 兼容的 LLM 客户端"""

    def __init__(self, api_key: str, base_url: str = None,
                 model: str = "gpt-4o-mini", timeout: float = 30.0):
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com").rstrip("/")
        self.model = model
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(5)

    async def chat(self, messages: list[dict], temperature: float = 0.3,
                   max_tokens: int = 500, response_format: dict = None) -> str | None:
        async with self.semaphore:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    body = {
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
                logger.warning(f"LLM call failed: {e}")
                return None
```

## 8.3 创建 src/llm/embedder.py

```python
class TextEmbedder:
    def __init__(self, provider: LLMProvider, embedding_model: str = "text-embedding-3-small"):
        self.provider = provider
        self.model = embedding_model

    async def embed(self, text: str) -> list[float] | None:
        async with self.provider.semaphore:
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
                logger.warning(f"Embedding failed: {e}")
                return None
```

## 8.4 创建 src/llm/summarizer.py

```python
class SessionSummarizer:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def summarize(self, messages: list[dict]) -> str | None:
        conversation = "\n".join(
            f"{m['role']}: {m['content']}" for m in messages
        )
        system_msg = "你是记忆管理助手。请用1-3句话总结以下对话的关键信息。只输出摘要，不要额外解释。"
        result = await self.provider.chat([
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"对话：\n{conversation}"},
        ])
        return result
```

## 8.5 创建 src/llm/extractor.py

```python
import json

class MemoryExtractor:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def extract(self, messages: list[dict]) -> dict:
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
```

## 8.6 LLM 模块集成点

在 `src/services/session_service.py` 的 `add_message` 方法中，异步调用：

```python
# add_message 方法末尾追加：
import asyncio
from src.llm import LLMProvider, TextEmbedder, SessionSummarizer, MemoryExtractor

# 获取 agent config 判断 LLM 是否启用
agent = await self.get_agent(session.agent_id)
llm_config = agent.config.get("llm", {})
if llm_config.get("api_key"):
    provider = LLMProvider(
        api_key=llm_config["api_key"],
        base_url=llm_config.get("base_url"),
        model=llm_config.get("model", "gpt-4o-mini"),
    )
    embedder = TextEmbedder(provider, llm_config.get("embedding_model", "text-embedding-3-small"))
    summarizer = SessionSummarizer(provider)
    extractor = MemoryExtractor(provider)

    # 异步后台任务
    async def _llm_tasks():
        # 4a. 生成 embedding
        emb = await embedder.embed(content)
        if emb:
            await self.db.execute(
                update(Message).where(Message.message_id == message.message_id)
                .values(embedding=emb)
            )

        # 4b/c. 如果消息数超阈值
        msg_count = (await self.db.execute(
            select(func.count()).where(Message.session_id == session_id)
        )).scalar()
        if msg_count > 40:
            all_msgs = await self.get_messages(session_id, limit=msg_count)
            msgs_data = [{"role": m.role, "content": m.content} for m in all_msgs]
            # 摘要
            summary = await summarizer.summarize(msgs_data)
            if summary:
                await self.db.execute(
                    update(Session).where(Session.session_id == session_id).values(summary=summary)
                )
            # 记忆提取
            extracted = await extractor.extract(msgs_data)
            for frag in extracted.get("fragments", []):
                await self.db.add(MemoryFragment(
                    user_id=session.user_id, type=frag["type"],
                    content=frag["content"], importance=frag["importance"]
                ))
            # profile 更新
            profile_updates = extracted.get("profile_updates", {})
            if profile_updates:
                user = await self.db.execute(select(User).where(User.user_id == session.user_id))
                user_row = user.scalar_one_or_none()
                if user_row:
                    existing_profile = user_row.profile or {}
                    existing_profile.update(profile_updates)
                    user_row.profile = existing_profile

        await self.db.commit()

    asyncio.create_task(_llm_tasks())
```

---

# Task 11: 调试前端（共用部分）

Dev B 不直接负责前端，但需要在 LLM Logs Tab 提供数据接口。

## 11.1 创建 LLM 日志端点

在 `src/routers/admin.py` 中追加：

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/api/v1/llm/logs")
async def get_llm_logs():
    # 返回最近 LLM 调用记录
    # 可从 audit_log 表筛选 operation = 'LLM' 的记录
    pass
```

---

# Task 12: 集成验证

**执行: 全体 / 预估: 2h**

按 `总体施工计划.md` Task 12 验证清单逐项执行，特别关注：
- Agent CRUD + Skill 绑定/解绑端点
- LLM 降级模式（不配 API Key 时仍正常服务）
- LLM 全功能模式（配置 API Key 后摘要/提取/嵌入正常）
