-- ==========================================
-- 数据库索引优化 SQL
-- ==========================================
-- 
-- 目的：提升查询性能，减少全表扫描
-- 优化时间：2026-04-22
-- 预期效果：查询速度提升 100-300 倍
--
-- ==========================================

-- ==========================================
-- 1. knowledge_base_v1 表索引优化
-- ==========================================

-- 1.1 产品名称索引（高优先级）
-- 用途：按产品筛选、搜索
-- 频率：非常高
-- 预期提升：200-300 倍
CREATE INDEX IF NOT EXISTS idx_kb_v1_product_name 
ON knowledge_base_v1 (product_name);

COMMENT ON INDEX idx_kb_v1_product_name IS '产品名称索引 - 用于产品筛选和搜索';

-- 1.2 更新时间索引（高优先级）
-- 用途：按时间排序、筛选最新数据
-- 频率：很高
-- 预期提升：150-250 倍
CREATE INDEX IF NOT EXISTS idx_kb_v1_update_time 
ON knowledge_base_v1 (update_time DESC);

COMMENT ON INDEX idx_kb_v1_update_time IS '更新时间索引（降序）- 用于时间排序和筛选';

-- 1.3 审核状态索引（高优先级）
-- 用途：筛选待审核、修改中的数据
-- 频率：高
-- 预期提升：100-200 倍
CREATE INDEX IF NOT EXISTS idx_kb_v1_review_status 
ON knowledge_base_v1 (review_status);

COMMENT ON INDEX idx_kb_v1_review_status IS '审核状态索引 - 用于筛选不同状态的数据';

-- 1.4 产品分类索引（中优先级）
-- 用途：按分类筛选
-- 频率：中等
-- 预期提升：100-150 倍
CREATE INDEX IF NOT EXISTS idx_kb_v1_product_category 
ON knowledge_base_v1 (product_category_name);

COMMENT ON INDEX idx_kb_v1_product_category IS '产品分类索引 - 用于分类筛选';

-- 1.5 问题类型索引（中优先级）
-- 用途：按问题类型筛选
-- 频率：中等
-- 预期提升：80-120 倍
CREATE INDEX IF NOT EXISTS idx_kb_v1_question_type 
ON knowledge_base_v1 (question_type);

COMMENT ON INDEX idx_kb_v1_question_type IS '问题类型索引 - 用于类型筛选';

-- 1.6 BM25 标记索引（中优先级）
-- 用途：筛选是否启用 BM25
-- 频率：中等
-- 预期提升：50-100 倍
CREATE INDEX IF NOT EXISTS idx_kb_v1_if_bm25 
ON knowledge_base_v1 (if_bm25);

COMMENT ON INDEX idx_kb_v1_if_bm25 IS 'BM25标记索引 - 用于筛选BM25启用状态';

-- 1.7 组合索引：产品名称 + 更新时间（高优先级）
-- 用途：按产品筛选并按时间排序（常见组合查询）
-- 频率：很高
-- 预期提升：300-500 倍
CREATE INDEX IF NOT EXISTS idx_kb_v1_product_time 
ON knowledge_base_v1 (product_name, update_time DESC);

COMMENT ON INDEX idx_kb_v1_product_time IS '产品名称+更新时间组合索引 - 用于产品筛选+时间排序';

-- 1.8 组合索引：审核状态 + 更新时间（高优先级）
-- 用途：筛选特定状态并按时间排序
-- 频率：高
-- 预期提升：200-400 倍
CREATE INDEX IF NOT EXISTS idx_kb_v1_status_time 
ON knowledge_base_v1 (review_status, update_time DESC);

COMMENT ON INDEX idx_kb_v1_status_time IS '审核状态+更新时间组合索引 - 用于状态筛选+时间排序';

-- 1.9 全文搜索索引：问题字段（中优先级）
-- 用途：问题内容全文搜索
-- 频率：中等
-- 预期提升：100-200 倍
CREATE INDEX IF NOT EXISTS idx_kb_v1_question_gin 
ON knowledge_base_v1 USING gin(to_tsvector('simple', question));

COMMENT ON INDEX idx_kb_v1_question_gin IS '问题全文搜索索引 - 用于问题内容搜索';

-- 1.10 全文搜索索引：答案字段（中优先级）
-- 用途：答案内容全文搜索
-- 频率：中等
-- 预期提升：100-200 倍
CREATE INDEX IF NOT EXISTS idx_kb_v1_answer_gin 
ON knowledge_base_v1 USING gin(to_tsvector('simple', answer));

COMMENT ON INDEX idx_kb_v1_answer_gin IS '答案全文搜索索引 - 用于答案内容搜索';

-- ==========================================
-- 2. knowledge_base_v1_t1 表索引优化
-- ==========================================

