# Dev C 施工计划

> **负责模块:** User Memory API、Python SDK、调试前端、集成验证
> **关联:** `docs/superpowers/plans/总体施工计划.md`

---

## 依赖概览

```
Task 2 (Dev A) → Task 5 → Task 10 → Task 11 → Task 12
       (DB)       (API)    (SDK)    (前端)    (验证)
```

- Task 5 依赖 Dev A 的 Task 2（数据库模型就绪）
- Task 10（SDK）基于 API 契约开发，Task 5 API 稳定后即可开始
- Task 11（前端）不依赖后端运行，可纯静态开发
- 等待 Task 2 期间：提前准备 Pydantic schema + SDK 类骨架 + 前端 HTML 骨架

---

# Task 5: User Memory API

**预估:** 3h | **依赖:** Task 2 (Dev A) 完成

## 5.1 创建 src/services/user_service.py

```python
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func
from src.models.database import User, MemoryFragment

class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_user(self, user_id: str) -> User:
        result = await self.db.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(user_id=user_id)
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
        return user

    async def get_user(self, user_id: str) -> User | None:
        result = await self.db.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()

    async def update_profile(self, user_id: str, profile: dict) -> User | None:
        user = await self.get_user(user_id)
        if not user:
            return None
        existing = user.profile or {}
        existing.update(profile)
        user.profile = existing
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def add_memory_fragment(self, user_id: str, type: str, content: str,
                                   importance: float = 0.5, embedding: list[float] = None,
                                   source_msg_id: str = None) -> MemoryFragment:
        fragment = MemoryFragment(
            fragment_id=uuid.uuid4(),
            user_id=user_id,
            type=type,
            content=content,
            importance=importance,
            embedding=embedding,
            source_msg_id=source_msg_id,
        )
        self.db.add(fragment)
        await self.db.commit()
        await self.db.refresh(fragment)
        return fragment

    async def search_memories(self, user_id: str, query: str = None,
                               vector: list[float] = None, top_k: int = 5,
                               fragment_type: str = None) -> list[MemoryFragment]:
        # 如果有向量 → 向量检索；否则 → 降级为全文检索
        if vector is not None:
            stmt = text("""
                SELECT *, embedding <=> :vec::vector AS score
                FROM memory_fragments
                WHERE user_id = :uid
                  AND (:ftype IS NULL OR type = :ftype)
                ORDER BY embedding <=> :vec::vector
                LIMIT :lim
            """)
            result = await self.db.execute(stmt, {
                "vec": f"[{','.join(str(v) for v in vector)}]",
                "uid": user_id, "ftype": fragment_type, "lim": top_k
            })
        elif query:
            stmt = text("""
                SELECT *, ts_rank(to_tsvector('simple', content),
                       plainto_tsquery('simple', :query)) AS score
                FROM memory_fragments
                WHERE user_id = :uid
                  AND to_tsvector('simple', content) @@ plainto_tsquery('simple', :query)
                  AND (:ftype IS NULL OR type = :ftype)
                ORDER BY score DESC
                LIMIT :lim
            """)
            result = await self.db.execute(stmt, {
                "query": query, "uid": user_id,
                "ftype": fragment_type, "lim": top_k
            })
        else:
            # 无查询 → 返回最近记忆
            result = await self.db.execute(
                select(MemoryFragment)
                .where(MemoryFragment.user_id == user_id)
                .order_by(MemoryFragment.created_at.desc())
                .limit(top_k)
            )
        return list(result.scalars().all())

    async def delete_memory_fragment(self, fragment_id: str) -> bool:
        result = await self.db.execute(
            select(MemoryFragment).where(MemoryFragment.fragment_id == fragment_id)
        )
        fragment = result.scalar_one_or_none()
        if fragment:
            await self.db.delete(fragment)
            await self.db.commit()
            return True
        return False
```

## 5.2 创建 Pydantic Schemas

在 `src/routers/users.py` 中定义：

