-- Contract gate for the new product release expansion.
-- This file intentionally does not auto-enable the feature. It only validates the
-- preconditions expected by the migration gate and raises exceptions if the
-- real tables do not meet the required shape.

BEGIN;

DO $$
DECLARE
    kb_scope_exists boolean;
    record_scope_exists boolean;
    release_status_exists boolean;
    association_status_exists boolean;
    migration_batch_exists boolean;
    binding_exists boolean;
    request_exists boolean;
    pending_version_exists boolean;
    pending_modification_exists boolean;
    batch_exists boolean;
    outbox_exists boolean;
    reconciliation_exists boolean;
    switch_exists boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'knowledge_base_v1'
           AND column_name = 'kb_scope'
    ) INTO kb_scope_exists;

    SELECT EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'knowledge_base_modifications'
           AND column_name = 'record_scope'
    ) INTO record_scope_exists;

    SELECT EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'product_matrix'
           AND column_name = 'release_status'
    ) INTO release_status_exists;

    SELECT EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'product_matrix'
           AND column_name = 'association_status'
    ) INTO association_status_exists;

    SELECT EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'matrix_submit_operation'
           AND column_name = 'migration_batch_id'
    ) INTO migration_batch_exists;

    SELECT EXISTS (
        SELECT 1
          FROM information_schema.tables
         WHERE table_schema = 'public'
           AND table_name = 'product_release_model_binding'
    ) INTO binding_exists;

    SELECT EXISTS (
        SELECT 1
          FROM information_schema.tables
         WHERE table_schema = 'public'
           AND table_name = 'product_release_request'
    ) INTO request_exists;

    SELECT EXISTS (
        SELECT 1
          FROM information_schema.tables
         WHERE table_schema = 'public'
           AND table_name = 'product_release_pending_version'
    ) INTO pending_version_exists;

    SELECT EXISTS (
        SELECT 1
          FROM information_schema.tables
         WHERE table_schema = 'public'
           AND table_name = 'product_release_pending_modification'
    ) INTO pending_modification_exists;

    SELECT EXISTS (
        SELECT 1
          FROM information_schema.tables
         WHERE table_schema = 'public'
           AND table_name = 'product_release_batch'
    ) INTO batch_exists;

    SELECT EXISTS (
        SELECT 1
          FROM information_schema.tables
         WHERE table_schema = 'public'
           AND table_name = 'product_release_business_outbox'
    ) INTO outbox_exists;

    SELECT EXISTS (
        SELECT 1
          FROM information_schema.tables
         WHERE table_schema = 'public'
           AND table_name = 'product_release_reconciliation'
    ) INTO reconciliation_exists;

    SELECT EXISTS (
        SELECT 1
          FROM information_schema.tables
         WHERE table_schema = 'public'
           AND table_name = 'release_migration_exit_switch'
    ) INTO switch_exists;

    IF NOT kb_scope_exists OR NOT record_scope_exists OR NOT release_status_exists OR NOT association_status_exists OR NOT migration_batch_exists
       OR NOT binding_exists OR NOT request_exists OR NOT pending_version_exists OR NOT pending_modification_exists OR NOT batch_exists
       OR NOT outbox_exists OR NOT reconciliation_exists OR NOT switch_exists THEN
        RAISE EXCEPTION 'new product release migration contract not yet satisfied: missing required schema objects';
    END IF;
END $$;

ALTER TABLE public.product_release_request
    DROP CONSTRAINT IF EXISTS ck_product_release_request_status;
ALTER TABLE public.product_release_request
    ADD CONSTRAINT ck_product_release_request_status CHECK (
        release_status IN ('pending_release', 'releasing', 'released', 'release_cancelled')
    ) NOT VALID;
ALTER TABLE public.product_release_request VALIDATE CONSTRAINT ck_product_release_request_status;

ALTER TABLE public.product_release_pending_version
    DROP CONSTRAINT IF EXISTS ck_product_release_pending_version_status;
ALTER TABLE public.product_release_pending_version
    ADD CONSTRAINT ck_product_release_pending_version_status CHECK (
        release_status IN ('pending_release', 'blocked', 'published', 'cancelled', 'superseded')
    ) NOT VALID;
