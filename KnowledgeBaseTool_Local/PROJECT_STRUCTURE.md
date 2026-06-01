# 项目结构分类与说明

为了更好地管理 `KnowledgeBaseTool` 目录下的文件，我们对现有文件进行了逻辑分类。

## 1. 核心服务 (Core Service)
主要负责启动后端服务、处理评分逻辑和管理配置。
- **`server.py`**: 项目入口，Flask Web 服务主程序。
- **`scoring_logic.py`**: 核心评分逻辑模块。
- **`llm_score_evaluator.py`**: 调用 LLM 进行评分的模块。
- **`启动服务.bat`**: 快速启动服务的 Windows 批处理文件。
- **`KB1知识库评分工具.bat`**: 可能是旧版或别名的启动脚本。
- **`requirements.txt`**: Python 依赖包清单。
- **`product_catalog.json`**: 产品目录配置。
- **`scoring_config.json`**: 评分规则配置。
- **`supabase_config.json`**: 数据库连接配置。
- **`model_mappings.json`**: 模型映射配置。
- **`tag_pool.json`**: 标签池配置。

## 2. 前端应用 (Frontend)
存放 Web 界面的相关资源。
- **`link_viewer/`**: 前端根目录。
  - `index.html`: 主页面。
  - `app_v8.js`: 前端逻辑脚本。
  - `styles.css`, `extra_styles.css`: 样式表。
  - `Product_Manual.md`: 产品手册文档。

## 3. 数据与存储 (Data & Storage)
存放输入数据、输出结果、日志及数据库文件。
- **`instance/`**: 存放本地 SQLite 数据库 (`data.db`)。
- **`Excel_Data/`**: 存放待处理或已处理的 Excel 数据源文件。
- **`Output/`**: 存放生成的评分报告、CSV 缓存等输出文件。
- **`Backups/`**: 存放备份文件。
- **`Logs/`**: 存放运行日志 (`error_log.txt`, `process_log.txt`)。
- **`prompt/`**: 存放 LLM 提示词模板。

## 4. 数据库维护 (Database Maintenance)
用于数据库初始化、更新或迁移的 SQL 脚本。
- **`supabase_schema.sql`**: Supabase 数据库初始架构。
- **`create_kb_scores.sql`**: 创建评分表脚本。
- **`create_mod_table.sql`**: 创建修改记录表脚本。
- **`update_schema_v2.sql`, `update_schema_v3.sql`**: 数据库架构更新脚本。

## 5. 开发与调试工具 (Dev & Debug Tools)
用于开发过程中验证功能、检查数据或清理环境的脚本。建议后续归档至 `DevTools/` 目录。
- **`debug_*.py`**: 调试脚本 (如 `debug_kb.py`, `debug_score_data.py`)。
- **`check_*.py`**: 检查脚本 (如 `check_db_count.py`, `check_supabase_data.py`)。
- **`verify_*.py`**: 验证脚本 (如 `verify_setup.py`, `verify_sync_count.py`)。
- **`test_*.py`**: 测试脚本 (如 `test_import.py`, `test_scoring_cache.py`)。
- **`clean_data.py`**: 数据清理脚本。

## 6. 部署与打包 (Deployment)
用于项目打包和部署。
- **`package_deploy.py`**: 自动打包脚本。
- **`README_DEPLOY.txt`**: 部署说明文档。
- **`KnowledgeBaseTool_Deploy_*.zip`**: 生成的部署包。

## 7. 其他辅助脚本 (Scripts)
存放在 `Scripts/` 目录下的各类数据处理脚本。
- **`Scripts/`**: 包含 `process_*.py`, `generate_*.py` 等具体任务脚本。

---
**建议**: 为了保持根目录整洁，建议将 `Debug_Tools` 类别下的 `.py` 脚本移动到 `DevTools` 文件夹中（需注意调整 import 路径）。
