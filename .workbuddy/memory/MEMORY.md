# 项目长期笔记（KnowBase Hub / knowbase_hub_8085）

## 前端结构速查

- 前端在 `KnowledgeBaseTool_Local/link_viewer/`：index.html（开发版）→ build.js 生成 index.prod.html 与 dist/（引用换 .min）。
- 全局主色 `--primary-color: #2563eb`（styles.css :root）；按钮颜色定义在 design-system.css。
- 服务 :8085 由 server.py（Python）提供，静态响应 no-store，改完刷新即生效。

## UI 改版工作方式（用户约定）

- 需求边界严格限定在**视觉层面与微文案**，保留现有操作习惯与功能架构；改动前先出方案预览再动手。
- 机型分类映射弹窗（2026-09-17 已完成改版）：型号**不折叠、全量显示**是用户的明确要求。

## 验证工具链

- 项目级 skill `ui-change-verify`（.workbuddy/skills/）：playwright 驱动系统 Chrome 截图、CSS 层叠诊断脚本、link_viewer CSS 陷阱清单（kb-workbench 全局 !important 表格污染、双份定义、按钮全局类等）。改 link_viewer 样式时先加载它。

## 已知坑

- Edit 工具对超大 CSS 文件（styles.css/extra_styles.css）可能出现"成功未落盘"，关键修改用 python 直写 + md5/grep 验证。
- extra_styles.css 后段有多代互相打架的 productManagerView 高度规则（auto/100vh/上限混杂），11256/11290 行 `.kb-section { flex:0 0 auto !important }` 特异度极高；要改其布局必须逐字复用同选择器写在文件末尾反杀。方案 A（满幅工作台，2026-10-08）即以此方式落地。
- 给带 hidden 属性的视图加 `display:flex !important` 会压过 UA 的 display:none，必须配 `[hidden] { display:none !important }`。
- :8085 测试登录凭据 admin/123456（DevTools/test_matrix_clone_review.py）。