```python
from pydantic import BaseModel
from datetime import datetime

class ProfileUpdate(BaseModel):
    profile: dict

class AddMemoryRequest(BaseModel):
    type: str = "fact"
    content: str
    importance: float = 0.5
    source_msg_id: str | None = None

class MemoryFragmentResponse(BaseModel):
    fragment_id: str
    type: str
    content: str
    importance: float
    score: float | None = None
    created_at: datetime
```

## 5.3 创建 src/routers/users.py

实现端点（参考 `设计.md` §四）：

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/v1/users/{user_id}/profile` | 获取用户画像（不存在则 404） |
| PATCH | `/api/v1/users/{user_id}/profile` | 合并更新画像 JSONB |
| POST | `/api/v1/users/{user_id}/memories` | 手动添加记忆片段 |
| GET | `/api/v1/users/{user_id}/memories?query=&top_k=&type=` | 检索记忆（向量/全文/最近） |
| DELETE | `/api/v1/users/{user_id}/memories/{fragment_id}` | 删除单条记忆 |

---

# Task 10: Python SDK

**预估:** 3h | **依赖:** Task 5 API 稳定

## 10.1 创建 sdk/setup.py

```python
from setuptools import setup, find_packages

setup(
    name="agentmemory-client",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["requests>=2.28"],
    author="AgentMemoryManager Team",
    description="AI Agent Memory Management SDK",
    python_requires=">=3.10",
)
```

## 10.2 创建 sdk/requirements.txt

```
requests>=2.28
```

## 10.3 创建 sdk/agentmemory/__init__.py

```python
from .client import MemoryClient
from .session import Session
from .context import Context, AgentMemory, UserMemory, SessionMemory
from .exceptions import MemoryServiceError
```

## 10.4 创建 sdk/agentmemory/exceptions.py

```python
class MemoryServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}
```

## 10.5 创建 sdk/agentmemory/client.py

```python
import requests
from .session import Session
from .exceptions import MemoryServiceError