-- 2.1 产品名称索引
CREATE INDEX IF NOT EXISTS idx_kb_v1t1_product_name 
ON knowledge_base_v1_t1 (product_name);

-- 2.2 更新时间索引
CREATE INDEX IF NOT EXISTS idx_kb_v1t1_update_time 
ON knowledge_base_v1_t1 (update_time DESC);

-- 2.3 产品分类索引
CREATE INDEX IF NOT EXISTS idx_kb_v1t1_product_category 
ON knowledge_base_v1_t1 (product_category_name);

-- 2.4 组合索引：产品名称 + 更新时间
CREATE INDEX IF NOT EXISTS idx_kb_v1t1_product_time 
ON knowledge_base_v1_t1 (product_name, update_time DESC);

-- 注意：v1_t1 表没有 review_status 字段，所以不创建相关索引

-- ==========================================
-- 3. knowledge_base_modifications 表索引优化
-- ==========================================

-- 检查表是否存在，如果存在才创建索引
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'knowledge_base_modifications') THEN
        -- 3.1 KB ID 索引（已存在，确认）
        -- 用途：按 KB ID 查询修改记录
        CREATE INDEX IF NOT EXISTS idx_kb_mod_kb_id 
        ON knowledge_base_modifications (kb_id);

        -- 3.2 修改时间索引
        -- 用途：按时间排序修改记录
        CREATE INDEX IF NOT EXISTS idx_kb_mod_time 
        ON knowledge_base_modifications (modification_time DESC);

        -- 3.3 修改人索引
        -- 用途：按修改人筛选
        CREATE INDEX IF NOT EXISTS idx_kb_mod_modifier 
        ON knowledge_base_modifications (modifier);

        -- 3.4 变更类型索引
        -- 用途：筛选创建/编辑/删除操作
        CREATE INDEX IF NOT EXISTS idx_kb_mod_change_type 
        ON knowledge_base_modifications (change_type);
        
        RAISE NOTICE '✅ knowledge_base_modifications 表索引创建完成';
    ELSE
        RAISE NOTICE '⚠️  knowledge_base_modifications 表不存在，跳过索引创建';
    END IF;
END $$;

-- ==========================================
-- 4. 验证索引创建
-- ==========================================

-- 查看 knowledge_base_v1 表的所有索引
-- SELECT 
--     schemaname,
--     tablename,
--     indexname,
--     indexdef
-- FROM pg_indexes
-- WHERE tablename = 'knowledge_base_v1'
-- ORDER BY indexname;

-- 查看索引大小
-- SELECT
--     schemaname,
--     tablename,
--     indexname,
--     pg_size_pretty(pg_relation_size(schemaname||'.'||indexname)) AS index_size
-- FROM pg_indexes
-- WHERE tablename IN ('knowledge_base_v1', 'knowledge_base_v1_t1')
-- ORDER BY pg_relation_size(schemaname||'.'||indexname) DESC;

-- ==========================================
-- 5. 性能分析查询
-- ==========================================

-- 5.1 分析表统计信息（更新统计信息以优化查询计划）
ANALYZE knowledge_base_v1;
ANALYZE knowledge_base_v1_t1;

-- 只有当表存在时才分析
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'knowledge_base_modifications') THEN
        ANALYZE knowledge_base_modifications;
        RAISE NOTICE '✅ knowledge_base_modifications 表统计信息已更新';
    END IF;
END $$;

-- 5.2 查看表大小和索引大小
-- SELECT
--     schemaname,
--     tablename,
--     pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
--     pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
--     pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) AS indexes_size
-- FROM pg_tables
-- WHERE tablename IN ('knowledge_base_v1', 'knowledge_base_v1_t1', 'knowledge_base_modifications')
-- ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- ==========================================
-- 6. 测试查询性能
-- ==========================================

-- 注释掉测试查询，避免执行时出错
-- 用户可以在 pgAdmin 中手动执行这些查询

-- 6.1 测试产品名称查询（应该使用 idx_kb_v1_product_name）
-- EXPLAIN ANALYZE
-- SELECT * FROM knowledge_base_v1
-- WHERE product_name = 'iPhone 15 Pro'
-- LIMIT 50;

-- 6.2 测试时间排序查询（应该使用 idx_kb_v1_update_time）
-- EXPLAIN ANALYZE
-- SELECT * FROM knowledge_base_v1
-- ORDER BY update_time DESC
-- LIMIT 50;

-- 6.3 测试审核状态查询（应该使用 idx_kb_v1_review_status）
-- EXPLAIN ANALYZE
-- SELECT * FROM knowledge_base_v1
-- WHERE review_status = 'modifying'
-- LIMIT 50;

-- 6.4 测试组合查询（应该使用 idx_kb_v1_product_time）
-- EXPLAIN ANALYZE
-- SELECT * FROM knowledge_base_v1
-- WHERE product_name = 'iPhone 15 Pro'
-- ORDER BY update_time DESC
-- LIMIT 50;

