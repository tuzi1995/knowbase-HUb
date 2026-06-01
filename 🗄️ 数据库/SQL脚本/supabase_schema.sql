-- 创建知识库 V1 表
CREATE TABLE IF NOT EXISTS knowledge_base_v1 (
    question_wiki_id TEXT PRIMARY KEY,
    question_type TEXT,
    question TEXT,
    answer TEXT,
    answer_type TEXT,
    if_bm25 BOOLEAN,
    similar_questions JSONB,
    error_list JSONB,
    keyword_list JSONB,
    image_urls JSONB,
    video_urls JSONB,
    file_urls JSONB,
    link_type TEXT,
    link_url TEXT,
    update_time TIMESTAMPTZ,
    product_category_name TEXT,
    product_name TEXT
);

-- 创建知识库 V1T-1 表 (结构与 V1 相同)
CREATE TABLE IF NOT EXISTS knowledge_base_v1_t1 (
    question_wiki_id TEXT PRIMARY KEY,
    question_type TEXT,
    question TEXT,
    answer TEXT,
    answer_type TEXT,
    if_bm25 BOOLEAN,
    similar_questions JSONB,
    error_list JSONB,
    keyword_list JSONB,
    image_urls JSONB,
    video_urls JSONB,
    file_urls JSONB,
    link_type TEXT,
    link_url TEXT,
    update_time TIMESTAMPTZ,
    product_category_name TEXT,
    product_name TEXT
);

-- 开启 RLS (Row Level Security)
ALTER TABLE knowledge_base_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_base_v1_t1 ENABLE ROW LEVEL SECURITY;

-- 创建允许所有操作的策略 (注意：这意味着任何拥有 Key 的人都可以操作这两张表)
-- 如果表已存在策略，这可能会报错，可以忽略
CREATE POLICY "Allow all operations for anon" ON knowledge_base_v1
FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow all operations for anon" ON knowledge_base_v1_t1
FOR ALL USING (true) WITH CHECK (true);

-- 创建同步函数：清空 V1T-1 并从 V1 复制数据
CREATE OR REPLACE FUNCTION sync_knowledge_base()
RETURNS void AS $$
BEGIN
    -- 清空目标表
    TRUNCATE TABLE knowledge_base_v1_t1;
    
    -- 插入数据
    INSERT INTO knowledge_base_v1_t1 
    SELECT
        question_wiki_id,
        question_type,
        question,
        answer,
        answer_type,
        if_bm25,
        similar_questions,
        error_list,
        keyword_list,
        image_urls,
        video_urls,
        file_urls,
        link_type,
        link_url,
        update_time,
        product_category_name,
        product_name
    FROM knowledge_base_v1;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS kb_recall (
    id bigserial PRIMARY KEY,
    kb_id text NOT NULL,
    month text NOT NULL,
    recall_count integer DEFAULT 0,
    valid_recall_count integer DEFAULT 0,
    created_at timestamptz DEFAULT now(),
    CONSTRAINT unique_kb_recall_kb_month UNIQUE (kb_id, month)
);

CREATE INDEX IF NOT EXISTS idx_kb_recall_month ON kb_recall (month);
CREATE INDEX IF NOT EXISTS idx_kb_recall_kb_id ON kb_recall (kb_id);

ALTER TABLE kb_recall ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY "Allow all operations for anon" ON kb_recall FOR ALL USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

