-- 8085 知识图谱一期：旁路关系层（PostgreSQL / Supabase）
-- 不修改 knowledge_base_v1 或 product_matrix；部署前请先执行对应 rollback 脚本回读验证。

CREATE TABLE IF NOT EXISTS kg_nodes (
    node_id uuid PRIMARY KEY,
    node_type text NOT NULL CHECK (node_type IN ('knowledge', 'product_model', 'product_category', 'topic')),
    business_key text NOT NULL,
    canonical_name text NOT NULL,
    aliases_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    scope_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    claims_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    properties_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_system text NOT NULL,
    source_version text NOT NULL DEFAULT '',
    content_hash text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'deleted')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_kg_nodes_type_key UNIQUE (node_type, business_key)
);

CREATE TABLE IF NOT EXISTS kg_edges (
    edge_id uuid PRIMARY KEY,
    from_node_id uuid NOT NULL REFERENCES kg_nodes(node_id),
    to_node_id uuid NOT NULL REFERENCES kg_nodes(node_id),
    relation_type text NOT NULL CHECK (relation_type IN ('APPLIES_TO', 'BELONGS_TO', 'RELATED_TO', 'OVERLAPS_WITH', 'DUPLICATES', 'SPECIALIZES', 'EXCEPTION_TO', 'CONFLICTS_WITH', 'PARENT_TOPIC_OF', 'ROUTES_TO', 'PREREQUISITE_FOR', 'SUBPROCEDURE_OF')),
    evidence_json jsonb NOT NULL,
    scope_basis_json jsonb NOT NULL,
    confidence numeric(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    review_status text NOT NULL DEFAULT 'candidate' CHECK (review_status IN ('candidate', 'confirmed', 'rejected', 'expired')),
    generated_by text NOT NULL CHECK (generated_by IN ('source_field', 'rule', 'ai', 'human')),
    provenance_json jsonb NOT NULL,
    source_version text NOT NULL DEFAULT '',
    source_content_hashes_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    review_note text NOT NULL DEFAULT '',
    reviewed_by text NOT NULL DEFAULT '',
    reviewed_at timestamptz,
    valid_from timestamptz NOT NULL DEFAULT now(),
    valid_to timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_kg_edge_nodes_differ CHECK (from_node_id <> to_node_id)
);

CREATE TABLE IF NOT EXISTS kg_edge_events (
    event_id uuid PRIMARY KEY,
    edge_id uuid NOT NULL REFERENCES kg_edges(edge_id),
    event_type text NOT NULL,
    from_review_status text,
    to_review_status text,
    event_data_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    actor text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kg_nodes_business_key ON kg_nodes (business_key);
CREATE INDEX IF NOT EXISTS idx_kg_edges_from_review ON kg_edges (from_node_id, review_status);
CREATE INDEX IF NOT EXISTS idx_kg_edges_to_review ON kg_edges (to_node_id, review_status);
CREATE INDEX IF NOT EXISTS idx_kg_edges_relation_review ON kg_edges (relation_type, review_status);
CREATE INDEX IF NOT EXISTS idx_kg_edge_events_edge_created ON kg_edge_events (edge_id, created_at);

ALTER TABLE kg_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE kg_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE kg_edge_events ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY "kg_nodes_service_access" ON kg_nodes FOR ALL USING (true) WITH CHECK (true);
    CREATE POLICY "kg_edges_service_access" ON kg_edges FOR ALL USING (true) WITH CHECK (true);
    CREATE POLICY "kg_edge_events_service_access" ON kg_edge_events FOR ALL USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
