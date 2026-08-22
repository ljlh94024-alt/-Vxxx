import time
from playwright.sync_api import sync_playwright
from config import load_config


def main():
    config = load_config()
    print("=" * 60)
    print("【人工登录窗口】正在启动带有可视化界面的浏览器...")
    print("请在打开的浏览器窗口中登录你的 Google / Gemini 账号。")
    print("登录完成后，请在终端按 Enter 回车键保存并关闭。")
    print("=" * 60)

    p = sync_playwright().start()
    context = p.chromium.launch_persistent_context(
        user_data_dir=config.browser.profile_path,
        headless=False,
        channel="chrome",
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 900},
    )

    page = context.pages[0] if context.pages else context.new_page()
    page.goto(config.gemini.url)

    input("\n>>> 请在浏览器窗口中完成账号登录。登录成功后回到此终端按下【回车键 Enter】继续: ")

    print("\n正在保存会话并写入 Profile 目录...")
    time.sleep(2)
    context.close()
    p.stop()
    print("Profile 保存完成！现在可以进行自动化任务执行。")


if __name__ == "__main__":
    main()
