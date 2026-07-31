-- 8085 知识图谱一期回退：仅移除旁路图谱表。
-- 执行前先保存 kg_* 导出或数据库备份；不会修改 knowledge_base_v1 或 product_matrix。

DROP TABLE IF EXISTS kg_edge_events;
DROP TABLE IF EXISTS kg_edges;
DROP TABLE IF EXISTS kg_nodes;
