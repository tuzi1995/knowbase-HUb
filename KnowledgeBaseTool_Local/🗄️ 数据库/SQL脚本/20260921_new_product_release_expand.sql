-- Additive PostgreSQL migration for the new product release expansion.
-- This script is intentionally defensive: it only extends the real tables already
-- used by the app and does not drop or rewrite existing operational data.

BEGIN;

ALTER TABLE public.knowledge_base_v1
    ADD COLUMN IF NOT EXISTS kb_scope text,
    ADD COLUMN IF NOT EXISTS release_status text,
    ADD COLUMN IF NOT EXISTS migration_batch_id text,
    ADD COLUMN IF NOT EXISTS shadow_product_names_json text DEFAULT '[]';

ALTER TABLE public.knowledge_base_modifications
    ADD COLUMN IF NOT EXISTS record_scope text,
    ADD COLUMN IF NOT EXISTS release_status text,
    ADD COLUMN IF NOT EXISTS migration_batch_id text,
    ADD COLUMN IF NOT EXISTS shadow_product_names_json text DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS source_code text,
    ADD COLUMN IF NOT EXISTS source_module text,
    ADD COLUMN IF NOT EXISTS record_source text;

UPDATE public.knowledge_base_modifications
   SET record_source = COALESCE(
       NULLIF(btrim(record_source), ''),
       NULLIF(btrim(source_code), ''),
       NULLIF(btrim(source_module), ''),
       'knowledge_base'
   )
 WHERE record_source IS NULL OR btrim(record_source) = '';

UPDATE public.knowledge_base_modifications
   SET record_scope = 'formal'
 WHERE record_scope IS NULL OR btrim(record_scope) = '';

ALTER TABLE public.knowledge_base_modifications
    ALTER COLUMN record_scope SET DEFAULT 'formal',
    ALTER COLUMN record_scope SET NOT NULL,
    ALTER COLUMN record_source SET DEFAULT 'knowledge_base',
    ALTER COLUMN record_source SET NOT NULL;

ALTER TABLE public.product_matrix
    ADD COLUMN IF NOT EXISTS release_status text,
    ADD COLUMN IF NOT EXISTS association_status text,
    ADD COLUMN IF NOT EXISTS migration_batch_id text,
    ADD COLUMN IF NOT EXISTS product_release_scope text,
    ADD COLUMN IF NOT EXISTS shadow_product_names_json text DEFAULT '[]';

ALTER TABLE public.matrix_submit_operation
    ADD COLUMN IF NOT EXISTS migration_batch_id text,
    ADD COLUMN IF NOT EXISTS release_status text,
    ADD COLUMN IF NOT EXISTS validation_snapshot_json text DEFAULT '{}';

CREATE TABLE IF NOT EXISTS public.product_release_request (
    id bigserial PRIMARY KEY,
    request_id text NOT NULL DEFAULT '',
    question_wiki_id text NOT NULL,
    target_model text NOT NULL,
    release_status text NOT NULL DEFAULT 'pending_release',
    pending_version integer NOT NULL DEFAULT 1,
    kb_scope text NOT NULL DEFAULT 'unscoped',
    migration_batch_id text NOT NULL DEFAULT '',
    requested_by text NOT NULL DEFAULT '',
    target_kb text NOT NULL DEFAULT '',
    trigger_model text NOT NULL DEFAULT '',
    effective_method text NOT NULL DEFAULT 'online',
    public_kb_confirmed boolean NOT NULL DEFAULT false,
    preview_token_digest text NOT NULL DEFAULT '',
    preview_token_expires_at timestamptz,
    pending_chain_json text NOT NULL DEFAULT '[]',
    predecessor_request_id text NOT NULL DEFAULT '',
    generation integer NOT NULL DEFAULT 1,
    conflict_status text NOT NULL DEFAULT 'clean',
    downstream_status text NOT NULL DEFAULT 'queued',
    outbox_status text NOT NULL DEFAULT 'pending',
    idempotency_key text NOT NULL DEFAULT '',
    cancelled_at timestamptz,
    cancelled_by text NOT NULL DEFAULT '',
    cancel_reason text NOT NULL DEFAULT '',
    reapplied_from text NOT NULL DEFAULT '',
    batch_id text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (request_id),
    UNIQUE (question_wiki_id, target_model, migration_batch_id)
);

CREATE TABLE IF NOT EXISTS public.product_release_pending_version (
    id bigserial PRIMARY KEY,
    question_wiki_id text NOT NULL,
    pending_version integer NOT NULL DEFAULT 1,
    release_status text NOT NULL DEFAULT 'pending_release',
    source_model text NOT NULL DEFAULT '',
    snapshot_json text NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (question_wiki_id, pending_version)
);

