import os
import time
from playwright.sync_api import sync_playwright
from config import load_config


def main():
    config = load_config()
    profile_path = os.path.abspath(config.browser.profile_path)
    os.makedirs(profile_path, exist_ok=True)

    print("=" * 70)
    print("【人工登录与会话保持模式】")
    print(f"用户数据目录: {profile_path}")
    print("浏览器窗口即将保持打开，请在窗口中正常完成 Google / Gemini 账号登录。")
    print("【注意】：只要不手动关闭该浏览器窗口，它会一直保持打开等待你操作。")
    print("当你完成登录并能看到 Gemini 聊天界面后，直接手动关闭该浏览器窗口即可自动保存会话！")
    print("=" * 70)

    p = sync_playwright().start()
    try:
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
        )
    except Exception:
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
        )

    page = context.pages[0] if context.pages else context.new_page()
    page.goto(config.gemini.url)

    # 循环监控：只要浏览器窗口未被关闭，就一直保持运行
    try:
        while not page.is_closed() and context.pages:
            time.sleep(1)
    except Exception:
        pass
    finally:
        try:
            context.close()
        except Exception:
            pass
        try:
            p.stop()
        except Exception:
            pass

    print("\n" + "=" * 70)
    print("【完成】检测到浏览器窗口已关闭，登录 Session 与 Cookie 已成功持久化写入本地目录！")
    print("=" * 70)


if __name__ == "__main__":
    main()
