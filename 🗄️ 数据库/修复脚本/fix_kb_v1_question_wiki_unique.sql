-- Fix incremental KB import upsert failures.
-- Error: there is no unique or exclusion constraint matching the ON CONFLICT specification
--
-- Run this on the target PostgreSQL database used by K-Matrix.
-- It adds the unique constraint required by:
--   INSERT ... ON CONFLICT (question_wiki_id) DO UPDATE

DO $$
DECLARE
    v_table text;
    v_null_count integer;
    v_dup_count integer;
    v_has_constraint boolean;
BEGIN
    FOREACH v_table IN ARRAY ARRAY['knowledge_base_v1', 'knowledge_base_v1_t1']
    LOOP
        EXECUTE format(
            'SELECT COUNT(*) FROM public.%I WHERE question_wiki_id IS NULL OR btrim(question_wiki_id) = ''''',
            v_table
        )
        INTO v_null_count;

        IF v_null_count > 0 THEN
            RAISE EXCEPTION '% has % rows with empty question_wiki_id. Fix those rows before adding a unique constraint.',
                v_table, v_null_count;
        END IF;

        EXECUTE format(
            'SELECT COUNT(*) FROM (
                SELECT question_wiki_id
                FROM public.%I
                GROUP BY question_wiki_id
                HAVING COUNT(*) > 1
            ) d',
            v_table
        )
        INTO v_dup_count;

        IF v_dup_count > 0 THEN
            RAISE EXCEPTION '% has % duplicate question_wiki_id values. Deduplicate before adding a unique constraint.',
                v_table, v_dup_count;
        END IF;

        SELECT EXISTS (
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
              AND t.relname = v_table
              AND c.contype IN ('p', 'u')
              AND c.conkey = ARRAY[
                  (
                      SELECT a.attnum
                      FROM pg_attribute a
                      WHERE a.attrelid = t.oid
                        AND a.attname = 'question_wiki_id'
                        AND NOT a.attisdropped
                  )
              ]::smallint[]
        )
        INTO v_has_constraint;

        IF NOT v_has_constraint THEN
            EXECUTE format(
                'ALTER TABLE public.%I ADD CONSTRAINT %I UNIQUE (question_wiki_id)',
                v_table,
                v_table || '_question_wiki_id_unique'
            );
            RAISE NOTICE 'Added unique constraint on %.question_wiki_id', v_table;
        ELSE
            RAISE NOTICE '%.question_wiki_id already has a primary/unique constraint', v_table;
        END IF;

        EXECUTE format('ALTER TABLE public.%I ALTER COLUMN question_wiki_id SET NOT NULL', v_table);
    END LOOP;
END $$;

-- Refresh PostgREST/Supabase schema cache when applicable.
NOTIFY pgrst, 'reload schema';
