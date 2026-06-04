-- Cloud module list-load indexes.
-- Run once on the PostgreSQL database used by the deployed K-Matrix service.

DO $$
BEGIN
    IF to_regclass('public.kb_scores') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_kb_scores_kb_id ON public.kb_scores(kb_id);
        CREATE INDEX IF NOT EXISTS idx_kb_scores_status ON public.kb_scores(status);
        CREATE INDEX IF NOT EXISTS idx_kb_scores_updated_at ON public.kb_scores(updated_at);
        CREATE INDEX IF NOT EXISTS idx_kb_scores_total_score ON public.kb_scores(total_score);
        CREATE INDEX IF NOT EXISTS idx_kb_scores_product_name ON public.kb_scores(product_name);
        ANALYZE public.kb_scores;
    END IF;

    IF to_regclass('public.link_previews') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_link_previews_created_at ON public.link_previews(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_link_previews_kb_id ON public.link_previews(kb_id);
        CREATE INDEX IF NOT EXISTS idx_link_previews_type ON public.link_previews(type);
        ANALYZE public.link_previews;
    END IF;

    IF to_regclass('public.kb_recall') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_kb_recall_month ON public.kb_recall(month);
        CREATE INDEX IF NOT EXISTS idx_kb_recall_kb_id ON public.kb_recall(kb_id);
        CREATE INDEX IF NOT EXISTS idx_kb_recall_month_kb_id ON public.kb_recall(month, kb_id);
        ANALYZE public.kb_recall;
    END IF;

    IF to_regclass('public.product_matrix') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_product_matrix_question_wiki_id ON public.product_matrix(question_wiki_id);
        CREATE INDEX IF NOT EXISTS idx_product_matrix_product_name ON public.product_matrix(product_name);
        CREATE INDEX IF NOT EXISTS idx_product_matrix_question_product ON public.product_matrix(question_wiki_id, product_name);
        CREATE INDEX IF NOT EXISTS idx_product_matrix_product_question ON public.product_matrix(product_name, question_wiki_id);
        CREATE INDEX IF NOT EXISTS idx_product_matrix_product_category ON public.product_matrix(product_category);
        CREATE INDEX IF NOT EXISTS idx_product_matrix_is_configured ON public.product_matrix(is_configured);
        CREATE INDEX IF NOT EXISTS idx_product_matrix_manual_edit ON public.product_matrix(manual_edit);
        CREATE INDEX IF NOT EXISTS idx_product_matrix_edit_source ON public.product_matrix(edit_source);
        ANALYZE public.product_matrix;
    END IF;

    IF to_regclass('public.matrix_column') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_matrix_column_product_name ON public.matrix_column(product_name);
        CREATE INDEX IF NOT EXISTS idx_matrix_column_sort_order ON public.matrix_column(sort_order);
        ANALYZE public.matrix_column;
    END IF;

    IF to_regclass('public.kb_item_tags') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_kb_item_tags_library_wiki ON public.kb_item_tags(library_type, question_wiki_id);
        CREATE INDEX IF NOT EXISTS idx_kb_item_tags_library_tag ON public.kb_item_tags(library_type, tag_id);
        CREATE INDEX IF NOT EXISTS idx_kb_item_tags_question_wiki_id ON public.kb_item_tags(question_wiki_id);
        CREATE INDEX IF NOT EXISTS idx_kb_item_tags_tag_id ON public.kb_item_tags(tag_id);
        ANALYZE public.kb_item_tags;
    END IF;

    IF to_regclass('public.kb_tags') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_kb_tags_name ON public.kb_tags(name);
        ANALYZE public.kb_tags;
    END IF;
END $$;

NOTIFY pgrst, 'reload schema';
