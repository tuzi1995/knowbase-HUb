-- 关系类型 v2 回退：新关系存在时主动失败，不删边、不删事件。

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM kg_edges
        WHERE relation_type IN ('PREREQUISITE_FOR', 'SUBPROCEDURE_OF')
    ) THEN
        RAISE EXCEPTION '仍存在 v2 流程关系，请使用迁移前备份恢复，避免丢失审计记录';
    END IF;
END $$;

ALTER TABLE kg_edges DROP CONSTRAINT IF EXISTS chk_kg_edges_relation_type_v2;
ALTER TABLE kg_edges
    ADD CONSTRAINT chk_kg_edges_relation_type_v1
    CHECK (relation_type IN (
        'APPLIES_TO', 'BELONGS_TO', 'RELATED_TO', 'OVERLAPS_WITH', 'DUPLICATES',
        'SPECIALIZES', 'EXCEPTION_TO', 'CONFLICTS_WITH', 'PARENT_TOPIC_OF', 'ROUTES_TO'
    ));

COMMIT;
