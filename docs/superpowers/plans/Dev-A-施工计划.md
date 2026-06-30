# Dev A 施工计划

> **负责模块:** 数据库基础、高阶 SQL 对象、Session/Message API、Context API、App 组装、集成验证
> **关联:** `docs/superpowers/plans/总体施工计划.md`

---

## 依赖概览

```
Task 2 ─→ Task 3 ─→ Task 6 ─→ Task 7 ─→ Task 9 ─→ Task 12
 (DB)     (SQL)    (Session)  (Context)  (组装)    (验证)
```

- Task 2 产出是其他人（Dev B/C）的依赖，需优先交付
- Task 7 依赖 Dev B 的 Task 4 和 Dev C 的 Task 5，需等待他们完成后再汇集

---

# Task 2: 数据库基础

**预估:** 2h | **产出:** 4 个文件

## 2.1 创建 src/config.py

```python
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://memory:memorypass@localhost:5432/memorydb",
)
MEMORY_API_KEY = os.getenv("MEMORY_API_KEY", "")
MAX_SESSION_TURNS = int(os.getenv("MAX_SESSION_TURNS", "20"))
USER_MEMORY_TOP_K = int(os.getenv("USER_MEMORY_TOP_K", "5"))
```

## 2.2 创建 src/database.py

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
```

## 2.3 创建 src/models/database.py

实现 8 张表的 SQLAlchemy ORM 模型：

| 表名 | 关键字段 |
|------|---------|
| `Agent` | agent_id, name, persona, config(JSONB), status |
| `Skill` | skill_id(UUID), name, trigger_keys(ARRAY), prompt_snippet |
| `SkillAgent` | skill_id(FK), agent_id(FK), enabled |
| `User` | user_id, external_id, profile(JSONB) |
| `MemoryFragment` | fragment_id(UUID), user_id(FK), type, content, embedding(VECTOR), importance |
| `Session` | session_id, agent_id(FK), user_id(FK), status, message_count, summary |
| `Message` | message_id(UUID), session_id(FK), role, content, embedding(VECTOR) |
| `AuditLog` | log_id(BIGSERIAL), table_name, operation, record_id, old_data(JSONB), new_data(JSONB) |
| `MemoryArchive` | archive_id(UUID), fragment_id, user_id, content, reason |

参考 `docs/设计.md` 第三章 DDL 逐字段映射。

## 2.4 创建 docker/init.sql

将 DDL（设计文档 §三）写入 `docker/init.sql`，包含：
- `CREATE EXTENSION vector;`
- `CREATE EXTENSION pgcrypto;`
- 全部 9 张表的 `CREATE TABLE`
- 6 个 `CREATE INDEX`

## 2.5 验证

```bash
# 启动 PostgreSQL
docker compose up db -d
# 检查数据库
docker compose exec db psql -U memory -d memorydb -c "\dt"
# 预期: 列出 9 张表
```

**完成状态:** ✅ 已完成 (2026-06-29)

**实际产出:**
- `src/__init__.py` + `src/models/__init__.py` — Python 包标记
- `src/config.py` — 6 个环境变量，含 `python-dotenv` 加载
- `src/database.py` — `DeclarativeBase` + async engine (pool_size=20) + `get_db` 依赖注入
- `src/models/database.py` — 9 张表 ORM 模型:
  - 使用 `pgvector.sqlalchemy.Vector` 类型（无维度约束，MemoryFragment / Message）
  - 仅定义 `ForeignKey`，不定义 `relationship()`（避免 async lazy loading）
  - UUID 主键使用 `gen_random_uuid()`
  - `AuditLog` 使用 `BigInteger` + `Identity()`
- `docker/init.sql` — 完整 DDL + 8 个自定义索引（含 IVFFlat、GIN）

**验证结果:**
- `uv run python -c "from src.models.database import ..."` — 9 个模型导入成功
- `docker compose exec db psql ... -c "\dt"` — 9 张表完整创建
- `docker compose exec db psql ... -c "\di"` — 17 个索引（9 PK + 8 自定义）
- `vector` + `pgcrypto` 扩展已启用
- ORM ↔ DB 往返测试: Agent/Skill/User/Session/Message/MemoryFragment 全部 CRUD 通过
- pgvector embedding 列: `list[float]` → DB → `list[float]` 往返正确
- `docker-compose.yml` 端口改为 `5433:5432`（系统 PG 占用 5432）

---

# Task 3: 高阶 SQL 对象

**预估:** 2h | **依赖:** Task 2 完成

## 3.1 存储过程 sp_compose_context

追加到 `docker/init.sql`：

```sql
CREATE OR REPLACE FUNCTION sp_compose_context(
    p_agent_id VARCHAR(64),
    p_user_id VARCHAR(64),
    p_session_id VARCHAR(64),
    p_top_k INT DEFAULT 5
) RETURNS JSONB AS $$
DECLARE
    v_agent_config JSONB;
    v_persona TEXT;
    v_skills JSONB;
    v_profile JSONB;
    v_fragments JSONB;
    v_messages JSONB;
    v_summary TEXT;
    v_result JSONB;
