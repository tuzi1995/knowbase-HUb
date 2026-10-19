-- Rename the existing tag records so item associations keep their original IDs.
BEGIN;
SET LOCAL lock_timeout = '15s';
LOCK TABLE public.kb_tags, public.kb_item_tags IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    mapping record;
BEGIN
    FOR mapping IN
        SELECT * FROM (VALUES
            ('618保价', '交易–618保价'),
            ('报错-重置解决', '异常恢复–重置解决'),
            ('产品对比', '导购–产品对比'),
            ('错误码', '异常–错误码提示'),
            ('电量 15%', '充电–电量15%'),
            ('电量 20%', '充电–电量20%'),
            ('订单购买', '交易–下单流程'),
            ('联网', '设备–配网联网'),
            ('轻拖', '清洁–轻拖模式'),
            ('洗地机全品类对比', '导购–洗地机品类对比'),
            ('延保', '服务–延保购买'),
            ('重启', '异常恢复–设备重启'),
            ('转人工', '客服–转人工')
        ) AS names(old_name, new_name)
    LOOP
        IF EXISTS (SELECT 1 FROM public.kb_tags WHERE name = mapping.old_name) THEN
            UPDATE public.kb_tags
               SET name = mapping.new_name, updated_at = CURRENT_TIMESTAMP
             WHERE name = mapping.old_name;
        ELSIF NOT EXISTS (SELECT 1 FROM public.kb_tags WHERE name = mapping.new_name) THEN
            RAISE EXCEPTION 'Required tag missing: %', mapping.old_name;
        END IF;
    END LOOP;
END $$;

DELETE FROM public.kb_item_tags
WHERE tag_id IN (SELECT id FROM public.kb_tags WHERE name = 'E2E临时标签');
DELETE FROM public.kb_tags WHERE name = 'E2E临时标签';
COMMIT;
