# link_viewer CSS 陷阱清单（2026-09-17 整理）

## 1. kb-workbench 全局表格污染（extra_styles.css ~8289-8304）

```css
table th {
    background: #dceeff !important;
    color: var(--kb-workbench-ink) !important;
    ...
}
table td {
    background-color: var(--kb-workbench-surface) !important;
    color: var(--kb-workbench-ink) !important;
    ...
}
```

影响：所有未经防护的表格表头被强制染蓝 #dceeff；td 背景被强制，**tr 的 hover/状态背景会被 td 盖住不可见**。

对策：
- 定制表头：`background: <色> !important; color: <色> !important;`，选择器 specificity 需高于 `(0,0,0,2)`（如 `.xxx-table th` 是 (0,0,1,1)，够）。
- 行 hover/状态色必须写到 td 级：
  ```css
  .xxx-table tbody tr:hover td { background-color: <色> !important; }
  ```

## 2. styles.css 裸 th 规则

```css
th {
    background: linear-gradient(rgb(248,251,255), rgb(241,246,253));
    font-weight: 600;
    height: 48px;
    ...
}
```

无 !important， specificity (0,0,0,1)。定制时用类选择器即可覆盖，但要显式重置 height/font-weight 否则继承 48px 高等样式。

## 3. 按钮全局类

- `.primary-btn / .action-btn / .success-btn / .secondary-btn / .danger-btn / .btn-ghost`：styles.css 5586 行统一设 `min-height: 40px; padding: 9px 14px; border-radius: 14px`。
- 按钮实际颜色在 design-system.css（如 `.action-btn { border: 1px solid rgba(203,213,225,0.95); ... }`）。**只引 styles.css 不引 design-system.css 时按钮露出 UA 默认黑边框**（验证页必须两个都引，顺序与 index.html 一致）。
- 弹窗/工具栏内收敛按钮：用作用域覆盖，勿改全局类：
  ```css
  .mm-toolbar .action-btn { min-height: 30px; padding: 5px 12px; border-radius: 6px; font-size: 12px; box-shadow: none; }
  ```

## 4. 双份/多份重复定义

extra_styles.css 历史上多次"追加覆盖"（如 .mm-* 曾有 802-1082 紫色旧主题 + 1084-1470 蓝色覆盖两套）。改样式前先 grep 该类名的所有定义位置，确认改的是最终生效那份；理想做法是合并重写并删除旧段。

## 5. 其他

- `server.py` 静态响应带 `Cache-Control: no-store`，改完刷新即生效，无需改 `?v=` 版本号。
- 构建：`node build.js` 会从 index.html 生成 index.prod.html 与 dist/（替换为 .min 引用）；验证真实页面效果前要重新构建。
- Chrome 原生 CSS Nesting：`CSSStyleRule.cssRules` 对无嵌套规则返回空 CSSRuleList（truthy），遍历脚本需用 `rule.selectorText` 判普通规则、`rule.cssRules.length` 判递归，否则匹配结果为空。
