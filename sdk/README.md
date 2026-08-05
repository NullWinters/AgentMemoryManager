# agentmemory-client-nullwinters

AgentMemory 微服务的 Python 客户端 SDK。提供三层记忆（会话/用户/Agent）的便捷访问接口。

## 安装

```bash
pip install agentmemory-client-nullwinters
```

## 快速开始

```python
from agentmemory import MemoryClient

client = MemoryClient("http://localhost:8080", api_key="dev-secret")

# 注册 Agent
client.setup(agent_id="book_bot", persona="你是书籍推荐助手")

# 开始会话
session = client.session_start(agent_id="book_bot", user_id="zhang")

# 对话
session.add_message(role="user", content="推荐一本 Python 书")
ctx = session.inject_context(query="推荐一本 Python 书")

# ctx.to_messages() 返回标准 OpenAI 消息格式，可直接传入 LLM
```

## API

| 端点 | 说明 |
|------|------|
| `MemoryClient.setup()` | 注册/更新 Agent |
| `MemoryClient.session_start()` | 创建会话 |
| `Session.add_message()` | 追加消息 |
| `Session.inject_context()` | 注入三层记忆上下文 |
| `MemoryClient.search_user_memories()` | 语义/全文检索用户记忆 |
| `MemoryClient.get_user_profile()` | 获取用户画像 |
| `MemoryClient.health()` | 健康检查 |