ALTER TABLE public.product_release_pending_version VALIDATE CONSTRAINT ck_product_release_pending_version_status;

ALTER TABLE public.product_release_pending_modification
    DROP CONSTRAINT IF EXISTS ck_product_release_pending_modification_scope;
ALTER TABLE public.product_release_pending_modification
    ADD CONSTRAINT ck_product_release_pending_modification_scope CHECK (
        (status = 'pending_release' AND record_scope = 'pending')
        OR (status = 'published' AND record_scope = 'formal')
        OR status = 'cancelled'
    ) NOT VALID;
ALTER TABLE public.product_release_pending_modification VALIDATE CONSTRAINT ck_product_release_pending_modification_scope;

ALTER TABLE public.product_release_model_binding
    DROP CONSTRAINT IF EXISTS ck_product_release_model_binding_status;
ALTER TABLE public.product_release_model_binding
    ADD CONSTRAINT ck_product_release_model_binding_status CHECK (
        release_status IN ('pending_release', 'releasing', 'released', 'release_cancelled')
    ) NOT VALID;
ALTER TABLE public.product_release_model_binding VALIDATE CONSTRAINT ck_product_release_model_binding_status;

ALTER TABLE public.product_release_batch
    DROP CONSTRAINT IF EXISTS ck_product_release_batch_status;
ALTER TABLE public.product_release_batch
    ADD CONSTRAINT ck_product_release_batch_status CHECK (
        release_status IN ('validating', 'completed', 'failed')
    ) NOT VALID;
ALTER TABLE public.product_release_batch VALIDATE CONSTRAINT ck_product_release_batch_status;

ALTER TABLE public.product_release_business_outbox
    DROP CONSTRAINT IF EXISTS ck_product_release_business_outbox_status;
ALTER TABLE public.product_release_business_outbox
    ADD CONSTRAINT ck_product_release_business_outbox_status CHECK (
        status IN ('pending', 'processing', 'sent', 'failed')
    ) NOT VALID;
ALTER TABLE public.product_release_business_outbox VALIDATE CONSTRAINT ck_product_release_business_outbox_status;

ALTER TABLE public.product_release_migration_batch
    DROP CONSTRAINT IF EXISTS ck_product_release_migration_batch_status;
ALTER TABLE public.product_release_migration_batch
    ADD CONSTRAINT ck_product_release_migration_batch_status CHECK (
        status IN ('created', 'ready', 'running', 'passed', 'failed')
    ) NOT VALID;
ALTER TABLE public.product_release_migration_batch VALIDATE CONSTRAINT ck_product_release_migration_batch_status;

ALTER TABLE public.product_release_reconciliation
    DROP CONSTRAINT IF EXISTS ck_product_release_reconciliation_status;
ALTER TABLE public.product_release_reconciliation
    ADD CONSTRAINT ck_product_release_reconciliation_status CHECK (
        reconciliation_status IN ('pending', 'passed', 'failed', 'skipped')
    ) NOT VALID;
ALTER TABLE public.product_release_reconciliation VALIDATE CONSTRAINT ck_product_release_reconciliation_status;

ALTER TABLE public.release_migration_exit_switch
    DROP CONSTRAINT IF EXISTS ck_release_migration_exit_switch_enabled;
ALTER TABLE public.release_migration_exit_switch
    ADD CONSTRAINT ck_release_migration_exit_switch_enabled CHECK (
        enabled IN (true, false)
    ) NOT VALID;
ALTER TABLE public.release_migration_exit_switch VALIDATE CONSTRAINT ck_release_migration_exit_switch_enabled;

ALTER TABLE public.knowledge_base_v1
    DROP CONSTRAINT IF EXISTS ck_knowledge_base_v1_kb_scope;
ALTER TABLE public.knowledge_base_v1
    ADD CONSTRAINT ck_knowledge_base_v1_kb_scope CHECK (
        kb_scope IN ('formal', 'draft_pending_release')
    ) NOT VALID;
ALTER TABLE public.knowledge_base_v1 VALIDATE CONSTRAINT ck_knowledge_base_v1_kb_scope;

ALTER TABLE public.knowledge_base_modifications
    DROP CONSTRAINT IF EXISTS ck_knowledge_base_modifications_record_scope;
