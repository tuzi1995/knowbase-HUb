-- ==========================================
-- 修复导入错误：为 knowledge_base_v1 表添加缺失字段
-- ==========================================
-- 执行此脚本前请确保已备份数据库
-- ==========================================

-- 为 knowledge_base_v1 表添加新字段
ALTER TABLE IF EXISTS knowledge_base_v1
    ADD COLUMN IF NOT EXISTS image_urls JSONB,
    ADD COLUMN IF NOT EXISTS video_urls JSONB,
    ADD COLUMN IF NOT EXISTS file_urls JSONB,
    ADD COLUMN IF NOT EXISTS link_type TEXT,
    ADD COLUMN IF NOT EXISTS link_url TEXT;

-- 删除旧字段（如果存在）
ALTER TABLE IF EXISTS knowledge_base_v1
    DROP COLUMN IF EXISTS answer_info,
    DROP COLUMN IF EXISTS urls;

-- 为 knowledge_base_v1_t1 表添加新字段
ALTER TABLE IF EXISTS knowledge_base_v1_t1
    ADD COLUMN IF NOT EXISTS image_urls JSONB,
    ADD COLUMN IF NOT EXISTS video_urls JSONB,
    ADD COLUMN IF NOT EXISTS file_urls JSONB,
    ADD COLUMN IF NOT EXISTS link_type TEXT,
    ADD COLUMN IF NOT EXISTS link_url TEXT;

-- 删除旧字段（如果存在）
ALTER TABLE IF EXISTS knowledge_base_v1_t1
    DROP COLUMN IF EXISTS answer_info,
    DROP COLUMN IF EXISTS urls;

-- 验证字段是否添加成功
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'knowledge_base_v1' 
  AND column_name IN ('image_urls', 'video_urls', 'file_urls', 'link_type', 'link_url')
ORDER BY column_name;
