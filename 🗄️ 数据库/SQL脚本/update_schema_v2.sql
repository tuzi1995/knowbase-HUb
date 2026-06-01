-- 1. Add 'review_status' to the main table
-- Values: 'unadjusted' (未调整), 'modified' (修改中), 'deleting' (删除中)
ALTER TABLE public.knowledge_base_v1 
ADD COLUMN IF NOT EXISTS review_status text DEFAULT 'unadjusted';

-- 2. Add 'change_type' to the modifications table
-- Values: 'edit', 'delete'
ALTER TABLE public.knowledge_base_modifications 
ADD COLUMN IF NOT EXISTS change_type text DEFAULT 'edit';

-- 3. Add Indexes for performance
CREATE INDEX IF NOT EXISTS idx_kb_v1_status ON public.knowledge_base_v1 (review_status);
CREATE INDEX IF NOT EXISTS idx_kb_mod_type ON public.knowledge_base_modifications (change_type);