ALTER TABLE public.knowledge_base_modifications
    ADD CONSTRAINT ck_knowledge_base_modifications_record_scope CHECK (
        record_scope = 'formal'
    ) NOT VALID;
ALTER TABLE public.knowledge_base_modifications VALIDATE CONSTRAINT ck_knowledge_base_modifications_record_scope;

ALTER TABLE public.product_matrix
    DROP CONSTRAINT IF EXISTS ck_product_matrix_release_status;
ALTER TABLE public.product_matrix
    ADD CONSTRAINT ck_product_matrix_release_status CHECK (
        release_status IN ('pending_release', 'releasing', 'released', 'release_cancelled')
    ) NOT VALID;
ALTER TABLE public.product_matrix VALIDATE CONSTRAINT ck_product_matrix_release_status;

ALTER TABLE public.product_matrix
    DROP CONSTRAINT IF EXISTS ck_product_matrix_association_status;
ALTER TABLE public.product_matrix
    ADD CONSTRAINT ck_product_matrix_association_status CHECK (
        association_status IN ('pending_release', 'active', 'cancelled')
    ) NOT VALID;
ALTER TABLE public.product_matrix VALIDATE CONSTRAINT ck_product_matrix_association_status;

ALTER TABLE public.product_release_model_binding
    DROP CONSTRAINT IF EXISTS ck_product_release_model_binding_association_status;
ALTER TABLE public.product_release_model_binding
    ADD CONSTRAINT ck_product_release_model_binding_association_status CHECK (
        association_status IS NULL OR association_status IN ('pending_release', 'active', 'cancelled')
    ) NOT VALID;
ALTER TABLE public.product_release_model_binding VALIDATE CONSTRAINT ck_product_release_model_binding_association_status;

ALTER TABLE public.product_release_model_binding
    DROP CONSTRAINT IF EXISTS ck_product_release_model_binding_binding_status;
ALTER TABLE public.product_release_model_binding
    ADD CONSTRAINT ck_product_release_model_binding_binding_status CHECK (
        binding_status IS NULL OR binding_status IN ('waiting', 'consumed', 'released_by_peer', 'cancelled')
    ) NOT VALID;
ALTER TABLE public.product_release_model_binding VALIDATE CONSTRAINT ck_product_release_model_binding_binding_status;

-- Defensive validations: default deny unless a later gate explicitly authorizes a release.
DO $$
DECLARE
    kb_null_count integer;
    mod_null_count integer;
    product_null_count integer;
    binding_duplicate_rows integer;
    request_duplicate_rows integer;
    batch_null_count integer;
    reconciliation_null_count integer;
    switch_null_count integer;
    switch_enabled boolean;