BEGIN
    -- Step A: Agent 记忆
    SELECT persona, config INTO v_persona, v_agent_config
    FROM agents WHERE agent_id = p_agent_id;

    SELECT jsonb_agg(jsonb_build_object(
        'skill_id', s.skill_id, 'name', s.name,
        'trigger_keys', s.trigger_keys, 'prompt_snippet', s.prompt_snippet
    )) INTO v_skills
    FROM skills s
    JOIN skill_agents sa ON s.skill_id = sa.skill_id
    WHERE sa.agent_id = p_agent_id AND sa.enabled = TRUE;

    -- Step B: User 记忆
    SELECT profile INTO v_profile FROM users WHERE user_id = p_user_id;

    SELECT jsonb_agg(jsonb_build_object(
        'fragment_id', fragment_id, 'type', type,
        'content', content, 'importance', importance
    ) ORDER BY importance DESC) INTO v_fragments
    FROM (
        SELECT * FROM memory_fragments
        WHERE user_id = p_user_id
        ORDER BY importance DESC, created_at DESC
        LIMIT p_top_k
    ) sub;

    -- Step C: Session 记忆
    SELECT summary INTO v_summary FROM sessions WHERE session_id = p_session_id;

    SELECT jsonb_agg(sub) INTO v_messages
    FROM (
        SELECT message_id, role, content, tool_name, created_at
        FROM messages
        WHERE session_id = p_session_id
        ORDER BY created_at
        LIMIT COALESCE((v_agent_config->>'max_session_turns')::INT, 20)
    ) sub;

    -- Step D: 组装
    v_result := jsonb_build_object(
        'agent_memory', jsonb_build_object(
            'agent_id', p_agent_id, 'persona', v_persona,
            'skills', COALESCE(v_skills, '[]'::JSONB)
        ),
        'user_memory', jsonb_build_object(
            'profile', COALESCE(v_profile, '{}'::JSONB),
            'fragments', COALESCE(v_fragments, '[]'::JSONB)
        ),
        'session_memory', jsonb_build_object(
            'session_id', p_session_id,
            'summary', COALESCE(to_jsonb(v_summary), 'null'::JSONB),
            'messages', COALESCE(v_messages, '[]'::JSONB)
        )
    );

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;
```

## 3.2 触发器 tg_audit_log

```sql
CREATE OR REPLACE FUNCTION tg_audit_log() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_log(table_name, operation, record_id, new_data, performed_by)
        VALUES (TG_TABLE_NAME, TG_OP, NEW.fragment_id::TEXT, to_jsonb(NEW), current_user);
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_log(table_name, operation, record_id, old_data, new_data, performed_by)
        VALUES (TG_TABLE_NAME, TG_OP, NEW.fragment_id::TEXT, to_jsonb(OLD), to_jsonb(NEW), current_user);
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_log(table_name, operation, record_id, old_data, performed_by)
        VALUES (TG_TABLE_NAME, TG_OP, OLD.fragment_id::TEXT, to_jsonb(OLD), current_user);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_memory_fragments
    AFTER INSERT OR UPDATE OR DELETE ON memory_fragments
    FOR EACH ROW EXECUTE FUNCTION tg_audit_log();

