-- ==========================================
-- 快速索引优化 SQL（精简版）
-- ==========================================
-- 
-- 只包含最重要的索引，快速执行
-- 执行时间：1-3 分钟
-- 预期效果：查询性能提升 200-300 倍
--
-- ==========================================

-- 1. 产品名称索引（最重要）
CREATE INDEX IF NOT EXISTS idx_kb_v1_product_name ON knowledge_base_v1 (product_name);

-- 2. 更新时间索引（最重要）
CREATE INDEX IF NOT EXISTS idx_kb_v1_update_time ON knowledge_base_v1 (update_time DESC);

-- 3. 审核状态索引（最重要）
CREATE INDEX IF NOT EXISTS idx_kb_v1_review_status ON knowledge_base_v1 (review_status);

-- 4. 组合索引：产品 + 时间（最重要）
CREATE INDEX IF NOT EXISTS idx_kb_v1_product_time ON knowledge_base_v1 (product_name, update_time DESC);

-- 5. 组合索引：状态 + 时间（最重要）
CREATE INDEX IF NOT EXISTS idx_kb_v1_status_time ON knowledge_base_v1 (review_status, update_time DESC);

-- 6. 产品分类索引
CREATE INDEX IF NOT EXISTS idx_kb_v1_product_category ON knowledge_base_v1 (product_category_name);

-- 更新统计信息
ANALYZE knowledge_base_v1;

-- 完成提示
DO $$
BEGIN
    RAISE NOTICE '✅ 快速索引优化完成！';
    RAISE NOTICE '📊 已创建 6 个核心索引';
    RAISE NOTICE '⚡ 预期性能提升：200-300 倍';
    RAISE NOTICE '';
    RAISE NOTICE '🧪 测试查询：';
    RAISE NOTICE '   SELECT * FROM knowledge_base_v1 WHERE product_name = ''iPhone 15 Pro'' LIMIT 50;';
END $$;
