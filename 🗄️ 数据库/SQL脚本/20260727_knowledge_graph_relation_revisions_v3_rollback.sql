-- 关系修订 v3 回退：存在修订历史时主动失败，不删边、不删事件。

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM kg_edges
        WHERE supersedes_edge_id IS NOT NULL
           OR revision_no <> 1
           OR revision_kind <> 'original'
    ) THEN
        RAISE EXCEPTION '仍存在人工修订或重新复核版本，请使用迁移前备份恢复，避免丢失审计记录';
    END IF;
END $$;

DROP INDEX IF EXISTS idx_kg_edges_effective;
DROP INDEX IF EXISTS idx_kg_edges_supersedes;
ALTER TABLE kg_edges DROP CONSTRAINT IF EXISTS fk_kg_edges_supersedes;
ALTER TABLE kg_edges DROP CONSTRAINT IF EXISTS chk_kg_edges_revision_no;
ALTER TABLE kg_edges DROP CONSTRAINT IF EXISTS chk_kg_edges_revision_kind;
ALTER TABLE kg_edges DROP COLUMN IF EXISTS supersedes_edge_id;
ALTER TABLE kg_edges DROP COLUMN IF EXISTS revision_no;
ALTER TABLE kg_edges DROP COLUMN IF EXISTS revision_kind;

COMMIT;
