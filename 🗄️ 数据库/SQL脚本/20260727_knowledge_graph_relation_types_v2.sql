-- 知识图谱关系类型 v2：只扩展旁路边的 CHECK 约束。
-- 执行前必须备份 kg_edges 和 kg_edge_events。

BEGIN;

DO $$
DECLARE
    constraint_record record;
BEGIN
    FOR constraint_record IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'kg_edges'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) LIKE '%relation_type%'
    LOOP
        EXECUTE format('ALTER TABLE kg_edges DROP CONSTRAINT %I', constraint_record.conname);
    END LOOP;
END $$;

ALTER TABLE kg_edges
    ADD CONSTRAINT chk_kg_edges_relation_type_v2
    CHECK (relation_type IN (
        'APPLIES_TO', 'BELONGS_TO', 'RELATED_TO', 'OVERLAPS_WITH', 'DUPLICATES',
        'SPECIALIZES', 'EXCEPTION_TO', 'CONFLICTS_WITH', 'PARENT_TOPIC_OF',
        'ROUTES_TO', 'PREREQUISITE_FOR', 'SUBPROCEDURE_OF'
    ));

COMMIT;