class MemoryClient:
    def __init__(self, base_url: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session_headers = {"X-API-Key": api_key} if api_key else {}

    def _request(self, method: str, path: str, json: dict = None) -> dict:
        url = f"{self.base_url}{path}"
        resp = requests.request(method, url, headers=self.session_headers, json=json)
        if resp.status_code >= 400:
            raise MemoryServiceError(
                f"API error: {resp.text}", status_code=resp.status_code, response=resp.json()
            )
        return resp.json() if resp.text else {}

    # Agent
    def setup(self, agent_id: str, name: str = None, persona: str = "",
              config: dict = None):
        return self._request("POST", "/api/v1/agents", json={
            "agent_id": agent_id, "name": name or agent_id,
            "persona": persona, "config": config or {}
        })

    def add_skill_to_agent(self, agent_id: str, skill_id: str):
        return self._request("POST", f"/api/v1/agents/{agent_id}/skills/{skill_id}")

    def create_skill(self, name: str, trigger_keys: list[str],
                     prompt_snippet: str = "") -> dict:
        return self._request("POST", "/api/v1/skills", json={
            "name": name, "trigger_keys": trigger_keys,
            "prompt_snippet": prompt_snippet
        })

    # Session
    def session_start(self, agent_id: str, user_id: str,
                      session_id: str = None) -> Session:
        data = self._request("POST", "/api/v1/sessions", json={
            "agent_id": agent_id, "user_id": user_id, "session_id": session_id
        })
        return Session(client=self, agent_id=agent_id, user_id=user_id,
                       session_id=data["session_id"])

    # User Memory
    def get_user_profile(self, user_id: str) -> dict:
        return self._request("GET", f"/api/v1/users/{user_id}/profile")

    def update_user_profile(self, user_id: str, profile: dict) -> dict:
        return self._request("PATCH", f"/api/v1/users/{user_id}/profile",
                             json={"profile": profile})

    def add_user_memory(self, user_id: str, type: str, content: str,
                        importance: float = 0.5) -> dict:
        return self._request("POST", f"/api/v1/users/{user_id}/memories", json={
            "type": type, "content": content, "importance": importance
        })

    def search_user_memories(self, user_id: str, query: str = "",
                              top_k: int = 10, type: str = None) -> dict:
        params = f"top_k={top_k}"
        if query:
            params += f"&query={query}"
        if type:
            params += f"&type={type}"
        return self._request("GET",
            f"/api/v1/users/{user_id}/memories?{params}")

    # Admin
    def stats(self) -> dict:
        return self._request("GET", "/api/v1/stats")

    def health(self) -> dict:
        return self._request("GET", "/api/v1/health")
```

## 10.6 创建 sdk/agentmemory/session.py

```python
class Session:
    def __init__(self, client, agent_id: str, user_id: str, session_id: str):
        self._client = client
        self.agent_id = agent_id
        self.user_id = user_id
        self.session_id = session_id

    def add_message(self, role: str, content: str,
                    tool_name: str = None, tool_call_id: str = None) -> dict:
        return self._client._request("POST",
            f"/api/v1/sessions/{self.session_id}/messages", json={
                "role": role, "content": content,
                "tool_name": tool_name, "tool_call_id": tool_call_id
            })

    def inject_context(self, query: str = None, **opts) -> "Context":
        from .context import Context
        body = {
            "agent_id": self.agent_id, "user_id": self.user_id,
            "session_id": self.session_id, "query": query,
            "options": {**opts}
        }
        data = self._client._request("POST", "/api/v1/context", json=body)
        return Context.from_response(data)

    def end(self) -> dict:
        return self._client._request("PATCH",
            f"/api/v1/sessions/{self.session_id}", json={"status": "completed"})

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.end()
```

## 10.7 创建 sdk/agentmemory/context.py

```python
from dataclasses import dataclass, field

@dataclass
class Skill:
    name: str
    prompt_snippet: str

@dataclass
class AgentMemory:
    agent_id: str
    persona: str
    skills: list[Skill] = field(default_factory=list)

@dataclass
class Fragment:
    type: str
    content: str
    score: float = 0.0

@dataclass
class UserMemory:
    profile: dict = field(default_factory=dict)
    fragments: list[Fragment] = field(default_factory=list)

@dataclass
class Message:
    role: str
    content: str
    tool_name: str | None = None

@dataclass
class SessionMemory:
    session_id: str
    message_count: int = 0
    summary: str | None = None
    messages: list[Message] = field(default_factory=list)

@dataclass
class Context:
    agent_memory: AgentMemory
    user_memory: UserMemory
    session_memory: SessionMemory

    @classmethod
    def from_response(cls, data: dict) -> "Context":
        am = data["agent_memory"]
        um = data["user_memory"]
        sm = data["session_memory"]

        return cls(
            agent_memory=AgentMemory(
                agent_id=am["agent_id"], persona=am.get("persona", ""),
                skills=[Skill(**s) for s in am.get("skills", [])]
            ),
            user_memory=UserMemory(
                profile=um.get("profile", {}),
                fragments=[Fragment(**f) for f in um.get("fragments", [])]
            ),
            session_memory=SessionMemory(
                session_id=sm["session_id"],
                message_count=sm.get("message_count", 0),
                summary=sm.get("summary"),
                messages=[Message(**m) for m in sm.get("messages", [])]
            ),
        )

    def to_messages(self) -> list[dict]:
        """将三层记忆拼接为标准 OpenAI 消息列表"""
        messages = []

        # System: Persona + Skills + Profile
        system_parts = [self.agent_memory.persona]
        for skill in self.agent_memory.skills:
            system_parts.append(f"\n[技能：{skill.name}]\n{skill.prompt_snippet}")
        if self.user_memory.profile:
            profile_str = ", ".join(
                f"{k}={v.get('v', v)}" if isinstance(v, dict) else f"{k}={v}"
                for k, v in self.user_memory.profile.items()
            )
            system_parts.append(f"\n用户偏好：{profile_str}")
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})

        # User memory fragments injected as user messages
        for frag in self.user_memory.fragments:
            messages.append({
                "role": "user",
                "content": f"[历史记忆] {frag.content}"
            })

        # Session messages
        for msg in self.session_memory.messages:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })

        return messages
