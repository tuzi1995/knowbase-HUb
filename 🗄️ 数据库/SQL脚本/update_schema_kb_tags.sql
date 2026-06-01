-- KB Tags: kb_tags + kb_item_tags
-- library_type: current (此刻库 V1) / previous (前刻库 V1T-1)

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Global tag dictionary (方案A：tags.name 全局唯一)
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

-- Mapping between KB items and tags
CREATE TABLE IF NOT EXISTS kb_item_tags (
    library_type TEXT NOT NULL,
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

