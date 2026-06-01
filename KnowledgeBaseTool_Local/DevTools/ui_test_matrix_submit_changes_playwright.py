import sys


def main():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print("Playwright 未安装，跳过 UI 自动化用例。")
        print("安装方式: pip install playwright && playwright install")
        print("导入错误:", e)
        return 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://127.0.0.1:8080", wait_until="domcontentloaded")

        page.fill("#username", "admin")
        page.fill("#password", "123456")
        page.click("#loginBtn")
        page.wait_for_load_state("domcontentloaded")

        page.click("#tab-matrixView")
        page.wait_for_timeout(500)

        dialog_message = {"text": None}

        def on_dialog(d):
            dialog_message["text"] = d.message
            d.accept()

        page.once("dialog", on_dialog)
        page.click("#matrixSubmitChangesBtn")
        page.wait_for_timeout(300)

        assert dialog_message["text"] is not None, "预期弹出校验失败提示对话框"
        assert "没有可提交的修改" in dialog_message["text"], dialog_message["text"]

        browser.close()

    print("UI 自动化用例通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
