-- ============================================================
-- Agent Memory Manager — Database Initialization
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- Agent 级记忆
-- ============================================================

CREATE TABLE agents (
    agent_id    VARCHAR(64) PRIMARY KEY,
    name        VARCHAR(128) NOT NULL,
    persona     TEXT NOT NULL DEFAULT '',
    config      JSONB NOT NULL DEFAULT '{}',
    status      VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Skills（全局技能定义）
-- ============================================================

CREATE TABLE skills (
    skill_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(128) NOT NULL,
    trigger_keys    TEXT[] NOT NULL DEFAULT '{}',
    prompt_snippet  TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Skill-Agent M:N 启用关系
CREATE TABLE skill_agents (
    skill_id    UUID NOT NULL REFERENCES skills(skill_id) ON DELETE CASCADE,
    agent_id    VARCHAR(64) NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (skill_id, agent_id)
);

-- ============================================================
-- User 级记忆
-- ============================================================

CREATE TABLE users (
    user_id       VARCHAR(64) PRIMARY KEY,
    external_id   VARCHAR(128),
    profile       JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 跨会话用户记忆单元
CREATE TABLE memory_fragments (
    fragment_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    type          VARCHAR(32) NOT NULL DEFAULT 'fact',
    content       TEXT NOT NULL,
    embedding     VECTOR(1536),
    importance    FLOAT4 NOT NULL DEFAULT 0.5,
    source_msg_id UUID,
    accessed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Session 级记忆
-- ============================================================

CREATE TABLE sessions (
    session_id    VARCHAR(64) PRIMARY KEY,
    agent_id      VARCHAR(64) NOT NULL REFERENCES agents(agent_id),
    user_id       VARCHAR(64) NOT NULL REFERENCES users(user_id),
    status        VARCHAR(16) NOT NULL DEFAULT 'active',
    message_count INT NOT NULL DEFAULT 0,
    summary       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE messages (
    message_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    VARCHAR(64) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role          VARCHAR(16) NOT NULL,
    content       TEXT NOT NULL,
    tool_name     VARCHAR(64),
    tool_call_id  VARCHAR(64),
    embedding     VECTOR(1536),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 系统表
-- ============================================================

CREATE TABLE audit_log (
    log_id        BIGSERIAL PRIMARY KEY,
    table_name    VARCHAR(64) NOT NULL,
    operation     VARCHAR(8) NOT NULL,
    record_id     VARCHAR(64) NOT NULL,
    old_data      JSONB,
    new_data      JSONB,
    performed_by  VARCHAR(64),
    performed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE memory_archives (
    archive_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fragment_id   UUID NOT NULL,
    user_id       VARCHAR(64) NOT NULL,
    content       TEXT NOT NULL,
    archived_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason        VARCHAR(32) NOT NULL DEFAULT 'manual'
);

-- ============================================================
-- 索引
-- ============================================================

-- 会话消息时间序查询
CREATE INDEX idx_messages_session_time ON messages(session_id, created_at);

-- 用户记忆查询
CREATE INDEX idx_fragments_user ON memory_fragments(user_id, type);
-- 向量索引：IVFFlat
CREATE INDEX idx_fragments_embedding ON memory_fragments
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
-- 全文检索索引
CREATE INDEX idx_fragments_fts ON memory_fragments
    USING gin (to_tsvector('simple', content));

-- 会话查询
CREATE INDEX idx_sessions_user ON sessions(user_id, status);
CREATE INDEX idx_sessions_agent ON sessions(agent_id, created_at);

-- Skills 关键词匹配
CREATE INDEX idx_skills_trigger ON skills USING gin (trigger_keys);

-- 消息工具查询
CREATE INDEX idx_messages_tool ON messages(session_id, tool_name)
    WHERE tool_name IS NOT NULL;
