# V1 vs 矩阵 product_name 差异预览（只读）

> 生成时间：2026-08-17；数据源为本地 PostgreSQL `knowledgebase_local`。本报告未修改数据库，也未切换 `use_supabase_matrix`。

- 差异总数：**0**
- 分类统计：{}
- 时间关系：{}
- 建议动作：{}
- 明确可回填候选：**0**（仅指已有 V1 且有 `button.submitted_at` 且矩阵证据晚于 V1；仍需人工批准）

## 字段说明

`matrix_product_name` 仅聚合 `product_matrix.is_configured = true` 的型号。`matrix_evidence_at` 是 `last_synced_at`、`product_matrix.update_time`、`button.submitted_at` 中最新时间；只有按钮提交审计才被视为可自动回填的可靠意图证据。

完整 787 条逐行清单见同名 CSV/JSON。下面列出所有明确可回填候选的 ID，供人工抽样：

| question_wiki_id | V1 product_name | 矩阵 product_name | V1 更新时间 | 按钮提交时间 |
| --- | --- | --- | --- | --- |

## 后续边界

- `matrix_only_missing_v1` 不可直接更新 V1，因为 V1 行不存在；应先确认是否为误导入、待恢复条目或合法矩阵孤儿。
- `matrix_newer` 但无按钮审计的条目只做人工复核，不自动回填。
- 在人工批准回填并重新对账前，不应把 `use_supabase_matrix` 切换为 `true`。
