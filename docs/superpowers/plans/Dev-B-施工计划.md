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

**完成状态:** ✅ 已完成 (2026-06-29)

### 设计决策

| # | 决策点 | 选择 | 说明 |
|---|--------|------|------|
| 1 | UUID 路径参数 | `uuid.UUID` | FastAPI 自动校验，0 样板代码 |
| 2 | Service 更新方法 | 显式参数 | 类型安全，与 `sessions.py` 模式一致 |
| 3 | 异常处理 | Router 转 HTTP，Service 返回 None | 延续 sessions.py 模式 |
| 4 | `add_skill_to_agent` 跨表查询 | AgentService 直接查 skills 表 | ORM 表是共享资源，非私有财产 |
| 5 | 响应模型 | 含 `enabled` 字段 (`AgentSkillResponse`) | 调试前端 Tab 需要 toggle 开关 |

### 实际产出

#### 4.1 `src/services/agent_service.py` (84 行, 7 方法)

| 方法 | 参数变化 | 特性 |
|------|----------|------|
| `create_agent` | 无变化 | — |
| `get_agent` | 无变化 | — |
| `update_agent(agent_id, name, persona, config, status)` | `**kwargs` → 显式参数 | 类型安全 |
| `add_skill_to_agent(agent_id, skill_id: uuid.UUID)` | `str` → `uuid.UUID`; 新增前置验证 | Agent/Skill 存在性 + 重复绑定三检查 |
| `remove_skill_from_agent(agent_id, skill_id: uuid.UUID)` | `str` → `uuid.UUID` | — |
| `get_agent_skills(agent_id)` | 无变化 | 仅返回 enabled=True 的 Skills |
| `get_agent_skill_bindings(agent_id)` | **新增** | 返回所有 SkillAgent 记录（含 enabled 状态） |

#### 4.2 `src/services/skill_service.py` (57 行, 5 方法)

| 方法 | 参数变化 |
|------|----------|
| `create_skill`, `list_skills` | 无变化 |
| `get_skill(skill_id: uuid.UUID)` | `str` → `uuid.UUID` |
| `update_skill(skill_id: uuid.UUID, name, trigger_keys, prompt_snippet)` | `str` → `uuid.UUID`; `**kwargs` → 显式参数 |
| `delete_skill(skill_id: uuid.UUID)` | `str` → `uuid.UUID` |

#### 4.3 `src/routers/agents.py` (139 行, 6 端点)

Pydantic Schemas: `AgentCreate`, `AgentUpdate`, `AgentResponse`, `AgentSkillResponse`(含 enabled), `SkillBindingResponse`
所有响应模型含 `model_config = ConfigDict(from_attributes=True)`

| 端点 | 响应 |
|------|------|
| `POST /agents` | 200 OK / 409 重复 |
| `GET /agents/{agent_id}` | 200 / 404 |
| `PATCH /agents/{agent_id}` | 200 / 404 |
| `POST /agents/{agent_id}/skills/{skill_id}` | 201+JSON / 404 / 409 重复 |
| `DELETE /agents/{agent_id}/skills/{skill_id}` | 204 / 404 |
| `GET /agents/{agent_id}/skills` | 200 (含 enabled 字段) / 404 |

#### 4.4 `src/routers/skills.py` (92 行, 5 端点)

Pydantic Schemas: `SkillCreate`, `SkillUpdate`, `SkillResponse`

| 端点 | 响应 |
|------|------|
| `POST /skills` | 201 |
| `GET /skills` | 200 |
| `GET /skills/{skill_id}` | 200 / 404 |
| `PATCH /skills/{skill_id}` | 200 / 404 |
| `DELETE /skills/{skill_id}` | 204 / 404 |

### 验证结果

- Agent CRUD: POST → GET → PATCH (200/404/409) ✓
- Skill CRUD: POST → GET → PATCH → DELETE (201/200/204/404) ✓
- Skill 绑定: POST → GET (含 enabled) → 重复绑定 409 → DELETE ✓
- UUID 路径参数: 非法 UUID 返回 422 (FastAPI 内置) ✓
- 跨表 FK 验证: 不存在的 Skill → 404 ✓

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