-- Cross-source pending modification ledger. This is deliberately separate from
-- knowledge_base_modifications, whose record_scope is formal-only after the gate.
CREATE TABLE IF NOT EXISTS public.product_release_pending_modification (
    record_id text PRIMARY KEY,
    record_scope text NOT NULL DEFAULT 'pending',
    release_status text NOT NULL DEFAULT 'pending_release',
    source_module text NOT NULL DEFAULT '',
    source_operation_id text NOT NULL DEFAULT '',
    question_wiki_id text NOT NULL,
    target_model text NOT NULL,
    before_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    after_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    change_type text NOT NULL DEFAULT 'matrix_association',
    status text NOT NULL DEFAULT 'pending_release',
    created_by text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    release_batch_id text NOT NULL DEFAULT '',
    formal_record_id text NOT NULL DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_product_release_pending_modification_operation
    ON public.product_release_pending_modification (source_operation_id, question_wiki_id, target_model)
    WHERE source_operation_id <> '';
CREATE INDEX IF NOT EXISTS idx_product_release_pending_modification_status
    ON public.product_release_pending_modification (status, target_model);

ALTER TABLE public.product_release_pending_version
    ADD COLUMN IF NOT EXISTS pending_id text,
    ADD COLUMN IF NOT EXISTS sequence_no integer,
    ADD COLUMN IF NOT EXISTS baseline_content_version integer,
    ADD COLUMN IF NOT EXISTS parent_pending_id text,
    ADD COLUMN IF NOT EXISTS content_hash text,
    ADD COLUMN IF NOT EXISTS pending_change_type text,
    ADD COLUMN IF NOT EXISTS replaces_pending_id text,
    ADD COLUMN IF NOT EXISTS published_content_version integer,
    ADD COLUMN IF NOT EXISTS formal_record_id text,
    ADD COLUMN IF NOT EXISTS public_kb_confirmed boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS impact_models_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS confirmed_by text NOT NULL DEFAULT '';

ALTER TABLE public.product_release_pending_version
    ADD COLUMN IF NOT EXISTS baseline_snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS block_reason text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS cancelled_at timestamptz,
    ADD COLUMN IF NOT EXISTS cancelled_by text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS cancel_reason text NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS public.product_release_model_binding (
    id bigserial PRIMARY KEY,
    question_wiki_id text NOT NULL,
    product_name text NOT NULL,
    kb_scope text NOT NULL DEFAULT 'unscoped',
    record_scope text NOT NULL DEFAULT 'unscoped',
    release_status text NOT NULL DEFAULT 'pending_release',
    migration_batch_id text NOT NULL DEFAULT '',
    shadow_product_names_json text NOT NULL DEFAULT '[]',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (question_wiki_id, product_name, migration_batch_id)
);

ALTER TABLE public.product_release_model_binding
    ADD COLUMN IF NOT EXISTS pending_id text,
    ADD COLUMN IF NOT EXISTS application_id text,
    ADD COLUMN IF NOT EXISTS association_status text,
    ADD COLUMN IF NOT EXISTS content_binding_mode text,
    ADD COLUMN IF NOT EXISTS binding_role text,
    ADD COLUMN IF NOT EXISTS binding_status text,
    ADD COLUMN IF NOT EXISTS released_content_version integer,
    ADD COLUMN IF NOT EXISTS source_operation_id text;

CREATE TABLE IF NOT EXISTS public.product_release_batch (
    id bigserial PRIMARY KEY,
    migration_batch_id text NOT NULL UNIQUE,
    release_status text NOT NULL DEFAULT 'validating',
    total_items integer NOT NULL DEFAULT 0,
    created_by text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    dispatched_at timestamptz,
    completed_at timestamptz
);

ALTER TABLE public.product_release_batch
    ADD COLUMN IF NOT EXISTS model_id text,
    ADD COLUMN IF NOT EXISTS application_id text,
    ADD COLUMN IF NOT EXISTS release_version integer,
    ADD COLUMN IF NOT EXISTS association_version integer,
    ADD COLUMN IF NOT EXISTS preview_digest text,
    ADD COLUMN IF NOT EXISTS idempotency_key text,
    ADD COLUMN IF NOT EXISTS operator text,
    ADD COLUMN IF NOT EXISTS formal_record_ids_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS published_pending_ids_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS started_at timestamptz,
    ADD COLUMN IF NOT EXISTS finished_at timestamptz,
    ADD COLUMN IF NOT EXISTS error_summary text NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS public.product_release_business_outbox (
    id bigserial PRIMARY KEY,
    migration_batch_id text NOT NULL DEFAULT '',
    op_type text NOT NULL DEFAULT 'release',
    payload_json text NOT NULL DEFAULT '{}',
    status text NOT NULL DEFAULT 'pending',
    attempts integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.product_release_business_outbox
    ADD COLUMN IF NOT EXISTS event_id text,
    ADD COLUMN IF NOT EXISTS event_type text,
    ADD COLUMN IF NOT EXISTS idempotency_key text,
    ADD COLUMN IF NOT EXISTS last_error text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS receipt_json jsonb;

CREATE TABLE IF NOT EXISTS public.product_release_domain_state (
    singleton_id smallint PRIMARY KEY CHECK (singleton_id = 1),
    state_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    revision bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.product_release_domain_state (singleton_id, state_json, revision)
VALUES (1, '{}'::jsonb, 0)
ON CONFLICT (singleton_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.product_release_audit (
    id bigserial PRIMARY KEY,
    audit_id text NOT NULL UNIQUE,
    action text NOT NULL,
    actor text NOT NULL DEFAULT '',
    model_id text NOT NULL DEFAULT '',
    request_id text NOT NULL DEFAULT '',
    pending_id text NOT NULL DEFAULT '',
    batch_id text NOT NULL DEFAULT '',
    reason text NOT NULL DEFAULT '',
    details_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.product_release_migration_batch (
    id bigserial PRIMARY KEY,
    migration_batch_id text NOT NULL UNIQUE,
    batch_name text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'created',
    run_summary_json text NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.product_release_reconciliation (
    id bigserial PRIMARY KEY,
    migration_batch_id text NOT NULL DEFAULT '',
    reconciliation_status text NOT NULL DEFAULT 'pending',
    official_set_json text NOT NULL DEFAULT '[]',
    shadow_set_json text NOT NULL DEFAULT '[]',
    extra_in_official_json text NOT NULL DEFAULT '[]',
    extra_in_shadow_json text NOT NULL DEFAULT '[]',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.release_migration_exit_switch (
    switch_name text PRIMARY KEY,
    enabled boolean NOT NULL DEFAULT false,
    migration_batch_id text NOT NULL DEFAULT '',
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.release_migration_exit_switch (switch_name, enabled, migration_batch_id)
VALUES ('new_product_release', false, '')
ON CONFLICT (switch_name) DO NOTHING;

UPDATE public.release_migration_exit_switch
   SET enabled = false,
       migration_batch_id = COALESCE(migration_batch_id, ''),
       updated_at = now()
 WHERE switch_name = 'new_product_release'
   AND enabled IS NULL;

CREATE INDEX IF NOT EXISTS idx_product_release_request_batch
    ON public.product_release_request (migration_batch_id);
CREATE INDEX IF NOT EXISTS idx_product_release_request_model
    ON public.product_release_request (target_model, release_status);
CREATE INDEX IF NOT EXISTS idx_product_release_model_binding_batch
    ON public.product_release_model_binding (migration_batch_id);
CREATE INDEX IF NOT EXISTS idx_product_release_business_outbox_status
    ON public.product_release_business_outbox (status);
CREATE INDEX IF NOT EXISTS idx_product_release_migration_batch_status
    ON public.product_release_migration_batch (status);
CREATE INDEX IF NOT EXISTS idx_product_release_reconciliation_status
    ON public.product_release_reconciliation (reconciliation_status);

CREATE UNIQUE INDEX IF NOT EXISTS uq_product_release_pending_id
    ON public.product_release_pending_version (pending_id) WHERE pending_id IS NOT NULL;
ALTER TABLE public.product_release_request
    DROP CONSTRAINT IF EXISTS product_release_request_idempotency_key_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_product_release_request_idempotency
    ON public.product_release_request (idempotency_key)
    WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';
DROP INDEX IF EXISTS public.uq_product_release_batch_idempotency;
CREATE UNIQUE INDEX uq_product_release_batch_idempotency
    ON public.product_release_batch (idempotency_key)
    WHERE idempotency_key IS NOT NULL AND idempotency_key <> '' AND release_status = 'completed';
CREATE UNIQUE INDEX IF NOT EXISTS uq_product_release_outbox_event
    ON public.product_release_business_outbox (event_id) WHERE event_id IS NOT NULL;

-- One database switch controls all formal-read views. While it is off the
-- views preserve the legacy set; after the migration gate enables it they
-- enforce the formal scope at each outlet's ownership boundary.  Modification
-- history is keyed by its own record_scope and must not be inner-joined to the
-- current product matrix: historical records can outlive an association while
-- remaining part of the formal audit trail.
CREATE OR REPLACE VIEW public.formal_product_matrix AS
SELECT pm.*
  FROM public.product_matrix pm
  JOIN public.knowledge_base_v1 kb ON kb.question_wiki_id = pm.question_wiki_id
 WHERE NOT EXISTS (
           SELECT 1 FROM public.release_migration_exit_switch sw
            WHERE sw.switch_name = 'new_product_release' AND sw.enabled = true
       )
    OR (kb.kb_scope = 'formal' AND pm.association_status = 'active' AND pm.release_status = 'released');

CREATE OR REPLACE VIEW public.formal_knowledge_base_v1 AS
SELECT kb.*
  FROM public.knowledge_base_v1 kb
 WHERE NOT EXISTS (
           SELECT 1 FROM public.release_migration_exit_switch sw
            WHERE sw.switch_name = 'new_product_release' AND sw.enabled = true
       )
    OR (kb.kb_scope = 'formal' AND EXISTS (
        SELECT 1 FROM public.product_matrix pm
         WHERE pm.question_wiki_id = kb.question_wiki_id
           AND pm.association_status = 'active' AND pm.release_status = 'released'
    ));

CREATE OR REPLACE VIEW public.formal_knowledge_base_modifications AS
SELECT modifications.*
  FROM public.knowledge_base_modifications modifications
 WHERE NOT EXISTS (
           SELECT 1 FROM public.release_migration_exit_switch sw
            WHERE sw.switch_name = 'new_product_release' AND sw.enabled = true
       )
    OR modifications.record_scope = 'formal';

COMMIT;
