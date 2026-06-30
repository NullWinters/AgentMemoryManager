# Agent Memory Manager

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-✓-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green)](./LICENSE)

面向 **LangChain / LangGraph** 开发者的 AI Agent 三层记忆管理微服务。将记忆管理从业务逻辑中解耦，提供自动化的长短期记忆注入接口。

---

## 特性

- **三层记忆模型** — 会话记忆（对话上下文）+ 用户记忆（跨会话画像）+ Agent 记忆（Skill/人设）
- **Docker 一键部署** — `docker compose up -d`，零环境配置
- **可选 LLM 增强** — 兼容 OpenAI API 格式，自动摘要/记忆提取/向量嵌入，未配置时自动降级
- **Python SDK** — 3 行初始化，2 行注入上下文，1 行传给 LLM
- **pgvector 语义检索** — 余弦相似度 + 全文检索双模式
- **调试控制台** — 单页 HTML，上下文预览 / 记忆检索 / LLM 日志

---

## 快速开始

```bash
# 1. 启动服务
git clone https://github.com/NullWinters/AgentMemoryManager.git
cd AgentMemoryManager
docker compose up -d

# 宿主机默认映射 8080→容器 8000（避免与本机 8000 冲突，可在 .env 设置 API_PORT）
curl http://localhost:8080/api/v1/health
# → {"status":"ok","pgvector":true,"llm_enabled":false}

# 3. 安装 SDK
pip install -e sdk/
```

```python
from agentmemory import MemoryClient

client = MemoryClient("http://localhost:8080", api_key="dev-secret")

# 一次性 Setup：注册 Agent + 绑定 Skill
client.setup(agent_id="book_bot", persona="你是书籍推荐助手...")
client.add_skill_to_agent("book_bot", skill_id)

# 开始会话
session = client.session_start(agent_id="book_bot", user_id="zhang")

# 对话循环
session.add_message(role="user", content="推荐一本进阶 Python 书")
ctx = session.inject_context(query="推荐一本进阶 Python 书")

# 三层记忆自动注入 → 直接发给 LLM
response = openai.chat.completions.create(
    model="gpt-4", messages=ctx.to_messages()
)
session.add_message(role="assistant", content=response.choices[0].message.content)
```

---

## API 概览

| 端点 | 说明 |
|------|------|
| `POST /api/v1/context` | **核心**：三层记忆注入 |
| `POST/GET /api/v1/sessions` | 会话管理 |
| `POST/GET /api/v1/sessions/{id}/messages` | 消息追加与查询 |
| `GET/PATCH /api/v1/users/{id}/profile` | 用户画像 |
| `POST/GET/DELETE /api/v1/users/{id}/memories` | 记忆片段管理 |
| `POST/GET/PATCH /api/v1/agents` | Agent 注册与配置 |
| `POST/GET/PATCH/DELETE /api/v1/skills` | Skill 管理 |
| `GET /api/v1/health` | 健康检查 |

完整文档见 [设计.md](./docs/设计.md)。

---

## 调试控制台

浏览器打开 `http://localhost:8080/debug`，提供：

- **Agent Info** — 人设/配置编辑、Skill 开关
- **User Memory** — 画像查看、向量检索/全文检索
- **Session** — 对话历史浏览、模拟消息注入
- **Context Preview** — 模拟 `to_messages()` 输出、Token 估算
- **LLM Logs** — 每次 LLM 调用的 prompt/response 详情

---

## 项目结构

```
├── src/              # FastAPI 微服务源码
│   ├── routers/      # API 路由 (agents/skills/users/sessions/context)
│   ├── services/     # 业务逻辑层
│   ├── models/       # SQLAlchemy ORM 模型
│   ├── llm/          # LLM 模块 (provider/extractor/summarizer/embedder)
│   └── static/       # 调试前端 (debug.html)
├── sdk/              # Python SDK 包
│   └── agentmemory/  # MemoryClient / Session / Context
├── docker/           # init.sql (DDL + 高阶 SQL)
├── docker-compose.yml
├── docs/
│   ├── 设计.md        # 完整设计文档
│   ├── 用户手册.md     # 用户手册
│   └── superpowers/plans/  # 施工计划
```

---

## 技术栈

**Python 3.11+** · **FastAPI** · **PostgreSQL 16** · **pgvector** · **SQLAlchemy 2.0** · **Docker** · **OpenAI API**

---

## 文档

- [设计文档](./docs/设计.md)
- [用户手册](./docs/用户手册.md)
- [总体施工计划](./docs/superpowers/plans/总体施工计划.md)