CREATE TRIGGER trg_audit_messages
    AFTER INSERT OR UPDATE OR DELETE ON messages
    FOR EACH ROW EXECUTE FUNCTION tg_audit_log();
```

## 3.3 触发器 tg_check_message_threshold

```sql
CREATE OR REPLACE FUNCTION tg_check_message_threshold() RETURNS TRIGGER AS $$
DECLARE
    v_threshold INT;
    v_count INT;
BEGIN
    SELECT (config->>'max_session_turns')::INT * 2 INTO v_threshold
    FROM agents WHERE agent_id = (SELECT agent_id FROM sessions WHERE session_id = NEW.session_id);

    -- 默认阈值
    IF v_threshold IS NULL THEN v_threshold := 40; END IF;

    SELECT COUNT(*) INTO v_count FROM messages WHERE session_id = NEW.session_id;

    -- 如果消息数超过阈值，插入审计日志作为标记
    IF v_count > v_threshold THEN
        INSERT INTO audit_log(table_name, operation, record_id, new_data, performed_by)
        VALUES ('messages', 'THRESHOLD', NEW.session_id,
                jsonb_build_object('message_count', v_count, 'threshold', v_threshold),
                'system');
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_threshold
    AFTER INSERT ON messages
    FOR EACH ROW EXECUTE FUNCTION tg_check_message_threshold();
```

## 3.4 视图 v_context_preview 和 v_memory_stats

```sql
CREATE OR REPLACE VIEW v_context_preview AS
SELECT
    s.session_id, s.agent_id, s.user_id, s.message_count, s.summary,
    a.name AS agent_name, a.status AS agent_status,
    u.profile AS user_profile,
    COUNT(f.fragment_id) AS memory_fragment_count
FROM sessions s
LEFT JOIN agents a ON s.agent_id = a.agent_id
LEFT JOIN users u ON s.user_id = u.user_id
LEFT JOIN memory_fragments f ON s.user_id = f.user_id
GROUP BY s.session_id, s.agent_id, s.user_id, s.message_count, s.summary,
         a.name, a.status, u.profile;

CREATE OR REPLACE VIEW v_memory_stats AS
SELECT
    u.user_id,
    COUNT(f.fragment_id) AS total_fragments,
    AVG(f.importance) AS avg_importance,
    COUNT(DISTINCT f.type) AS type_count,
    MAX(f.created_at) AS last_memory_at
FROM users u
LEFT JOIN memory_fragments f ON u.user_id = f.user_id
GROUP BY u.user_id;
```

## 3.5 验证

```bash
docker compose down -v && docker compose up db -d
docker compose exec db psql -U memory -d memorydb -c "\df sp_compose_context"
docker compose exec db psql -U memory -d memorydb -c "\dv"
docker compose exec db psql -U memory -d memorydb -c "SELECT * FROM pg_trigger WHERE tgname LIKE 'trg_%';"
```

**完成状态:** ✅ 已完成 (2026-06-29)

**实际产出:**
- `docker/init.sql` 追加 191 行：1 存储过程 + 2 触发器函数 + 3 触发器 + 2 视图
- `sp_compose_context` — 三步读取三层记忆，组装 JSONB 返回
- `tg_audit_log` — 通用 DML 审计触发器函数，根据 TG_TABLE_NAME 动态选择主键列
- `trg_audit_memory_fragments` + `trg_audit_messages` — 两个审计触发器
- `tg_check_message_threshold` + `trg_check_threshold` — 消息超阈值标记触发器
- `v_context_preview` — 多表 JOIN 上下文预览视图
- `v_memory_stats` — 每用户记忆统计视图

**Bug 修复:**
- tg_audit_log: 计划代码硬编码 `fragment_id`，messages 表无此列，改为根据表名动态选择主键
- tg_check_message_threshold: 计划代码写入 `'THRESHOLD'`(9字符) 超出 `audit_log.operation VARCHAR(8)` 限制，改为 `'THRESH'`

**后续增强 (2026-06-30):**
- `sp_compose_context` 新增 `p_query_embedding VECTOR` 可选参数（LLM 向量检索汇入点）
- Session 记忆输出新增 `message_count` 字段（设计文档 API 约定）
- VECTOR 类型去除 1536 维度锁定，兼容任意维度 embedding

**验证结果:** 本地 PostgreSQL + pgvector 实测，存储过程三层 JSON 返回正确，3 触发器正常触发，2 视图查询正确。

---

# Task 6: Session & Message API

**预估:** 3h | **依赖:** Task 2 完成

## 6.1 创建 src/services/session_service.py

```python
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from src.models.database import Session, Message

class SessionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(self, agent_id: str, user_id: str, session_id: str = None) -> Session:
        session = Session(
            session_id=session_id or f"sess_{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            user_id=user_id,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_session(self, session_id: str) -> Session | None:
        result = await self.db.execute(select(Session).where(Session.session_id == session_id))
        return result.scalar_one_or_none()

    async def update_session_status(self, session_id: str, status: str) -> Session | None:
        session = await self.get_session(session_id)
        if session:
            session.status = status
            await self.db.commit()
            await self.db.refresh(session)
        return session

    async def add_message(self, session_id: str, role: str, content: str,
                          tool_name: str = None, tool_call_id: str = None) -> Message:
        message = Message(
            message_id=uuid.uuid4(),
            session_id=session_id,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )
        self.db.add(message)
        # 更新计数器
        await self.db.execute(
            update(Session).where(Session.session_id == session_id)
            .values(message_count=Session.message_count + 1, updated_at=func.now())
        )
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get_messages(self, session_id: str, limit: int = 50) -> list[Message]:
        result = await self.db.execute(
            select(Message).where(Message.session_id == session_id)
            .order_by(Message.created_at).limit(limit)
        )
        return list(result.scalars().all())
```

## 6.2 创建 src/routers/sessions.py

实现 5 个端点，Pydantic schema 参考 `docs/设计.md` §四：
- `POST /api/v1/sessions` — `SessionCreate(agent_id, user_id, session_id?)` → `SessionResponse`
- `GET /api/v1/sessions/{session_id}` — 返回 Session + message_count + summary
- `PATCH /api/v1/sessions/{session_id}` — `SessionUpdate(status)` → 响应
- `POST /api/v1/sessions/{session_id}/messages` — `MessageCreate(role, content, ...)` → `MessageResponse`
- `GET /api/v1/sessions/{session_id}/messages?limit=50` — 返回消息列表

**完成状态:** ✅ 已完成 (2026-06-29)

**实际产出:**
- `src/services/session_service.py` — SessionService 类 5 方法
- `src/routers/sessions.py` — 5 Pydantic schema + 5 REST 端点

**关键实现:**
- `create_session`: 自动生成 `sess_{12位hex}` 格式 session_id
- `add_message`: INSERT message + UPDATE `message_count` 自增（`Session.message_count + 1`，SQL 原子操作）
- Router 层 404 保护：操作不存在 session 返回 404 而非 500 FK 错误
- `MessageResponse.message_id` 使用 `uuid.UUID` 类型（配合 `from_attributes=True`）

**后续集成 (2026-06-30):**
- Dev B LLM 模块集成：`add_message` 端点增加 `BackgroundTasks` 触发 `LLMService.run_post_message`

**验证结果:** 全 6 个 HTTP 端点测试通过（ASGI 传输 + uvicorn），计数器原子自增正确，404 处理正确。

---

# Task 7: Context Composition API

**预估:** 2h | **依赖:** Task 4 (Dev B), Task 5 (Dev C), Task 6 完成

## 7.1 创建 src/services/context_service.py

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

class ContextService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def compose_context(self, agent_id: str, user_id: str,
                              session_id: str, query: str = None,
                              top_k: int = 5) -> dict:
        stmt = text("SELECT sp_compose_context(:agent_id, :user_id, :session_id, :top_k)")
        result = await self.db.execute(stmt, {
            "agent_id": agent_id, "user_id": user_id,
            "session_id": session_id, "top_k": top_k
        })
        row = result.scalar_one()
        context = row if isinstance(row, dict) else row
        return context
```

## 7.2 创建 src/routers/context.py

实现 `POST /api/v1/context`：
- 接收 `ContextRequest(agent_id, user_id, session_id, query?, options?)`
- 调用 `ContextService.compose_context(...)`
- 返回 `ContextResponse`

**完成状态:** ✅ 已完成 (2026-06-30)

**实际产出:**
- `src/services/context_service.py` — ContextService 类，`compose_context` 方法
- `src/routers/context.py` — 5 Pydantic schema + `POST /api/v1/context` 端点

**关键实现:**
- 双路径设计：`query_embedding` 传入时走向量语义检索，NULL 时走 importance 降级
- `ContextOptions.query_embedding` — LLM 向量检索汇入点
- `AgentMemoryResponse.persona` 为可选字段（agent 不存在时返回 null）
- SQL 向量字面量拼接 `ARRAY[...]::vector`（安全：仅浮点数列表）

**Pydantic Schema:**
- `ContextRequest`: agent_id, user_id, session_id, query?, options?
- `ContextOptions`: max_session_turns(20), user_memory_top_k(5), include_skills(true), include_profile(true), query_embedding?
- `ContextResponse`: agent_memory + user_memory + session_memory 三层嵌套

**验证结果:** 全 4 场景测试通过：完整三层上下文 / 最小请求 / 不存在 ID 优雅降级 / Top-K 限制。

---

# Task 9: FastAPI App 组装

**预估:** 1h | **依赖:** Task 4, 5, 6, 7 完成

## 9.1 创建 src/main.py

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from src.routers import agents, skills, sessions, users, context, admin

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="Agent Memory Manager", version="1.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(agents.router, prefix="/api/v1")
app.include_router(skills.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(context.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")

app.mount("/debug", StaticFiles(directory="src/static", html=True), name="debug")
```

## 9.2 API Key 中间件

在 `src/main.py` 中加入：如果 `MEMORY_API_KEY` 不为空，校验 `X-API-Key` 或 `Authorization: Bearer` header。

**完成状态:** ✅ 已完成 (2026-06-30)

**实际产出:**
- `src/main.py` — 完整 FastAPI 应用组装
- `src/routers/admin.py` — health + stats 管理端点

**main.py 组装内容:**
- 注册全部 5 个 router: agents, skills, sessions, context, admin（users 待 Dev C）
- CORS 中间件 (`allow_origins=["*"]`)
- API Key 认证中间件（`X-API-Key` / `Authorization: Bearer`，空 `MEMORY_API_KEY` 时跳过）
- `/debug` 路由直接返回 `static/debug.html`
- lifespan 上下文管理器

**admin.py 端点:**
- `GET /api/v1/health` — 返回 `{"status":"ok","pgvector":true/false}`
- `GET /api/v1/stats` — 返回 `v_memory_stats` 视图的每用户记忆统计

**设计偏差:**
- 原计划用 `StaticFiles(app.mount)` 服务 debug.html，实际使用 `@app.get("/debug")` + `FileResponse`（避免 Starlette mount 与路由冲突）
- `config.py` 经设计变更移除 `EMBEDDING_DIM`，VECTOR 类型去除维度约束

**验证结果:** 全链路 uvicorn + curl 测试通过：health/stats/agents/skills/sessions/context/debug 全部返回正确。

---

# Task 12: 集成验证

**执行: 全体 / 预估: 2h**

按 `总体施工计划.md` Task 12 的验证清单逐项执行，记录结果。
