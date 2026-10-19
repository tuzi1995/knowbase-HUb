BEGIN;

ALTER TABLE public.knowledge_base_modifications
    ADD COLUMN IF NOT EXISTS source_code text,
    ADD COLUMN IF NOT EXISTS source_module text,
    ADD COLUMN IF NOT EXISTS record_scope text,
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

-- Preserve the current KB product set when legacy matrix rows are incomplete.
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
           SET status = 'pending', attempts = COALESCE(attempts, 0) + 1,
               error_message = NULL, updated_at = now()
         WHERE operation_id = p_operation_id;
    END IF;

    FOR wiki_id IN
        SELECT DISTINCT trim(value->>'question_wiki_id')
          FROM jsonb_array_elements(p_changes) AS value
         WHERE trim(value->>'question_wiki_id') <> ''
    LOOP
        SELECT * INTO kb_row
          FROM public.knowledge_base_v1
         WHERE question_wiki_id = wiki_id
         FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'knowledge not found: %', wiki_id;
        END IF;
        before_version := GREATEST(COALESCE(kb_row.content_version, 1), 1);
        before_products := COALESCE(kb_row.product_name, '');

        -- The KB row is the published baseline. Add any missing baseline rows
        -- without deleting matrix-only relations whose provenance is unknown.
        INSERT INTO public.product_matrix(
            question_wiki_id, product_name, is_configured, manual_edit,
            edit_source, last_synced_at, question_content, answer_content,
            update_time, product_category
        )
        SELECT wiki_id, trim(existing_model), true, false,
               'kb_seed', now(), kb_row.question, kb_row.answer,
               kb_row.update_time::text, kb_row.product_category_name
          FROM regexp_split_to_table(before_products, '[,，]') AS existing_model
         WHERE trim(existing_model) <> ''
        ON CONFLICT (question_wiki_id, product_name) DO UPDATE
          SET is_configured = true;

        FOR change IN
            SELECT value
              FROM jsonb_array_elements(p_changes) AS value
             WHERE trim(value->>'question_wiki_id') = wiki_id
        LOOP
            model_name := trim(change->>'product_name');
            old_value := COALESCE((change->>'old_is_configured')::boolean, false);
            new_value := COALESCE((change->>'new_is_configured')::boolean, false);
            IF model_name = '' OR NOT EXISTS (
                SELECT 1 FROM public.matrix_column WHERE product_name = model_name
            ) THEN
                RAISE EXCEPTION 'unknown model: %', model_name;
            END IF;
            SELECT COALESCE(is_configured, false) INTO current_value
              FROM public.product_matrix
             WHERE question_wiki_id = wiki_id AND product_name = model_name
             FOR UPDATE;
            current_value := COALESCE(current_value, false);
            IF current_value <> old_value AND current_value <> new_value THEN
                RAISE EXCEPTION 'matrix conflict for %/%: current %, expected %',
                                wiki_id, model_name, current_value, old_value;
            END IF;
            INSERT INTO public.product_matrix(
                question_wiki_id, product_name, is_configured, manual_edit,
                edit_source, last_synced_at, question_content, answer_content,
                update_time, product_category
            ) VALUES (
                wiki_id, model_name, new_value, true, 'submitted', now(),
                kb_row.question, kb_row.answer, kb_row.update_time::text,
                kb_row.product_category_name
            )
            ON CONFLICT (question_wiki_id, product_name) DO UPDATE
              SET is_configured = EXCLUDED.is_configured,
                  manual_edit = true,
                  edit_source = 'submitted',
                  last_synced_at = now();
            INSERT INTO public.button(
                operation_id, question_wiki_id, product_name,
                old_is_configured, new_is_configured, edit_source,
                submitted_by, submitted_at
            ) VALUES (
                p_operation_id, wiki_id, model_name, old_value, new_value,
                COALESCE(change->>'edit_source', 'cell'), p_actor, now()
            )
            ON CONFLICT (operation_id, question_wiki_id, product_name) DO NOTHING;
            written := written + 1;
        END LOOP;

        -- The published KB is the source of truth for the product set.  The
        -- matrix is only used to persist the explicit deltas in this request;
        -- aggregating every configured matrix row would re-introduce stale or
        -- unrelated matrix-only relations.  The old aggregate predicate
        -- `WHERE question_wiki_id = wiki_id AND is_configured = true` is
        -- intentionally not used for the KB product list anymore.
        -- WHERE question_wiki_id = wiki_id AND is_configured = true
        WITH baseline AS (
            SELECT trim(model) AS display_name,
                   lower(regexp_replace(trim(model), '\\s+', ' ', 'g')) AS model_key
              FROM regexp_split_to_table(before_products, '[,，]') AS model
             WHERE trim(model) <> ''
        ),
        deltas AS (
            SELECT trim(value->>'product_name') AS display_name,
                   lower(regexp_replace(trim(value->>'product_name'), '\\s+', ' ', 'g')) AS model_key,
                   COALESCE((value->>'new_is_configured')::boolean, false) AS enabled
              FROM jsonb_array_elements(p_changes) AS value
             WHERE trim(value->>'question_wiki_id') = wiki_id
               AND trim(value->>'product_name') <> ''
        ),
        selected AS (
            SELECT DISTINCT ON (model_key) display_name, model_key
              FROM (
                    SELECT b.display_name, b.model_key
                      FROM baseline b
                     WHERE NOT EXISTS (
                         SELECT 1 FROM deltas d
                          WHERE d.model_key = b.model_key AND d.enabled = false
                     )
                    UNION ALL
                    SELECT d.display_name, d.model_key
                      FROM deltas d
                     WHERE d.enabled = true
                       AND NOT EXISTS (
                           SELECT 1 FROM deltas off
                            WHERE off.model_key = d.model_key AND off.enabled = false
                       )
              ) candidates
             ORDER BY model_key, display_name
        )
        SELECT string_agg(display_name, ', ' ORDER BY display_name)
          INTO after_products
          FROM selected;
        committed := before_version + 1;
        UPDATE public.knowledge_base_v1
           SET product_name = COALESCE(after_products, ''),
               content_version = committed,
               update_time = now(),
               content_lifecycle_status = COALESCE(content_lifecycle_status, 'normal')
         WHERE question_wiki_id = wiki_id AND content_version = before_version;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'version conflict for %', wiki_id;
        END IF;
        INSERT INTO public.knowledge_base_modifications(
            kb_id, question_wiki_id, product_name, question, answer,
            source_code, source_module, record_scope, record_source, operation_id, base_version,
            committed_version, submitted_version, conflict_resolution,
            modifier, modification_time, change_type, change_meta
        ) VALUES (
            wiki_id, wiki_id, COALESCE(after_products, ''), kb_row.question,
            kb_row.answer, source_code,
            CASE source_code WHEN 'new_product_entry' THEN '新品录入' ELSE '机型矩阵管理' END,
            'formal',
            source_code,
            p_operation_id, before_version, committed, committed, 'normal',
            p_actor, now(), 'edit',
            jsonb_build_object(
                'source', CASE source_code WHEN 'new_product_entry' THEN '新品录入' ELSE '机型矩阵管理' END,
                'source_code', source_code,
                'operation_id', p_operation_id,
                'before', jsonb_build_object('products', before_products),
                'after', jsonb_build_object('products', COALESCE(after_products, '')),
                'changed_fields', jsonb_build_array('products')
            )
        ) ON CONFLICT DO NOTHING;
        changed_ids := changed_ids || to_jsonb(wiki_id);
    END LOOP;

    UPDATE public.matrix_submit_operation
       SET status = 'success', updated_at = now(), error_message = NULL
     WHERE operation_id = p_operation_id;
    RETURN jsonb_build_object(
        'success', true,
        'operation_id', p_operation_id,
        'written', written,
        'question_wiki_ids', changed_ids
    );
END;
$$;

COMMIT;
