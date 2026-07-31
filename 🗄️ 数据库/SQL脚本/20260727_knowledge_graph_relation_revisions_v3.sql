-- 知识图谱关系修订 v3：追加版本链字段，不覆盖原知识表或产品矩阵。
-- 执行前必须备份 kg_edges 和 kg_edge_events。

BEGIN;

ALTER TABLE kg_edges ADD COLUMN IF NOT EXISTS supersedes_edge_id uuid;
ALTER TABLE kg_edges ADD COLUMN IF NOT EXISTS revision_no integer NOT NULL DEFAULT 1;
ALTER TABLE kg_edges ADD COLUMN IF NOT EXISTS revision_kind text NOT NULL DEFAULT 'original';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'kg_edges'::regclass
          AND conname = 'fk_kg_edges_supersedes'
    ) THEN
        ALTER TABLE kg_edges
            ADD CONSTRAINT fk_kg_edges_supersedes
            FOREIGN KEY (supersedes_edge_id) REFERENCES kg_edges(edge_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'kg_edges'::regclass
          AND conname = 'chk_kg_edges_revision_no'
    ) THEN
        ALTER TABLE kg_edges
            ADD CONSTRAINT chk_kg_edges_revision_no CHECK (revision_no >= 1);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'kg_edges'::regclass
          AND conname = 'chk_kg_edges_revision_kind'
    ) THEN
        ALTER TABLE kg_edges
            ADD CONSTRAINT chk_kg_edges_revision_kind
            CHECK (revision_kind IN ('original', 'human_adjustment', 'source_revalidation'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_kg_edges_supersedes ON kg_edges(supersedes_edge_id);
CREATE INDEX IF NOT EXISTS idx_kg_edges_effective
    ON kg_edges(review_status, revision_kind, updated_at DESC)
    WHERE valid_to IS NULL;

COMMIT;
