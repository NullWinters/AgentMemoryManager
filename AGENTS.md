# AGENTS.md — Agent Memory Manager

## 环境与命令

- **Python 环境**：使用 `uv` 管理依赖，`.venv` 位于项目根目录。安装/运行用 `uv pip install`、`uv run`。
- **启动全部服务**：`docker compose up -d`（PostgreSQL + API，宿主机映射 8080）。
- **本地开发**：需先启动 `docker compose up -d db`，然后复制 `.env.example` 为 `.env`（注意本地 DATABASE_URL 端口为 5433），最后 `uv run uvicorn src.main:app --reload --port 8000`。
- **安装 SDK**：`uv pip install agentmemory-client-nullwinters`
- **健康检查**：`curl http://localhost:8080/api/v1/health`
- **调试控制台**：浏览器访问 `http://localhost:8080/debug`
- **依赖锁定**：`requirements.txt` 由 `uv export --format requirements-txt --no-hashes -o requirements.txt` 自动生成，**不要手动编辑**。

## 架构要点

- **三层记忆**：Session（会话上下文）→ User（跨会话画像+语义检索片段）→ Agent（人设+Skill）
- **入口点**：`src/main.py` — FastAPI app，含 CORS（允许所有源）和可选的 API Key 中间件。
- **路由层**：`src/routers/` 下每个文件是一个 `APIRouter`，前缀统一为 `/api/v1`。
- **服务层**：`src/services/` 下每个 `XxxService` 接受 `AsyncSession` 构造，不持有全局状态。
- **ORM 模型**：`src/models/database.py`，基类来自 `src/database.py:Base`。
- **LLM 模块**：`src/llm/` — `LLMProvider`（OpenAI 兼容）、`TextEmbedder`、`SessionSummarizer`、`MemoryExtractor`。LLM 完全可选，无 API key 时静默跳过。
- **核心查询**：上下文组合通过 PostgreSQL 存储过程 `sp_compose_context`（见 `docker/init.sql`）完成，不是 Python 代码。
- **SDK**：`sdk/agentmemory/` — 同步 `requests` 客户端，三层记忆结构（`context.py`）。

## 数据库

- PostgreSQL 16 + pgvector + pgcrypto，DDL 在 `docker/init.sql`，Docker 首次启动自动执行。
- 连接池：pool_size=40, max_overflow=20。
- 向量索引需有数据后手动创建（见 `init.sql` 注释中的 CREATE INDEX 语句）。
- 表结构变更后需重建 volume：`docker compose down -v && docker compose up -d`。

## 约定

- 路由中统一用辅助函数 `_service(db)` 构造服务、`_not_found(entity)` 抛 404。
- API key 通过 `X-API-Key` 头或 `Authorization: Bearer <key>` 传递，在 `src/config.py:10` 的 `MEMORY_API_KEY` 配置。
- 后台任务（LLM 摘要/提取/嵌入）在消息 POST 接口通过 FastAPI `BackgroundTasks` 触发。
- 无 CI/CD、无测试套件、无 linter — 验证靠 `docker compose up` + curl / 调试控制台。