CREATE TABLE IF NOT EXISTS matrix_column (
    id bigserial PRIMARY KEY,
    product_name text UNIQUE NOT NULL,
    sort_order integer DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_matrix_column_sort_order ON matrix_column (sort_order);

ALTER TABLE matrix_column ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY "Allow all operations for anon" ON matrix_column FOR ALL USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

CREATE TABLE IF NOT EXISTS product_matrix (
    id bigserial PRIMARY KEY,
    question_wiki_id text NOT NULL,
    product_name text NOT NULL,
    is_configured boolean DEFAULT false,
    manual_edit boolean DEFAULT false,
    edit_source text DEFAULT '',
    last_synced_at timestamptz DEFAULT now(),
    question_content text,
    answer_content text,
    update_time text,
    product_category text,
    CONSTRAINT unique_matrix_item UNIQUE (question_wiki_id, product_name)
);

CREATE INDEX IF NOT EXISTS idx_product_matrix_question_wiki_id ON product_matrix (question_wiki_id);
CREATE INDEX IF NOT EXISTS idx_product_matrix_product_name ON product_matrix (product_name);
CREATE INDEX IF NOT EXISTS idx_product_matrix_manual_edit ON product_matrix (manual_edit);

ALTER TABLE product_matrix ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY "Allow all operations for anon" ON product_matrix FOR ALL USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

CREATE TABLE IF NOT EXISTS matrix_submit_operation (
    id bigserial PRIMARY KEY,
    operation_id text UNIQUE NOT NULL,
    status text DEFAULT 'pending',
    attempts integer DEFAULT 0,
    created_by text,
    error_message text,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_matrix_submit_operation_created_at ON matrix_submit_operation (created_at);
CREATE INDEX IF NOT EXISTS idx_matrix_submit_operation_operation_id ON matrix_submit_operation (operation_id);

ALTER TABLE matrix_submit_operation ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY "Allow all operations for anon" ON matrix_submit_operation FOR ALL USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

CREATE TABLE IF NOT EXISTS button (
    id bigserial PRIMARY KEY,
    operation_id text NOT NULL,
    question_wiki_id text NOT NULL,
    product_name text NOT NULL,
    old_is_configured boolean NOT NULL,
    new_is_configured boolean NOT NULL,
    edit_source text DEFAULT '',
    diff_json text,
    submitted_by text,
    submitted_at timestamptz DEFAULT now(),
    CONSTRAINT unique_button_op_item UNIQUE (operation_id, question_wiki_id, product_name)
);

CREATE INDEX IF NOT EXISTS idx_button_operation_id ON button (operation_id);
CREATE INDEX IF NOT EXISTS idx_button_question_wiki_id ON button (question_wiki_id);

ALTER TABLE button ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY "Allow all operations for anon" ON button FOR ALL USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE kb_recall TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE matrix_column TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE product_matrix TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE matrix_submit_operation TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE button TO anon, authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;

CREATE TABLE IF NOT EXISTS ops_library_item (
    id bigserial PRIMARY KEY,
    kind text NOT NULL,
    name text NOT NULL,
    steps text NOT NULL,
    compatible_models text DEFAULT '',
    sort_order integer DEFAULT 0,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    CONSTRAINT unique_ops_kind_name UNIQUE (kind, name)
);

CREATE INDEX IF NOT EXISTS idx_ops_library_item_kind_sort ON ops_library_item (kind, sort_order, id);

ALTER TABLE ops_library_item ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY "Allow all operations for anon" ON ops_library_item FOR ALL USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE ops_library_item TO anon, authenticated;

-- ==========================================
-- KB Tags (kb_tags / kb_item_tags)
-- ==========================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS kb_tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE kb_tags ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    CREATE POLICY "Allow all operations for anon" ON kb_tags
    FOR ALL USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE kb_tags TO anon, authenticated;

CREATE TABLE IF NOT EXISTS kb_item_tags (
    library_type TEXT NOT NULL, -- current / previous
    question_wiki_id TEXT NOT NULL,
    tag_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT unique_kb_item_tags UNIQUE (library_type, question_wiki_id, tag_id)
);

ALTER TABLE kb_item_tags ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    CREATE POLICY "Allow all operations for anon" ON kb_item_tags
    FOR ALL USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE kb_item_tags TO anon, authenticated;

CREATE INDEX IF NOT EXISTS idx_kb_item_tags_library_item ON kb_item_tags (library_type, question_wiki_id);
CREATE INDEX IF NOT EXISTS idx_kb_item_tags_library_tag ON kb_item_tags (library_type, tag_id);
