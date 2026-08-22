import time
from browser import BrowserManager
from config import load_config


def main():
    config = load_config()
    print("=" * 60)
    print("正在启动 Chromium 浏览器，请在弹出的窗口中登录 Google/Gemini 账号...")
    print("=" * 60)

    bm = BrowserManager(profile_path=config.browser.profile_path, headless=False, timeout=180)
    started, err = bm.start()
    if not started:
        print(f"启动浏览器失败: {err}")
        return

    bm.open_page(config.gemini.url)
    print("Gemini 页面已加载，请在浏览器中完成登录。正在监听登录状态...")

    max_wait = 300  # 最多等待 5 分钟
    start_time = time.time()

    while (time.time() - start_time) < max_wait:
        time.sleep(3)
        logged_in, msg = bm.check_login()
        if logged_in:
            print("\n" + "=" * 60)
            print(f"【登录成功】检测到 Gemini 输入框已就绪！")
            print(f"会话与 Cookie 已持久化保存至 {config.browser.profile_path}")
            print("=" * 60)
            time.sleep(3)
            break
        print(".", end="", flush=True)
    else:
        print("\n等待登录超时。")

    bm.close()
    print("浏览器已保存并退出。")


if __name__ == "__main__":
    main()
