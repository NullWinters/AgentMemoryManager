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

**完成状态:** ✅ 已完成 (2026-06-29)

### 设计决策

| # | 决策点 | 选择 | 说明 |
|---|--------|------|------|
| 1 | httpx client 生命周期 | 每调用新建 (`async with AsyncClient`) | Provider 生命周期 = 单次 LLM 任务，多 Agent 多 endpoint 不能共享连接 |
| 2 | 信号量作用域 | 类级别 `LLMProvider._semaphore` | 全局 5 并发，所有 Provider 实例共享 |
| 3 | DB 会话生命周期 | BackgroundTasks + LLMService 独立 session | `LLMService.run_post_message` 创建 `async_session()`，与请求 session 分离 |
| 4 | 集成代码位置 | Router 层 `BackgroundTasks.add_task()` | 与 sessions 已有模式一致，Service 保持单一职责 |
| 5 | LLM / Embedding 配置分离 | 独立 `config.llm` + `config.embedding` 两块 | 兼容不同 Provider（如 Chat 用 DeepSeek、Embedding 用 GITEE AI） |
| 6 | VECTOR 维度约束 | 移除固定 1536 维 → `VECTOR`（无维度） | 不同 Provider 返回不同维度（OpenAI=1536, GITEE=1024） |
| 7 | memory_fragments.embedding 写入 | LLMService 为 fragment 生成 embedding | 闭合 IVFFlat 索引 ↔ 写入的 gap |

### 实际产出

#### 8.1 `src/llm/__init__.py` (8 行)
重导出 `LLMProvider`, `TextEmbedder`, `SessionSummarizer`, `MemoryExtractor`, `MemoryFragmentData`

#### 8.2 `src/llm/provider.py` (50 行)
- `LLMProvider._semaphore` — 类级 `asyncio.Semaphore(5)`
- 每 `chat()` 调用 `async with httpx.AsyncClient(...)` — 自动清理
- `chat()` 返回 `str | None`，异常兜底 `logger.warning`
- 无 `self.http` — 不创建实例级 client

#### 8.3 `src/llm/embedder.py` (35 行)
- `TextEmbedder(provider, embedding_model)`
- 通过 `LLMProvider._semaphore` 控制并发
- 每 `embed()` 调用新建 `httpx.AsyncClient`
- 返回 `list[float] | None`

#### 8.4 `src/llm/summarizer.py` (25 行)
- `SessionSummarizer(provider)`
- `summarize(messages: list[dict]) → str | None`

#### 8.5 `src/llm/extractor.py` (45 行)
- `MemoryExtractor(provider)`
- 返回 `ExtractionResult` TypedDict: `{fragments: [...], profile_updates: {...}}`
- JSON 解析失败兜底返回空结果

#### 8.6 `src/services/llm_service.py` (120 行)
- `LLMService.run_post_message(session_id, message_id, content, agent_id, user_id)` — 静态方法
- 独立 `async_session()` — 不依赖请求 session
- **LLM / Embedding 分离** — `config.llm` 创建 `chat_provider`，`config.embedding` 创建 `embed_provider`
  - `embed_config` 为空时 fallback 到 `llm_config`（向后兼容）
  - `LLMProvider.__init__` 自动剥离 base_url 末尾 `/v1`（支持 GITEE AI 等含 `/v1` 的 URL）
- 降级：`api_key` 为空 → 立即 return
- **memory_fragment embedding gap 修复**: 每创建 fragment 时调用 `embedder.embed(frag["content"])` 写入 `embedding` 列
- 写入 `messages.embedding` / `sessions.summary` / `memory_fragments` / `users.profile`

#### 8.7 数据库 schema 变更
- `VECTOR(1536)` → `VECTOR` 无维度约束 — `src/models/database.py`, `docker/init.sql`
- 完整流程：查 Agent 配置 → embed message → 超阈值(40条)时 summarize + extract
- 写入 `messages.embedding` / `sessions.summary` / `memory_fragments` / `users.profile`

#### 8.7 修改 `src/routers/sessions.py`
- 导入 `BackgroundTasks`, `LLMService`
- `add_message` 端点注入 `background_tasks: BackgroundTasks`
- 消息写入后调用 `background_tasks.add_task(LLMService.run_post_message, ...)`

### 验证结果

**降级测试（无 API Key）：**
- Agent 无 llm.config → Session + Message 正常创建 (200) ✓
- `LLMService.run_post_message` 检测 `api_key` 为空 → 立即 return ✓
- `messages.embedding` 为 NULL ✓

**全功能测试（DeepSeek Chat + GITEE AI Embedding）：**
- `messages.embedding`: YES (1024d) ✓
- `sessions.summary`: YES (DeepSeek 生成) ✓
- `memory_fragments`: 1 条, embedding=YES (1024d) ✓ — gap 已修复
- `users.profile`: 已更新 ✓
- LLM/Embedding 分离配置正常工作 ✓

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
