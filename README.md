# Gemini Browser Client v0.2 (AI Worker Runtime)

Gemini Browser Client v0.2 是面向长期稳定运行的 AI Worker Runtime 执行系统。
在 v0.1 单次执行脚本的基础上，v0.2 增强了运行时稳定性、常驻浏览器管理、异常自动恢复、SQLite 任务状态持久化、以及可扩展的 Worker 接口抽象。

---

## 1. v0.2 升级特性

- **Browser Manager (常驻运行时管理)**: 支持浏览器进程常驻与上下文复用，避免多任务之间重复拉起与关闭浏览器。
- **SQLite State Store (状态持久化)**: 内置 `StateStore` (`data/state.db`)，完整记录任务生命周期（`CREATED`, `RUNNING`, `SUCCESS`, `FAILED`, `RETRYING`, `CANCELLED`）。
- **Crash Recovery (异常自动恢复)**: 遇到页面崩溃或上下文断开时，系统自动重启 BrowserManager 并重新加载会话，无需人工干预。
- **Worker 接口抽象 (BaseWorker / GeminiWorker)**: 统一 Web AI Worker 交互协议，方便未来水平接入 ChatGPT Worker、Claude Worker 或本地模型。
- **Selector Adapter (选择器独立适配器)**: 采用 `selectors/gemini.yaml` 集中管理选择器配置，严格遵循 `aria` > `role` > `placeholder` > `text` > `css` 优先级。
- **日志可追踪性增强**: 记录 `execution_id`, `worker_id`, `browser_id`, `retry_count`, `duration`, `model` 等细粒度追踪字段。

---

## 2. 系统目录结构

```text
C:\code\
├── main.py                     # CLI 与常驻 Runtime 入口
├── controller.py               # 控制器、状态机流转与自愈逻辑
├── browser.py                  # BrowserManager (Playwright 常驻上下文管理与自愈)
├── worker.py                   # BaseWorker 抽象基类与 GeminiWorker 实现
├── gemini.py                   # 兼容层与模块重导出
├── store.py                    # SQLite 状态存储管理 (StateStore)
├── task.py                     # Task 与 Result 数据模型
├── parser.py                   # Markdown/JSON 提取与解析
├── validator.py                # 字段与模式校验器
├── config.py                   # 配置加载器
├── logger.py                   # 结构化 JSON 追踪日志记录
├── requirements.txt            # 项目依赖
├── config.yaml                 # 配置文件
├── config.yaml.example         # 配置示例文件
├── test_unit.py                # 自动化测试用例
├── README.md                   # 工程使用与说明文档
├── selectors/
│   └── gemini.yaml             # Gemini 页面元素选择器适配配置
└── data/
    ├── profile/                # Chromium 持久化用户目录 (保持登录状态)
    ├── logs/                   # 结构化运行日志目录 (app.log)
    ├── screenshots/            # 异常与错误截图目录
    ├── results/                # 任务执行结果输出目录
    ├── state.db                # SQLite 任务状态持久化数据库
    └── test_cases/             # 测试任务定义 (task_001_mvp.json)
```

---

## 3. 环境准备与依赖安装

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## 4. 运行与操作说明

### 4.1 首次人工登录
启动浏览器完成首次 Google/Gemini 账号登录（会话将自动保存在 `./data/profile`）：
```bash
python main.py
```

### 4.2 连续执行任务 (常驻 Browser 模式)
```bash
python main.py --task-id "task_002" --goal "总结Python特性" --prompt "请列出Python的三大核心特性并给出简评。" --expected-output '{"features": [], "summary": ""}'
```

### 4.3 查询任务状态
通过 SQLite 状态持久层查询任务历史与当前状态：
```bash
# 查询指定任务详情
python main.py --query-task "task_002"

# 查看最近执行任务列表
python main.py --list-tasks
```

---

## 5. 测试验收

执行测试套件：
```bash
python test_unit.py
```
