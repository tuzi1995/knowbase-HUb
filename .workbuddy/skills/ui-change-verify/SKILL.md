---
name: ui-change-verify
description: 验证 KnowBase Hub（link_viewer）前端样式改动的实际渲染效果。当修改了 link_viewer 下的 CSS（styles.css / extra_styles.css / design-system.css）或 JS 渲染逻辑、需要截图确认视觉效果、或排查"样式改了但没生效"的层叠冲突时使用。包含 playwright 驱动系统 Chrome 的截图/诊断脚本和本项目已知的 CSS 陷阱清单。
agent_created: true
---

# UI 改动验证流程（link_viewer / KnowBase Hub）

## 用途

修改 `KnowledgeBaseTool_Local/link_viewer/` 下的样式或渲染逻辑后，用真实浏览器渲染验证效果，并快速定位"改了没生效"的原因（层叠冲突、全局 !important 覆盖、缺失样式表等）。

## 前置条件

- 系统已安装 Google Chrome（`/Applications/Google Chrome.app`）。
- python venv 已装 playwright：`/Users/guoying/.workbuddy/binaries/python/envs/default/bin/pip install playwright`（只需装包，不用 `playwright install` 下载浏览器，用 channel="chrome" 复用系统 Chrome）。
- 用管理运行时：`/Users/guoying/.workbuddy/binaries/python/envs/default/bin/python`。

## 验证方式选择

1. **改动可静态复现**（弹窗、卡片等独立组件）：优先做"静态验证页"——在 `link_viewer/` 下建临时 `test_xxx.html`，引用与 `index.html` 完全相同的 css（含 design-system.css，顺序一致），复制目标 DOM，用模拟数据跑相同的渲染逻辑。放 link_viewer 目录内可保证相对引用（vendor/ 等）有效。
2. **需要完整应用状态**（登录、后端数据）：直接连 :8085 真实页面操作。
3. 两种都用 `scripts/snap_page.py` 截图。

## 标准流程

1. 改动代码后跑构建：`cd link_viewer && /Users/guoying/.workbuddy/binaries/node/versions/22.22.2-3/bin/node build.js`（重新生成 *.min.* 与 dist/、index.prod.html）。
2. 起静态服务（后台）：`cd link_viewer && python3 -m http.server 8899 --bind 127.0.0.1`。**不要直接用 file:// 打开验证页**——file:// 下 `document.styleSheets.cssRules` 被安全策略拦截，诊断脚本读不到任何规则，会误判"没有匹配规则"。
3. 截图：`scripts/snap_page.py <url> <输出png> [--width 1400 --height 960 --js "<内联脚本>"]`。
4. 效果不符预期时，用 `scripts/css_diag.py <url> "<CSS选择器>" <prop>` 列出该元素上所有匹配某属性的规则及来源文件（如 prop 填 `background|border|color`），找出谁覆盖了你的规则。
5. 验证完：停掉 8899 服务；临时验证页保留或删除视情况（项目有 test_*.html 先例）。

## 关键脚本

- `scripts/snap_page.py`：playwright 连接系统 Chrome（channel="chrome", headless, --no-sandbox）截图。Chrome CLI 的 --headless 在本环境会沙箱报错/卡死，不要用。
- `scripts/css_diag.py`：遍历所有 stylesheet（含 @media 嵌套），输出匹配元素的规则。**注意 Chrome 原生 CSS Nesting**：无嵌套规则的 `rule.cssRules` 是空 CSSRuleList 但 truthy，遍历必须以 `rule.selectorText` 为准、嵌套递归用 `rule.cssRules.length` 判断，否则会跳过所有普通规则（本 skill 的脚本已处理）。

## 本项目已知 CSS 陷阱（详见 references/link_viewer_css_pitfalls.md）

- `extra_styles.css` ~8294 行 kb-workbench 全局段：`table th { background:#dceeff !important }`、`table td { background-color:... !important }` 会覆盖一切表格样式。定制表头需 `!important` 反击且 specificity 要更高；行 hover / 状态行背景必须写到 **td 级**（tr 的背景会被 td 盖住看不见）。
- `styles.css` 裸 `th` 选择器有 `background: linear-gradient(...)` 和 `height:48px`。
- `.primary-btn/.action-btn/.success-btn/.icon-btn` 全局是大按钮（min-height 40px、radius 14px），实际颜色定义在 `design-system.css`。弹窗/工具栏内要收敛尺寸和权重时，用作用域选择器（如 `.mm-toolbar .action-btn`）覆盖，不要改全局类。
- `styles.css`/`extra_styles.css` 里大量历史重复定义，改动后必须用 grep/python 重新读文件验证落盘（见下）。
- `server.py` 已设 `Cache-Control: no-store`，改完刷新即生效，无需改 `?v=` 版本号。

## 重要：编辑落盘验证

Edit 工具对 `extra_styles.css` 的大块替换曾出现"返回成功但内容未落盘"的情况。对这两个大 CSS 文件，每次关键修改后立即重新读取目标行验证；批量修改优先用 python 脚本 `read_text → replace → write_text` 并做 md5 前后对比 + grep 断言。

## Resources

- `scripts/snap_page.py` — 截图脚本（playwright + 系统 Chrome）
- `scripts/css_diag.py` — CSS 层叠诊断脚本
- `references/link_viewer_css_pitfalls.md` — 本项目 CSS 陷阱详细清单
