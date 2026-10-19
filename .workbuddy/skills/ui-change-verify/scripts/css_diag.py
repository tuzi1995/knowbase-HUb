#!/usr/bin/env python3
"""CSS 层叠诊断：列出作用于指定元素的所有匹配某属性的规则及来源文件。

用法:
  css_diag.py <url> "<CSS选择器>" [属性正则] [--wait 800]

示例:
  css_diag.py http://127.0.0.1:8899/test.html ".mm-category-table thead th" "background|color"
  css_diag.py http://127.0.0.1:8899/test.html ".mm-toolbar .action-btn" "border"

输出: computed 计算值 + rules 匹配规则列表（来源文件 | 选择器 | 声明）。
用法要点:
  - url 必须 http(s)；file:// 下 styleSheets.cssRules 抛 SecurityError，规则列表会为空。
  - 遍历兼容 Chrome 原生 CSS Nesting：以 selectorText 判断普通规则，cssRules.length>0 才递归。
"""
import argparse
import json
from playwright.sync_api import sync_playwright

JS = """({sel, propRe}) => {
  const el = document.querySelector(sel);
  if (!el) return { error: 'selector not found: ' + sel };
  const re = new RegExp(propRe, 'i');
  const out = { computed: {}, rules: [] };
  const cs = getComputedStyle(el);
  for (const k of ['backgroundColor', 'backgroundImage', 'color', 'borderColor',
                   'borderRadius', 'height', 'fontSize', 'fontWeight']) {
    out.computed[k] = cs[k];
  }
  const walk = (list, sheetName) => {
    for (const rule of list) {
      if (rule.selectorText) {
        try {
          if (el.matches(rule.selectorText) && re.test(rule.cssText)) {
            out.rules.push(sheetName + ' | ' + rule.selectorText + ' | ' + rule.cssText.slice(0, 240));
          }
        } catch (e) {}
      }
      if (rule.cssRules && rule.cssRules.length) walk(rule.cssRules, sheetName);
    }
  };
  for (const sheet of document.styleSheets) {
    const name = sheet.href ? sheet.href.split('/').pop() : 'inline';
    try { walk(sheet.cssRules, name); }
    catch (e) { out.rules.push('ERR ' + name + ': ' + e.message); }
  }
  return out;
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('url')
    ap.add_argument('selector')
    ap.add_argument('prop', nargs='?', default='background|color|border')
    ap.add_argument('--wait', type=int, default=800)
    a = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel='chrome', headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'],
        )
        page = browser.new_page(viewport={'width': 1400, 'height': 960})
        page.goto(a.url, timeout=60000)
        page.wait_for_timeout(a.wait)
        result = page.evaluate(JS, {'sel': a.selector, 'propRe': a.prop})
        print(json.dumps(result, ensure_ascii=False, indent=1))
        browser.close()


if __name__ == '__main__':
    main()
