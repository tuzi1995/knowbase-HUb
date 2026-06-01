-- ==========================================
-- 创建 knowledge_base_modifications 表
-- ==========================================
-- 
-- 如果你的数据库中没有这个表，可以运行此脚本创建
-- 这个表用于记录知识库的修改历史
--
-- ==========================================

-- 启用 UUID 扩展
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 创建修改记录表
CREATE TABLE IF NOT EXISTS knowledge_base_modifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kb_id TEXT NOT NULL,
    question_wiki_id TEXT,
    product_name TEXT,
    question TEXT,
    answer TEXT,
    similar_questions JSONB,
    keyword_list JSONB,
    image_urls JSONB,
    video_urls JSONB,
    file_urls JSONB,
    link_type TEXT,
    link_url TEXT,
    change_meta JSONB,
    modification_time TIMESTAMPTZ DEFAULT NOW(),
    change_type TEXT DEFAULT 'edit', -- 'edit' or 'delete'
    modifier TEXT,
    question_type TEXT,
    answer_type TEXT,
    error_list JSONB,
    if_bm25 BOOLEAN
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_kb_mod_kb_id ON knowledge_base_modifications (kb_id);
CREATE INDEX IF NOT EXISTS idx_kb_mod_time ON knowledge_base_modifications (modification_time DESC);
CREATE INDEX IF NOT EXISTS idx_kb_mod_modifier ON knowledge_base_modifications (modifier);
CREATE INDEX IF NOT EXISTS idx_kb_mod_change_type ON knowledge_base_modifications (change_type);

-- 启用 RLS
ALTER TABLE knowledge_base_modifications ENABLE ROW LEVEL SECURITY;

-- 创建策略
DO $$
BEGIN
    CREATE POLICY "Allow all operations for anon" ON knowledge_base_modifications
    FOR ALL USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

-- 授权
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE knowledge_base_modifications TO anon, authenticated;

-- 完成提示
DO $$
BEGIN
    RAISE NOTICE '✅ knowledge_base_modifications 表创建完成！';
    RAISE NOTICE '📊 表结构：';
    RAISE NOTICE '   - 主键：id (UUID)';
    RAISE NOTICE '   - 外键：kb_id (关联知识库ID)';
    RAISE NOTICE '   - 索引：4个索引已创建';
    RAISE NOTICE '';
    RAISE NOTICE '🎉 现在可以运行索引优化脚本了！';
END $$;
