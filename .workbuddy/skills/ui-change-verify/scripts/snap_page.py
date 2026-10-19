#!/usr/bin/env python3
"""截图脚本：playwright 驱动系统 Chrome（headless，无需下载浏览器）。

用法:
  snap_page.py <url> <输出.png> [--width 1400] [--height 960] [--wait 1200] [--js "<JS>"] [--clip x,y,w,h]

示例:
  snap_page.py http://127.0.0.1:8899/test_mm_redesign.html /tmp/after.png
  snap_page.py http://127.0.0.1:8085/ /tmp/app.png --wait 3000
  snap_page.py http://127.0.0.1:8899/test.html /tmp/el.png --clip 55,25,1280,900

注意:
  - 必须加 --no-sandbox（本环境 Chrome CLI headless 会沙箱报错/卡死，不要直接用 Chrome CLI）。
  - 诊断样式规则时 url 必须是 http(s)，file:// 下 cssRules 被安全策略拦截。
"""
import argparse
from playwright.sync_api import sync_playwright


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('url')
    ap.add_argument('out')
    ap.add_argument('--width', type=int, default=1400)
    ap.add_argument('--height', type=int, default=960)
    ap.add_argument('--wait', type=int, default=1200, help='加载后等待 ms（等 JS 渲染）')
    ap.add_argument('--js', default='', help='截图前在页面执行的 JS，结果打印到 stdout')
    ap.add_argument('--clip', default='', help='裁剪区域 x,y,w,h')
    a = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel='chrome', headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'],
        )
        page = browser.new_page(viewport={'width': a.width, 'height': a.height})
        page.goto(a.url, timeout=60000)
        page.wait_for_timeout(a.wait)
        if a.js:
            print(page.evaluate(a.js))
        kw = {}
        if a.clip:
            x, y, w, h = map(int, a.clip.split(','))
            kw['clip'] = {'x': x, 'y': y, 'width': w, 'height': h}
        page.screenshot(path=a.out, **kw)
        browser.close()
    print('saved', a.out)


if __name__ == '__main__':
    main()
