-- Compatibility migration for databases where record_source was added as a
-- required column after the unified matrix writer had already been deployed.
-- The trigger keeps the old function definition compatible while the function
-- definitions in the previous migrations now write the field explicitly.

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

CREATE OR REPLACE FUNCTION public.populate_kb_modification_record_source()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.record_source := COALESCE(
        NULLIF(btrim(NEW.source_code), ''),
        NULLIF(btrim(NEW.source_module), ''),
        NULLIF(NULLIF(btrim(NEW.record_source), ''), 'knowledge_base'),
        'knowledge_base'
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_populate_kb_modification_record_source
    ON public.knowledge_base_modifications;

CREATE TRIGGER trg_populate_kb_modification_record_source
BEFORE INSERT OR UPDATE OF record_source, source_code, source_module
ON public.knowledge_base_modifications
FOR EACH ROW
EXECUTE FUNCTION public.populate_kb_modification_record_source();

COMMIT;
