# KnowledgeBase Hub UI/UX 整体改版方案

## 1. 文档目的

本文档用于沉淀 `KnowledgeBase Hub` 项目当前 Web 工作台的整体 UI/UX 改版方案，目标是：

- 明确当前页面存在的核心可用性与视觉问题
- 判断改版方案在现有代码结构下的可行性与实施风险
- 给出一版可执行的页面结构草图与信息架构方案
- 制定分阶段改造优先级，避免一次性大改导致风险失控
- 为后续前端实施提供到文件级别的改造蓝图

当前前端主入口位于：

- [index.html](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/index.html)
- [styles.css](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/styles.css)
- [extra_styles.css](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/extra_styles.css)
- [design-system.css](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/design-system.css)
- [app_v8.js](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/app_v8.js)

## 2. 当前系统现状概述

当前页面本质上已经不是“单功能工具页”，而是一个典型的本地数据治理工作台。前端页面已经承载：

- `9` 个一级模块
- `30+` 个弹窗
- 大量宽表格、筛选面板、批量操作工具栏
- 多类危险操作与管理操作并存

已识别的一级模块包括：

- 知识库管理
- 机型矩阵管理
- 多媒体预览
- 知识库评分
- 知识库治理
- 冗余自查
- 修改记录
- 归档管理
- 智能映射

这意味着当前系统已经从“功能可用”进入“复杂工作台治理”的阶段，原有的扁平化导航与单屏堆叠式布局开始明显失效。

## 3. 核心问题诊断

## 3.1 信息架构问题

- 顶部将 `9` 个模块作为同级 Tab 平铺，缺少业务分组与任务层级
- 首次进入页面后默认进入 `知识库管理`，但没有首页概览、常用入口或最近使用入口
- 用户从“管理数据”切换到“治理/评分/归档/日志”时，上下文缺乏过渡，认知成本高

相关结构可参考：