BEGIN
    SELECT COUNT(*) INTO product_null_count
      FROM public.product_matrix
     WHERE release_status IS NULL OR association_status IS NULL;
    IF product_null_count > 0 THEN
        RAISE EXCEPTION 'product_matrix.release_status must not be null before activation';
    END IF;

    SELECT COUNT(*) INTO kb_null_count
      FROM public.knowledge_base_v1
     WHERE kb_scope IS NULL;
    IF kb_null_count > 0 THEN
        RAISE EXCEPTION 'knowledge_base_v1.kb_scope must not be null before activation';
    END IF;

    SELECT COUNT(*) INTO mod_null_count
      FROM public.knowledge_base_modifications
     WHERE record_scope IS NULL;
    IF mod_null_count > 0 THEN
        RAISE EXCEPTION 'knowledge_base_modifications.record_scope must not be null before activation';
    END IF;

    SELECT COUNT(*) INTO batch_null_count
      FROM public.product_release_batch
     WHERE migration_batch_id IS NULL OR migration_batch_id = '';
    IF batch_null_count > 0 THEN
        RAISE EXCEPTION 'product_release_batch.migration_batch_id must not be null or empty before activation';
    END IF;

    SELECT COUNT(*) INTO reconciliation_null_count
      FROM public.product_release_reconciliation
     WHERE migration_batch_id IS NULL OR migration_batch_id = '';
    IF reconciliation_null_count > 0 THEN
        RAISE EXCEPTION 'product_release_reconciliation.migration_batch_id must not be null or empty before activation';
    END IF;

    SELECT COUNT(*) INTO switch_null_count
      FROM public.release_migration_exit_switch
     WHERE switch_name = 'new_product_release' AND enabled IS NULL;
    IF switch_null_count > 0 THEN
        RAISE EXCEPTION 'release_migration_exit_switch.enabled must not be null';
    END IF;

    SELECT enabled INTO switch_enabled
      FROM public.release_migration_exit_switch
     WHERE switch_name = 'new_product_release';
    IF switch_enabled IS DISTINCT FROM false THEN
        RAISE EXCEPTION 'release_migration_exit_switch must remain false until an explicit approval step';
    END IF;

    SELECT COUNT(*) INTO binding_duplicate_rows
      FROM (
          SELECT question_wiki_id, product_name, migration_batch_id
            FROM public.product_release_model_binding
           GROUP BY question_wiki_id, product_name, migration_batch_id
          HAVING COUNT(*) > 1
      ) AS d;
    IF binding_duplicate_rows > 0 THEN
        RAISE EXCEPTION 'product_release_model_binding contains duplicate rows';
    END IF;

    SELECT COUNT(*) INTO request_duplicate_rows
      FROM (
          SELECT question_wiki_id, target_model, migration_batch_id
            FROM public.product_release_request
           GROUP BY question_wiki_id, target_model, migration_batch_id
          HAVING COUNT(*) > 1
      ) AS d;
    IF request_duplicate_rows > 0 THEN
        RAISE EXCEPTION 'product_release_request contains duplicate rows';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM public.product_release_request
         WHERE release_status IS NULL
            OR release_status = ''
    ) THEN
        RAISE EXCEPTION 'product_release_request.release_status contains empty or null values';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM public.product_release_model_binding
         WHERE release_status NOT IN ('pending_release', 'releasing', 'released', 'release_cancelled')
    ) THEN
        RAISE EXCEPTION 'product_release_model_binding.release_status contains invalid enum values';
    END IF;

    -- Preserve the legacy KB enum contract while the expanded release domain
    -- uses the more explicit pending_release/releasing states elsewhere.
    IF EXISTS (
        SELECT 1
          FROM public.knowledge_base_v1
         WHERE release_status IS NOT NULL
           AND release_status NOT IN ('pending', 'approved', 'released', 'rejected')
    ) THEN
        RAISE EXCEPTION 'knowledge_base_v1.release_status contains invalid legacy enum values';
    END IF;
END $$;

DO $$
DECLARE
    migration_batch_gate integer;
    reconciliation_gate integer;
BEGIN
    SELECT COUNT(*) INTO migration_batch_gate
      FROM public.product_release_migration_batch
     WHERE status NOT IN ('created', 'ready', 'running', 'passed', 'failed');
    IF migration_batch_gate > 0 THEN
        RAISE EXCEPTION 'product_release_migration_batch status gate failed';
    END IF;

    SELECT COUNT(*) INTO reconciliation_gate
      FROM public.product_release_reconciliation
     WHERE reconciliation_status NOT IN ('pending', 'passed', 'failed', 'skipped');
    IF reconciliation_gate > 0 THEN
        RAISE EXCEPTION 'product_release_reconciliation status gate failed';
    END IF;
END $$;

ALTER TABLE public.knowledge_base_v1
    ALTER COLUMN kb_scope SET NOT NULL;
ALTER TABLE public.knowledge_base_modifications
    ALTER COLUMN record_scope SET NOT NULL;
ALTER TABLE public.product_matrix
    ALTER COLUMN release_status SET NOT NULL;
ALTER TABLE public.product_matrix
    ALTER COLUMN association_status SET NOT NULL;
ALTER TABLE public.product_release_model_binding
    ALTER COLUMN migration_batch_id SET NOT NULL;
ALTER TABLE public.release_migration_exit_switch
    ALTER COLUMN enabled SET DEFAULT false;

ALTER TABLE public.knowledge_base_v1
    ALTER COLUMN kb_scope SET DEFAULT 'formal';
ALTER TABLE public.knowledge_base_modifications
    ALTER COLUMN record_scope SET DEFAULT 'formal';
ALTER TABLE public.product_matrix
    ALTER COLUMN release_status SET DEFAULT 'released';
ALTER TABLE public.product_matrix
    ALTER COLUMN association_status SET DEFAULT 'active';

COMMIT;
