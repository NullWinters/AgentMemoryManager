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
    embedding     VECTOR,
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
    embedding     VECTOR,
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

-- ============================================================
-- 存储过程: sp_compose_context
-- 三步走：读 Agent 配置 + 检索用户记忆 + 提取会话消息 → 返回结构化 JSON
-- ============================================================

CREATE OR REPLACE FUNCTION sp_compose_context(
    p_agent_id VARCHAR(64),
    p_user_id VARCHAR(64),
    p_session_id VARCHAR(64),
    p_top_k INT DEFAULT 5,
    p_query_embedding VECTOR(1536) DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_agent_config JSONB;
    v_persona TEXT;
    v_skills JSONB;
    v_profile JSONB;
    v_fragments JSONB;
    v_messages JSONB;
    v_summary TEXT;
    v_message_count INT;
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
    -- 有 query_embedding → 向量语义检索；无 → 按 importance 排序
    SELECT profile INTO v_profile FROM users WHERE user_id = p_user_id;

    IF p_query_embedding IS NOT NULL THEN
        SELECT jsonb_agg(jsonb_build_object(
            'fragment_id', fragment_id, 'type', type,
            'content', content, 'importance', importance,
            'score', 1.0 - (embedding <=> p_query_embedding)
        ) ORDER BY embedding <=> p_query_embedding) INTO v_fragments
        FROM (
            SELECT * FROM memory_fragments
            WHERE user_id = p_user_id AND embedding IS NOT NULL
            ORDER BY embedding <=> p_query_embedding
            LIMIT p_top_k
        ) sub;
    ELSE
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
    END IF;

    -- Step C: Session 记忆
    SELECT summary, message_count INTO v_summary, v_message_count
    FROM sessions WHERE session_id = p_session_id;

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
            'message_count', COALESCE(v_message_count, 0),
            'summary', COALESCE(to_jsonb(v_summary), 'null'::JSONB),
            'messages', COALESCE(v_messages, '[]'::JSONB)
        )
    );

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 触发器函数: tg_audit_log
-- 全表 DML 审计日志记录
-- ============================================================

CREATE OR REPLACE FUNCTION tg_audit_log() RETURNS TRIGGER AS $$
DECLARE
    v_record_id TEXT;
BEGIN
    -- 不同表使用不同的主键列
    IF TG_TABLE_NAME = 'messages' THEN
        v_record_id := NEW.message_id::TEXT;
    ELSE
        v_record_id := NEW.fragment_id::TEXT;
    END IF;

    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_log(table_name, operation, record_id, new_data, performed_by)
        VALUES (TG_TABLE_NAME, TG_OP, v_record_id, to_jsonb(NEW), current_user);
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_log(table_name, operation, record_id, old_data, new_data, performed_by)
        VALUES (TG_TABLE_NAME, TG_OP, v_record_id, to_jsonb(OLD), to_jsonb(NEW), current_user);
    ELSIF TG_OP = 'DELETE' THEN
        IF TG_TABLE_NAME = 'messages' THEN
            v_record_id := OLD.message_id::TEXT;
        ELSE
            v_record_id := OLD.fragment_id::TEXT;
        END IF;
        INSERT INTO audit_log(table_name, operation, record_id, old_data, performed_by)
        VALUES (TG_TABLE_NAME, TG_OP, v_record_id, to_jsonb(OLD), current_user);
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

-- ============================================================
-- 触发器函数: tg_check_message_threshold
-- 消息超阈值标记
-- ============================================================

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
        VALUES ('messages', 'THRESH', NEW.session_id,
                jsonb_build_object('message_count', v_count, 'threshold', v_threshold),
                'system');
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_threshold
    AFTER INSERT ON messages
    FOR EACH ROW EXECUTE FUNCTION tg_check_message_threshold();

-- ============================================================
-- 视图: v_context_preview
-- 封装多表 JOIN 的上下文预览
-- ============================================================

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

-- ============================================================
-- 视图: v_memory_stats
-- 每用户记忆统计
-- ============================================================

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
