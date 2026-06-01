
-- Create knowledge_base_modifications table if it doesn't exist
CREATE EXTENSION IF NOT EXISTS pgcrypto;

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
    change_type TEXT DEFAULT 'edit' -- 'edit' or 'delete'
);

ALTER TABLE IF EXISTS knowledge_base_modifications
    ADD COLUMN IF NOT EXISTS modifier TEXT,
    ADD COLUMN IF NOT EXISTS question_type TEXT,
    ADD COLUMN IF NOT EXISTS answer_type TEXT,
    ADD COLUMN IF NOT EXISTS error_list JSONB,
    ADD COLUMN IF NOT EXISTS if_bm25 BOOLEAN,
    ADD COLUMN IF NOT EXISTS change_meta JSONB;

-- Add review_status column to KB table (兼容不同版本表名)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'knowledge_base_v1'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'knowledge_base_v1' AND column_name = 'review_status'
        ) THEN
            ALTER TABLE public.knowledge_base_v1 ADD COLUMN review_status TEXT DEFAULT 'unadjusted';
        END IF;
        UPDATE public.knowledge_base_v1 SET review_status = 'unadjusted' WHERE review_status IS NULL;
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'knowledge_base'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'knowledge_base' AND column_name = 'review_status'
        ) THEN
            ALTER TABLE public.knowledge_base ADD COLUMN review_status TEXT DEFAULT 'unadjusted';
        END IF;
        UPDATE public.knowledge_base SET review_status = 'unadjusted' WHERE review_status IS NULL;
    END IF;
END $$;

-- Update KB schema: split urls and remove answer_info (knowledge_base_v1 + knowledge_base_v1_t1)
ALTER TABLE IF EXISTS knowledge_base_v1
    ADD COLUMN IF NOT EXISTS image_urls JSONB,
    ADD COLUMN IF NOT EXISTS video_urls JSONB,
    ADD COLUMN IF NOT EXISTS file_urls JSONB,
    ADD COLUMN IF NOT EXISTS link_type TEXT,
    ADD COLUMN IF NOT EXISTS link_url TEXT;

ALTER TABLE IF EXISTS knowledge_base_v1
    DROP COLUMN IF EXISTS answer_info,
    DROP COLUMN IF EXISTS urls;

ALTER TABLE IF EXISTS knowledge_base_v1_t1
    ADD COLUMN IF NOT EXISTS image_urls JSONB,
    ADD COLUMN IF NOT EXISTS video_urls JSONB,
    ADD COLUMN IF NOT EXISTS file_urls JSONB,
    ADD COLUMN IF NOT EXISTS link_type TEXT,
    ADD COLUMN IF NOT EXISTS link_url TEXT;

ALTER TABLE IF EXISTS knowledge_base_v1_t1
    DROP COLUMN IF EXISTS answer_info,
    DROP COLUMN IF EXISTS urls;
