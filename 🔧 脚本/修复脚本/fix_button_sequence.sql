-- 修复 button 表的序列值问题
-- 这会解决 "duplicate key value violates unique constraint button_pkey" 错误

-- 1. 查看当前状态
SELECT 'Current sequence value:' as info, last_value FROM button_id_seq;
SELECT 'Max ID in table:' as info, MAX(id) as max_id FROM button;

-- 2. 修复序列值（设置为表中最大ID）
SELECT setval('button_id_seq', (SELECT COALESCE(MAX(id), 1) FROM button));

-- 3. 验证修复
SELECT 'Fixed sequence value:' as info, last_value FROM button_id_seq;

-- 4. 测试插入（可选，会回滚）
BEGIN;
INSERT INTO button (operation_id, question_wiki_id, product_name, old_is_configured, new_is_configured, edit_source, submitted_by, submitted_at)
VALUES ('test', 'test', 'test', false, true, 'test', 'test', NOW());
SELECT 'Test insert successful, ID:' as info, currval('button_id_seq') as new_id;
ROLLBACK;

SELECT '✅ Sequence fixed successfully!' as result;