- [index.html:L264-L275](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/index.html#L264-L275)
- [app_v8.js:L803-L862](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/app_v8.js#L803-L862)

## 3.2 单屏过载问题

以“知识库管理”为例，当前首屏同时承载：

- 导入模式选择
- 文件导入
- 查重预览
- 同步此刻到前刻
- 一键同步下游
- 此刻库/前刻库切换
- 多条件搜索
- 标签筛选
- 状态筛选
- 产品分类筛选
- 批量操作按钮
- 超宽表格与分页

这会直接带来两个问题：

- 首次上手时用户无法快速理解主任务
- 高频浏览操作与低频高危操作被混放，误触概率上升

相关区域：

- [index.html:L280-L477](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/index.html#L280-L477)
- [index.html:L487-L605](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/index.html#L487-L605)

## 3.3 视觉系统不统一

当前前端样式存在多源并行问题：

- `design-system.css` 中已经定义了较完整的新设计系统
- `styles.css` 中包含旧样式、补丁样式、覆盖样式
- `index.html` 中还内联了较长样式片段
- 同类组件在不同模块中呈现出不同圆角、不同背景、不同按钮视觉

典型表现：

- 同一个卡片系统既有 `8px` 圆角，也有 `20px` 圆角
- `header-info`、`main`、按钮、卡片容器等样式在后续区域被二次覆盖
- 造成“新版工作台 + 旧版页面碎片”并存的观感

相关样式来源：

- [design-system.css:L152-L245](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/design-system.css#L152-L245)
- [styles.css:L1138-L1145](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/styles.css#L1138-L1145)
- [styles.css:L1990-L2002](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/styles.css#L1990-L2002)
- [styles.css:L2178-L2287](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/styles.css#L2178-L2287)

## 3.4 表格阅读与操作负担过重

多个模块都是宽表格工作模式，但缺少有效的阅读减负机制：

- 默认列过多
- 长文本列占宽
- 核心列和次要列没有明显优先级
- 操作按钮分散
- 详情查看与编辑大量依赖弹窗
- 对比场景下横向滚动频繁

高风险区域：

- [index.html:L427-L452](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/index.html#L427-L452)
- [index.html:L668-L688](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/index.html#L668-L688)
- [index.html:L1175-L1198](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/index.html#L1175-L1198)
- [index.html:L1344-L1378](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/index.html#L1344-L1378)

## 3.5 交互模式不统一

当前不同模块的筛选、搜索、统计、空状态、危险操作提示风格不一致：

- 治理页已经较成熟，具备摘要条和高级条件入口
- 多媒体页和修改记录页仍偏平铺式堆控件
- 智能映射、冗余自查接近“流程工作台”，但缺少统一的阶段式视觉框架

这会导致用户在切换模块时产生重新学习成本。

## 4. 改版目标

本次改版不以“单纯变好看”为目标，而以以下四个结果为目标：

- 降低首次上手成本
- 降低高频操作认知负担
- 提高表格类页面的扫描效率
- 建立统一且可扩展的设计与组件规范

设计原则如下：

- 任务优先，不是组件优先
- 首屏只展示高频操作
- 危险动作后置、弱化、隔离
- 重要信息先摘要，再明细
- 统一交互模式，减少跨模块学习成本

## 5. 可行性评估

## 5.1 总体结论

整体方案 `可行`，但应拆阶段推进，不建议一次性推翻重做。

## 5.2 为什么可行

### 1. 导航重构可行

当前模块切换主要依赖：

- 统一的 `view id`
- `tab-*` 按钮 id
- `switchTab(tabId)` 方法

这意味着导航按钮的视觉位置可以改变，但底层切换逻辑可以保留。

参考：

- [app_v8.js:L803-L862](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/app_v8.js#L803-L862)

### 2. 页面框架可改

当前页面本质是 `#mainContent` 下多视图显示/隐藏，因此完全适合改造成：

- 左侧分组导航
- 右侧内容面板
- 顶部全局状态栏

而不需要改后端接口。

### 3. 视觉统一必要且可做

现有样式覆盖较多，说明当前视觉混乱不是“感觉问题”，而是代码结构层面的事实。统一视觉规范将明显降低后续维护成本。

### 4. 核心页瘦身可行

知识库管理、矩阵管理、评分等模块顶部工具栏虽复杂，但大多数是 DOM 结构和布局问题，不是深层逻辑耦合。

## 5.3 风险点

### 1. 样式联动风险

- `styles.css` 中存在多轮覆盖
- sticky、transform、z-index 叠加较多
- 改大布局时需重点验证表格表头、modal 层级与滚动容器表现

参考：

- [styles.css:L2939-L3011](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/styles.css#L2939-L3011)

### 2. 弹窗体系风险

当前大量弹窗通过 `style.display = 'block'/'none'` 控制，且有大量内联 `onclick`。

结论：

- 不能一开始就全面替换成 Drawer
- 应先做局部试点

### 3. 响应式返工风险

当前已存在多段断点规则，改为左侧导航后，窄屏和中屏布局需要重新设计折叠逻辑。

## 6. 新信息架构方案

建议将原顶部 `9` 个平级 Tab 改为左侧分组导航。

### 6.1 新导航分组

#### A. 核心数据

- 知识库管理
- 机型矩阵管理
- 多媒体预览

#### B. 质量管控

- 知识库评分
- 知识库治理
- 冗余自查

#### C. 工具与映射

- 智能映射

#### D. 日志与归档

- 修改记录
- 归档管理

### 6.2 导航结构意图

- 让用户知道“我现在是在做数据维护，还是做质量治理，还是看日志归档”
- 让相关模块更容易形成心智路径
- 给后续增加“首页概览”“最近使用”“收藏模块”预留位置

## 7. 整体页面结构草图

```text
+--------------------------------------------------------------------------------------+
| K-Matrix 助手                     [使用说明] [当前用户] [环境状态] [退出]           |
+----------------------+---------------------------------------------------------------+
| 核心数据             | 页面标题 + 摘要说明 + 关键状态                                |
| - 知识库管理         |---------------------------------------------------------------|
| - 机型矩阵管理       | 快捷操作区：搜索 / 新增 / 刷新 / 导出                         |
| - 多媒体预览         | 高危操作入口：更多操作 ▼                                      |
|                      |---------------------------------------------------------------|
| 质量管控             | 条件区：基础筛选 / 高级筛选 / 当前启用条件摘要                |
| - 知识库评分         |---------------------------------------------------------------|
| - 知识库治理         | 数据区：表格 / 统计摘要 / 空状态 / loading                    |
| - 冗余自查           |---------------------------------------------------------------|
|                      | 分页区：总数 / 页大小 / 前后翻页                               |
| 工具与映射           |---------------------------------------------------------------|
| - 智能映射           | 右侧详情面板（未来阶段可接入 Drawer）                         |
|                      |                                                               |
| 日志与归档           |                                                               |
| - 修改记录           |                                                               |
| - 归档管理           |                                                               |
+----------------------+---------------------------------------------------------------+
```

## 8. 页面级改版方案

## 8.1 全局框架层

### 改造目标

- 用统一后台布局承载所有模块
- 顶部只放全局信息
- 左侧只放导航
- 每个业务模块在右侧主内容区独立呈现

### 顶部栏建议内容

- 系统标题
- 当前模块名称
- 使用说明入口
- 当前用户
- 可选状态区：本地环境 / 数据源状态 / 最近同步时间

### 左侧导航建议

- 分组标题清晰
- 当前页高亮
- 支持折叠分组
- 保留现有 `switchTab()` 逻辑

## 8.2 知识库管理页

### 当前问题

- 首屏承担过多任务
- 导入和同步过于抢眼
- 高频搜索与低频维护操作混杂

### 改造方案

分成三个层次：

- 第一层：页面摘要与主操作
- 第二层：基础筛选与高级筛选
- 第三层：数据表格与详情

#### 首屏结构建议

```text
页面标题：知识库管理
说明：维护 V1 / V1T-1 知识库内容，支持搜索、编辑、导出与同步

[搜索框] [状态筛选] [分类筛选] [高级筛选▼] [新增] [刷新] [导出]
[更多操作▼]
  - 导入 Excel
  - 查重预览
  - 同步此刻到前刻
  - 一键同步下游
  - AI 配置
  - 管理型号库
  - 显示列

[数据摘要卡]
  - 当前数据源：此刻库 / 前刻库
  - 当前结果数
  - 当前已启用筛选条件

[表格]
```

### 收益

- 把低频维护动作后置
- 用户首屏只聚焦“查、看、改”
- 高危动作与日常动作隔离

## 8.3 机型矩阵管理页

### 当前问题

- 搜索工具栏过长
- 多选机型、分类筛选、列筛选、批量提交、提交日志全在首屏平铺

### 改造方案

建议拆成四层：

- 页面头：说明 + 当前状态
- 条件层：问题搜索、型号筛选、分类筛选
- 操作层：提交已选修改 / 提交全量修改 / 提交日志 / 导出
- 表格层：矩阵本体

其中“复制机型配置”“机型映射配置”“同步此刻库”应放入“更多操作”。

## 8.4 知识库评分页

### 当前问题

- 工具组较多
- 抽样、配置、筛选、评分操作混排

### 改造方案

按“数据准备 -> 筛选 -> 批量执行 -> 表格结果”顺序重组：

- 数据准备区：同步此刻库、抽样
- 配置区：API 配置、评分标准、操作库管理
- 筛选区：状态、问题、产品
- 执行区：批量评分、全量评分、导出

## 8.5 知识库治理页

### 当前评价

治理页已经是当前系统中比较成熟的交互形态，应作为其他模块的参考模板。

优点：

- 有摘要区域
- 有高级条件入口
- 有筛选状态反馈

建议：

- 保持该模块结构
- 仅将视觉风格统一到新的全局框架

## 8.6 多媒体预览页

### 当前问题

- 筛选区仍偏传统工具页
- 标签筛选逻辑说明与动作区分散

### 改造方案

- 将“录入区”和“筛选区”明确拆成两个卡片
- 批量添加与导入独立成“批量操作”卡片
- 标签逻辑与筛选摘要结合显示

## 8.7 冗余自查 / 智能映射

这两个模块本质是“流程型工作台”，应采用阶段式呈现：

- 模块一：准备数据
- 模块二：执行分析
- 模块三：人工决策工作台
- 模块四：导出 / 提交 / 归档

建议使用编号步骤头，例如：

- Step 1 数据准备
- Step 2 参数设置
- Step 3 结果工作台
- Step 4 提交与归档

这样比当前“模块一/模块二/模块三”更容易理解且更接近专业工作流产品。

## 8.8 修改记录 / 归档管理

### 当前问题

- 是典型的后台管理页，但视觉结构偏旧
- 首屏字段过多，查询区太长

### 改造方案

- 优先改成统一后台查询页样式
- 查询项按“常用项默认展开、次要项折叠”
- 增加“当前筛选摘要”
- 默认精简表格列

## 9. 组件规范建议

## 9.1 按钮体系

建议统一为四级：

- Primary：主操作，如搜索、保存、提交
- Secondary：次级动作，如刷新、导出、查看日志
- Ghost：轻量入口，如帮助、关闭、辅助跳转
- Danger：删除、覆盖、同步清空类操作

规则：

- 同一行最多一个 Primary
- Danger 不与 Primary 并列抢视觉焦点
- 危险操作尽量归入二级菜单或确认流程

## 9.2 卡片体系

建议统一：

- 圆角：`12px` 或 `16px`
- 边框：低对比浅边框
- 阴影：弱阴影，避免卡片层层隆起
- 页面背景：浅灰蓝工作台底色

## 9.3 筛选区体系

统一为三段：

- 基础筛选行
- 高级筛选折叠区
- 当前已启用条件摘要

优先参考治理页模式。

## 9.4 表格体系

统一规则：

- 默认只展示核心列
- 长文本列支持省略 + 查看详情
- 关键标识列尽量靠左
- 操作列尽量固定在右侧
- 表头 sticky
- 空状态与 loading 状态统一

## 9.5 详情展示体系

后续建议引入两种详情模式：

- Modal：轻量确认、配置、导入
- Drawer：详情查看、记录对比、局部编辑

不建议继续把所有详情交互都塞进全屏弹窗。

## 10. 分阶段改造优先级

## P0 导航与框架重构

### 目标

- 把顶部平铺导航改成左侧分组导航
- 建立统一顶栏与内容区框架

### 涉及文件

- [index.html](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/index.html)
- [styles.css](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/styles.css)

### 风险等级

- 中

### 收益等级

- 极高

## P1 视觉规范统一

### 目标

- 收敛设计系统
- 清理重复样式覆盖
- 统一按钮、表单、卡片、间距、圆角

### 涉及文件

- [design-system.css](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/design-system.css)
- [styles.css](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/styles.css)
- [extra_styles.css](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/extra_styles.css)

### 风险等级

- 中

### 收益等级

- 极高

## P2 核心页首屏瘦身

### 目标

- 优先重构知识库管理、机型矩阵管理
- 收纳低频高危动作
- 保留高频浏览与编辑动作在首屏

### 涉及文件

- [index.html](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/index.html)
- [app_v8.js](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/app_v8.js)
- [styles.css](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/styles.css)

### 风险等级

- 中

### 收益等级

- 高

## P3 表格交互升级

### 目标

- 默认列策略优化
- 表头 sticky
- 操作列收束
- 长文本查看体验优化

### 涉及文件

- [styles.css](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/styles.css)
- [app_v8.js](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/app_v8.js)

### 风险等级

- 中

### 收益等级

- 高

## P4 局部 Drawer 试点

### 目标

- 先选择 `知识库详情/编辑` 与 `修改记录详情` 试点
- 验证右侧详情面板模式

### 涉及文件

- [index.html](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/index.html)
- [app_v8.js](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/app_v8.js)
- [styles.css](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/styles.css)

### 风险等级

- 中高

### 收益等级

- 中高

## 11. 推荐实施顺序

建议按如下顺序推进：

### 阶段 1

- P0 导航与框架重构

### 阶段 2

- P1 视觉规范统一

### 阶段 3

- P2 核心页首屏瘦身

### 阶段 4

- P3 表格交互升级

### 阶段 5

- P4 局部 Drawer 试点

## 12. 文件级改造蓝图

## 12.1 [index.html](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/index.html)

需要改造内容：

- 顶部导航结构改为侧边栏结构
- 增加全局框架容器
- 重排 `知识库管理` 与 `机型矩阵管理` 的工具区结构
- 为“更多操作”预留容器
- 为未来 Drawer 容器预留挂载点

## 12.2 [styles.css](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/styles.css)

需要改造内容：

- 收敛多轮覆盖样式
- 重建全局工作台布局样式
- 统一卡片、按钮、表单、表格视觉
- 重新定义响应式断点下的导航折叠逻辑

## 12.3 [design-system.css](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/design-system.css)

需要改造内容：

- 作为未来统一设计令牌来源
- 保留按钮、圆角、间距、色彩规范
- 逐步上收 `styles.css` 中重复定义

## 12.4 [extra_styles.css](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/extra_styles.css)

需要改造内容：

- 清点仍在使用的补充样式
- 迁移有价值样式到主体系
- 减少长期“外挂补丁”状态

## 12.5 [app_v8.js](file:///Users/guoying/AI建设和学习/One/KnowBase%20Hub/KnowledgeBaseTool_Local/link_viewer/app_v8.js)

需要改造内容：

- 保留 `switchTab()` 现有逻辑
- 给新导航结构补绑定
- 支持“更多操作”菜单切换
- 后续支持 Drawer 试点交互

## 13. 不建议立即做的事情

以下事项不建议作为第一阶段实施内容：

- 不要一上来全面替换所有弹窗
- 不要一开始就重做所有 9 个模块
- 不要先做动效、毛玻璃、重视觉包装
- 不要先引入复杂前端框架迁移
- 不要先做路由系统重写

原因：

- 当前最缺的是结构清晰与视觉统一，不是技术栈升级

## 14. 最终结论

本方案方向正确，且在当前代码结构下具备明确可行性。

最稳妥的执行方式不是“大改版一次完成”，而是：

- 先重做框架层
- 再统一视觉层
- 再优化核心高频页面
- 再升级表格体验
- 最后小范围试点 Drawer

如果后续进入实施阶段，建议优先从：

- `P0 导航与框架重构`
- `P1 视觉规范统一`

两项开始。

这样既能迅速提升整体专业感，又不会在第一步就碰到最复杂的交互替换风险。

## 15. 当前实施状态与下一步计划（更新至 2026-05）

### 15.1 已实现内容
- **P0 导航与框架重构**：已完全落地。顶部平铺导航已成功重构为左侧分组导航（核心数据、质量管控、工具与映射、日志与归档），全局工作台结构（Workbench Layout）已建立。
- **P1 视觉规范统一**：部分落地。已引入 `design-system.css` 作为基础设计系统，统一了现代化的按钮（Primary/Secondary/Ghost/Danger）、输入框、卡片及弹窗样式。
- **P2 核心页首屏瘦身**：核心模块已大幅度优化。
  - `知识库管理`：低频及高危操作（如导入 Excel、同步此刻到前刻、一键同步下游）已全部收纳至“更多操作 ▼”下拉菜单中，首屏更聚焦于搜索与浏览。
  - `机型矩阵管理`：已重构为清晰的“页面头 - 条件层 - 操作层 - 表格层”四层结构，高危批量操作被合理隔离。
  - `知识库治理`：已实装高级条件折叠面板（Collapsible Filter）以及当前启用条件摘要。

### 15.2 计划外但已落地的优秀优化
- **标签筛选的 Modal 化改造**：原始文档仅建议“多媒体页标签逻辑与筛选摘要结合”，但实际落地时，我们在“知识库管理/多媒体”中将复杂的“标签多选下拉框”彻底重构为一个独立的 Modal 弹窗（`kbTagFilterModal`）。它由一个带数量角标的按钮触发，不仅完美解决了原下拉框被挤压、遮挡底部操作按钮的 Bug，还极大地释放了首屏筛选栏的空间。

### 15.3 当前执行顺序（建议按此逐项推进）
- **步骤 1：P1 视觉收口优先**
  - 先统一卡片、容器、表格、筛选区、弹窗的表面语言，清理仍在覆盖设计系统的旧样式。
  - 目标不是增加新视觉，而是让现有视觉真正统一。
- **步骤 2：P3 表格交互升级**
  - 优先优化默认列、长文本阅读、Sticky Header 和操作列收束。
- **步骤 3：P4 局部 Drawer 试点**
  - 先在 `知识库详情/编辑` 或 `修改记录详情` 做单点试验，再决定是否扩展。

### 15.4 逐项优化与人工验收原则
- 每次只推进一个明确的优化点，避免同时改动多个视觉层。
- 每完成一个点，必须给出可人工检查的验收方式。
- 人工验收优先看：视觉是否统一、是否影响现有功能、是否存在样式回退。
- 若该点通过，再进入下一点。
