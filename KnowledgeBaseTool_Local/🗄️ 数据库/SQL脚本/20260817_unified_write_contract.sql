-- KnowBase Hub five-module unified write contract (additive migration).
-- Run after the existing knowledge_base_v1 and modification tables exist.
-- All statements are idempotent so this can be applied during a maintenance
-- window without rewriting historical audit rows.

ALTER TABLE public.knowledge_base_v1
    ADD COLUMN IF NOT EXISTS content_version integer NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS content_lifecycle_status text NOT NULL DEFAULT 'normal';

UPDATE public.knowledge_base_v1
   SET content_version = 1
 WHERE content_version IS NULL OR content_version < 1;

ALTER TABLE public.knowledge_base_modifications
    ADD COLUMN IF NOT EXISTS operation_id text,
    ADD COLUMN IF NOT EXISTS source_code text,
    ADD COLUMN IF NOT EXISTS source_module text,
    ADD COLUMN IF NOT EXISTS base_version integer,
    ADD COLUMN IF NOT EXISTS committed_version integer,
    ADD COLUMN IF NOT EXISTS submitted_version integer,
    ADD COLUMN IF NOT EXISTS conflict_resolution text NOT NULL DEFAULT 'normal',
    ADD COLUMN IF NOT EXISTS archived_at timestamptz,
    ADD COLUMN IF NOT EXISTS archived_by text,
    ADD COLUMN IF NOT EXISTS archive_batch_id text;

UPDATE public.knowledge_base_modifications
   SET source_code = CASE COALESCE(source_module, change_meta ->> 'source')
       WHEN '机型矩阵管理' THEN 'product_matrix'
       WHEN '新品录入' THEN 'new_product_entry'
       WHEN '全量导入' THEN 'full_import'
       WHEN '系统迁移' THEN 'system_migration'
       ELSE 'knowledge_base'
   END
 WHERE source_code IS NULL OR btrim(source_code) = '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_kb_mod_operation_wiki
    ON public.knowledge_base_modifications (operation_id, question_wiki_id)
    WHERE operation_id IS NOT NULL AND question_wiki_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_kb_mod_pending_status
    ON public.knowledge_base_modifications (question_wiki_id, archived_at, modification_time DESC);

-- Older SQLite imports may have left PostgreSQL serial sequences behind the
-- copied IDs.  Align them before the unified writer starts inserting rows.
SELECT setval(pg_get_serial_sequence('public.matrix_column', 'id'), COALESCE((SELECT max(id) FROM public.matrix_column), 0) + 1, false);
SELECT setval(pg_get_serial_sequence('public.product_matrix', 'id'), COALESCE((SELECT max(id) FROM public.product_matrix), 0) + 1, false);
SELECT setval(pg_get_serial_sequence('public.matrix_submit_operation', 'id'), COALESCE((SELECT max(id) FROM public.matrix_submit_operation), 0) + 1, false);
SELECT setval(pg_get_serial_sequence('public.button', 'id'), COALESCE((SELECT max(id) FROM public.button), 0) + 1, false);

ALTER TABLE public.knowledge_base_modifications
    DROP CONSTRAINT IF EXISTS ck_kb_mod_source_code;

ALTER TABLE public.knowledge_base_modifications
    ADD CONSTRAINT ck_kb_mod_source_code CHECK (
        source_code IN ('knowledge_base', 'product_matrix', 'new_product_entry', 'full_import', 'system_migration')
    );