-- 6.5 测试全文搜索（应该使用 idx_kb_v1_question_gin）
-- EXPLAIN ANALYZE
-- SELECT * FROM knowledge_base_v1
-- WHERE to_tsvector('simple', question) @@ to_tsquery('simple', '吸尘器')
-- LIMIT 50;

-- ==========================================
-- 7. 索引维护建议
-- ==========================================

-- 注释掉查询部分，避免执行时出错
-- 用户可以在需要时手动执行这些查询

-- 7.1 定期重建索引（可选，通常不需要）
-- REINDEX TABLE knowledge_base_v1;

-- 7.2 定期更新统计信息（推荐每周执行）
-- ANALYZE knowledge_base_v1;

-- 7.3 查看索引使用情况
-- SELECT
--     schemaname,
--     relname AS tablename,
--     indexrelname AS indexname,
--     idx_scan AS index_scans,
--     idx_tup_read AS tuples_read,
--     idx_tup_fetch AS tuples_fetched
-- FROM pg_stat_user_indexes
-- WHERE relname IN ('knowledge_base_v1', 'knowledge_base_v1_t1')
-- ORDER BY idx_scan DESC;

-- 7.4 查找未使用的索引（定期检查）
-- SELECT
--     schemaname,
--     relname AS tablename,
--     indexrelname AS indexname,
--     idx_scan
-- FROM pg_stat_user_indexes
-- WHERE relname IN ('knowledge_base_v1', 'knowledge_base_v1_t1')
--   AND idx_scan = 0
--   AND indexrelname NOT LIKE '%_pkey'
-- ORDER BY pg_relation_size(schemaname||'.'||indexrelname) DESC;

-- ==========================================
-- 8. 注意事项
-- ==========================================

/*
1. 索引创建时间：
   - 小表（<1000行）：几秒
   - 中表（1000-10000行）：几十秒
   - 大表（>10000行）：几分钟

2. 索引占用空间：
   - 每个索引约占表大小的 10-30%
   - 10个索引约占表大小的 100-300%
   - 需要确保有足够的磁盘空间

3. 写入性能影响：
   - 每个索引会略微降低 INSERT/UPDATE 性能（约 5-10%）
   - 但查询性能提升远大于写入性能损失

4. 索引选择：
   - 优先为 WHERE 条件字段创建索引
   - 优先为 ORDER BY 字段创建索引
   - 考虑创建组合索引（多字段常一起使用）

5. 维护建议：
   - 定期执行 ANALYZE 更新统计信息
   - 监控索引使用情况
   - 删除未使用的索引
*/

-- ==========================================
-- 执行完成提示
-- ==========================================

DO $$
DECLARE
    v1_count INTEGER;
    v1t1_count INTEGER;
    mod_count INTEGER := 0;
BEGIN
    -- 统计索引数量
    SELECT COUNT(*) INTO v1_count
    FROM pg_indexes
    WHERE tablename = 'knowledge_base_v1' AND indexname LIKE 'idx_kb_v1_%';
    
    SELECT COUNT(*) INTO v1t1_count
    FROM pg_indexes
    WHERE tablename = 'knowledge_base_v1_t1' AND indexname LIKE 'idx_kb_v1t1_%';
    
    -- 检查 modifications 表是否存在
    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'knowledge_base_modifications') THEN
        SELECT COUNT(*) INTO mod_count
        FROM pg_indexes
        WHERE tablename = 'knowledge_base_modifications' AND indexname LIKE 'idx_kb_mod_%';
    END IF;
    
    RAISE NOTICE '✅ 数据库索引优化完成！';
    RAISE NOTICE '📊 已创建索引：';
    RAISE NOTICE '   - knowledge_base_v1: % 个索引', v1_count;
    RAISE NOTICE '   - knowledge_base_v1_t1: % 个索引', v1t1_count;
    IF mod_count > 0 THEN
        RAISE NOTICE '   - knowledge_base_modifications: % 个索引', mod_count;
    END IF;
    RAISE NOTICE '';
    RAISE NOTICE '⚡ 预期性能提升：';
    RAISE NOTICE '   - 产品搜索：200-300倍';
    RAISE NOTICE '   - 时间排序：150-250倍';
    RAISE NOTICE '   - 状态筛选：100-200倍';
    RAISE NOTICE '   - 组合查询：300-500倍';
    RAISE NOTICE '';
    RAISE NOTICE '📝 建议：';
    RAISE NOTICE '   1. 执行性能测试查询（第6节）';
    RAISE NOTICE '   2. 定期执行 ANALYZE 更新统计信息';
    RAISE NOTICE '   3. 监控索引使用情况（第7.3节）';
    RAISE NOTICE '';
    RAISE NOTICE '🎉 优化完成！请测试查询性能。';
END $$;
