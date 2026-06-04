-- Add product snapshots to kb_scores and backfill them from knowledge_base_v1.
-- This fixes scoring rows whose product column shows "-" while KB Management has products.

ALTER TABLE IF EXISTS public.kb_scores
    ADD COLUMN IF NOT EXISTS product_name TEXT;

UPDATE public.kb_scores s
SET product_name = COALESCE(k.product_name, '')
FROM public.knowledge_base_v1 k
WHERE s.kb_id = k.question_wiki_id
  AND COALESCE(s.product_name, '') <> COALESCE(k.product_name, '');

CREATE INDEX IF NOT EXISTS idx_kb_scores_product_name
    ON public.kb_scores(product_name);

-- Refresh PostgREST/Supabase schema cache when applicable.
NOTIFY pgrst, 'reload schema';