-- One transaction for matrix changes, the V1 product projection, idempotency,
-- and the audit event.  The API calls this function instead of coordinating
-- independent SQLite/PostgREST writes after the migration is enabled.
CREATE OR REPLACE FUNCTION public.submit_matrix_changes_unified(
    p_operation_id text,
    p_actor text,
    p_source_code text,
    p_changes jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    op_row public.matrix_submit_operation%ROWTYPE;
    kb_row public.knowledge_base_v1%ROWTYPE;
    change jsonb;
    wiki_id text;
    model_name text;
    old_value boolean;
    new_value boolean;
    current_value boolean;
    before_products text;
    after_products text;
    before_version integer;
    committed integer;
    written integer := 0;
    changed_ids jsonb := '[]'::jsonb;
    source_code text := COALESCE(NULLIF(p_source_code, ''), 'product_matrix');
BEGIN
    IF source_code NOT IN ('product_matrix', 'new_product_entry') THEN
        RAISE EXCEPTION 'invalid matrix source_code: %', source_code;
    END IF;
    IF jsonb_typeof(p_changes) <> 'array' OR jsonb_array_length(p_changes) = 0 THEN
        RAISE EXCEPTION 'changes must be a non-empty array';
    END IF;

    SELECT * INTO op_row
      FROM public.matrix_submit_operation
     WHERE operation_id = p_operation_id
     FOR UPDATE;
    IF FOUND AND op_row.status = 'success' THEN
        RETURN jsonb_build_object('success', true, 'idempotent', true,
                                  'operation_id', p_operation_id,
                                  'written', (SELECT count(*) FROM public.button WHERE operation_id = p_operation_id));
    END IF;
    IF FOUND AND op_row.created_by IS NOT NULL AND op_row.created_by <> p_actor THEN
        RAISE EXCEPTION 'operation_id belongs to another actor';
    END IF;
    IF NOT FOUND THEN
        INSERT INTO public.matrix_submit_operation(operation_id, status, attempts, created_by)
        VALUES (p_operation_id, 'pending', 1, p_actor);
    ELSE
        UPDATE public.matrix_submit_operation
           SET status = 'pending', attempts = COALESCE(attempts, 0) + 1, error_message = NULL, updated_at = now()
         WHERE operation_id = p_operation_id;
    END IF;

    FOR wiki_id IN
        SELECT DISTINCT trim(value->>'question_wiki_id')
          FROM jsonb_array_elements(p_changes) AS value
         WHERE trim(value->>'question_wiki_id') <> ''
    LOOP
        SELECT * INTO kb_row FROM public.knowledge_base_v1
         WHERE question_wiki_id = wiki_id FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'knowledge not found: %', wiki_id;
        END IF;
        before_version := GREATEST(COALESCE(kb_row.content_version, 1), 1);
        before_products := COALESCE(kb_row.product_name, '');

        FOR change IN
            SELECT value FROM jsonb_array_elements(p_changes) AS value
             WHERE trim(value->>'question_wiki_id') = wiki_id
        LOOP
            model_name := trim(change->>'product_name');
            old_value := COALESCE((change->>'old_is_configured')::boolean, false);
            new_value := COALESCE((change->>'new_is_configured')::boolean, false);
            IF model_name = '' OR NOT EXISTS (SELECT 1 FROM public.matrix_column WHERE product_name = model_name) THEN
                RAISE EXCEPTION 'unknown model: %', model_name;
            END IF;
            SELECT COALESCE(is_configured, false) INTO current_value
              FROM public.product_matrix
             WHERE question_wiki_id = wiki_id AND product_name = model_name
             FOR UPDATE;
            current_value := COALESCE(current_value, false);
            -- A legacy draft cell may already have written the requested value
            -- before this unified procedure runs.  Accept that converged state;
            -- reject only a value that is neither side of this submitted diff.
            IF current_value <> old_value AND current_value <> new_value THEN
                RAISE EXCEPTION 'matrix conflict for %/%: current %, expected %', wiki_id, model_name, current_value, old_value;
            END IF;
            INSERT INTO public.product_matrix(question_wiki_id, product_name, is_configured, manual_edit, edit_source, last_synced_at, question_content, answer_content, update_time, product_category)
            VALUES (wiki_id, model_name, new_value, true, 'submitted', now(), kb_row.question, kb_row.answer, kb_row.update_time::text, kb_row.product_category_name)
            ON CONFLICT (question_wiki_id, product_name) DO UPDATE
              SET is_configured = EXCLUDED.is_configured, manual_edit = true, edit_source = 'submitted', last_synced_at = now();
            INSERT INTO public.button(operation_id, question_wiki_id, product_name, old_is_configured, new_is_configured, edit_source, submitted_by, submitted_at)
            VALUES (p_operation_id, wiki_id, model_name, old_value, new_value, COALESCE(change->>'edit_source', 'cell'), p_actor, now())
            ON CONFLICT (operation_id, question_wiki_id, product_name) DO NOTHING;
            written := written + 1;
        END LOOP;

        SELECT string_agg(product_name, ', ' ORDER BY product_name)
          INTO after_products
          FROM public.product_matrix
         WHERE question_wiki_id = wiki_id AND is_configured = true;
        committed := before_version + 1;
        UPDATE public.knowledge_base_v1
           SET product_name = COALESCE(after_products, ''), content_version = committed,
               update_time = now(), content_lifecycle_status = COALESCE(content_lifecycle_status, 'normal')
         WHERE question_wiki_id = wiki_id AND content_version = before_version;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'version conflict for %', wiki_id;
        END IF;
        INSERT INTO public.knowledge_base_modifications(
            kb_id, question_wiki_id, product_name, question, answer, source_code, source_module,
            operation_id, base_version, committed_version, submitted_version, conflict_resolution,
            modifier, modification_time, change_type, change_meta
        ) VALUES (
            wiki_id, wiki_id, COALESCE(after_products, ''), kb_row.question, kb_row.answer, source_code,
            CASE source_code WHEN 'new_product_entry' THEN '新品录入' ELSE '机型矩阵管理' END,
            p_operation_id, before_version, committed, committed, 'normal', p_actor, now(), 'edit',
            jsonb_build_object('source', CASE source_code WHEN 'new_product_entry' THEN '新品录入' ELSE '机型矩阵管理' END,
                               'source_code', source_code, 'operation_id', p_operation_id,
                               'before', jsonb_build_object('products', before_products),
                               'after', jsonb_build_object('products', COALESCE(after_products, '')),
                               'changed_fields', jsonb_build_array('products'))
        ) ON CONFLICT DO NOTHING;
        changed_ids := changed_ids || to_jsonb(wiki_id);
    END LOOP;
    UPDATE public.matrix_submit_operation
       SET status = 'success', updated_at = now(), error_message = NULL
     WHERE operation_id = p_operation_id;
    RETURN jsonb_build_object('success', true, 'operation_id', p_operation_id, 'written', written, 'question_wiki_ids', changed_ids);
END;
$$;