```

## 10.8 验证

```bash
pip install -e sdk/
python -c "from agentmemory import MemoryClient; print('SDK OK')"
```

---

# Task 11: 调试前端

**预估:** 2h | **依赖:** 无（静态开发）

## 11.1 创建 src/static/debug.html

单一 HTML 文件，~800 行。实现以下结构：

### 布局：三栏 + 状态栏

```html
<div class="container">
  <aside class="sidebar-left"><!-- Agent 列表 --></aside>
  <aside class="sidebar-middle"><!-- User/Session 树 --></aside>
  <main class="main-area">
    <nav class="tabs">
      <button data-tab="agent">Agent Info</button>
      <button data-tab="user">User Memory</button>
      <button data-tab="session">Session</button>
      <button data-tab="context">Context Preview</button>
      <button data-tab="llm">LLM Logs</button>
    </nav>
    <section class="tab-content" id="tab-content"><!-- Tab 内容 --></section>
  </main>
</div>
<footer class="status-bar"><!-- 状态栏 --></footer>
```

### 技术要点

1. **API 通信:** `fetch()` 调用微服务 API，`X-API-Key` header
2. **路由:** `window.location.hash` 控制 Tab 切换，刷新不丢状态
3. **状态管理:** 全局 `state = {apiBase, apiKey, selectedAgent, selectedUser, selectedSession}`
4. **暗色主题:** CSS Variables + `@media (prefers-color-scheme: dark)`
5. **API 地址配置:** 状态栏可切换 `http://localhost:8000` 等

### Tab 1: Agent Info

- 左侧 Agent 列表 → 点击选中 → 展示右侧详情
- 详情区：agent_id, name, status, persona 文本框, config JSON 编辑器(语法高亮), Skills 表格(含 toggle 开关)
- 操作按钮：注册新 Agent / 保存配置 / 绑定 Skill / 解绑 Skill

### Tab 2: User Memory

- 顶部 User 切换 + Profile JSON 查看/编辑
- 检索框：搜索关键词 + top_k 选择 + type 筛选
- 搜索结果列表：type, content(截断), importance, score
- 底部操作：手动添加记忆 / 删除选中

### Tab 3: Session

- User/Session 树 → 选中 Session → 展示消息列表
- 消息列表样式：左侧 user 消息 + 右侧 assistant 消息（气泡）
- 底部操作：添加测试消息 / 触发摘要 / 结束会话

### Tab 4: Context Preview

- 顶部选择 Agent + User + Session 三联
- "刷新上下文"按钮 → 调用 `POST /api/v1/context`
- 展示 `to_messages()` 模拟输出：
  - `[0] system` 背景蓝色
  - `[1..K] user (记忆注入)` 背景灰色
  - `[K+1..] 会话消息` 默认背景
- 每行标注角色和来源
- Token 估算显示 + 复制按钮（复制 JSON / 复制 messages 数组）

### Tab 5: LLM Logs

- LLM 状态指示灯（enabled/disabled）
- 最近调用表格：时间 / 操作类型 / 耗时 / Tokens in/out / 状态
- 点击行展开 → 完整 prompt + response 对比

### 全局状态栏

- API 连接状态：`● Connected` 或 `○ Disconnected`
- LLM 状态：`● Enabled (gpt-4o-mini)` 或 `○ Disabled`
- pgvector 状态：靠 health API 检测

---

# Task 12: 集成验证

**执行: 全体 / 预估: 2h**

按 `总体施工计划.md` Task 12 验证清单逐项执行，特别关注：
- User Memory 向量检索 + 全文检索降级
- SDK `pip install -e sdk/` → 端到端调用链路
- 前端 `/debug` 页面加载 + 所有 Tab 交互正常
