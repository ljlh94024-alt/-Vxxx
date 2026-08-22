# Gemini Browser Client v0.1

Gemini Browser Client 是一个由单一 Controller 控制的网页 AI 客户端执行系统。
本系统将 Gemini 视为网页 AI 执行端，由 Playwright 管理 Chromium 自动化运行时，实现从任务派发、Prompt 发送、页面状态监听、回复提取、JSON 解析到结果校验的完整执行闭环。

---

## 1. 核心架构与边界

- **单一决策核心 (Controller)**: Controller 是唯一的流程决策者，管理有限状态机与重试流程。
- **网页 AI 端 (Gemini)**: 仅作为网页执行终端，不依赖外部 Agent 框架或复杂多智能体协作。
- **自动化运行时 (Browser/Playwright)**: 使用持久化 BrowserContext (`launch_persistent_context`) 保持用户 Google 登录会话与 Cookie。
- **登录策略**: 严格禁止自动输入账号密码。首次运行由人工在浏览器中完成登录，会话持久化存储在 `./data/profile` 中。后续运行自动加载该会话。若未登录则返回 `login_required`。
- **元素选择器优先级**: `aria-label` > `role` > `placeholder` > `text` > CSS 选择器（严禁依赖易变的随机混淆 class）。

---

## 2. 目录结构

```text
C:\code\
├── main.py                     # CLI 主入口
├── controller.py               # 控制器状态机与流程编排
├── browser.py                  # Playwright 浏览器持久化上下文管理
├── gemini.py                   # Gemini 网页交互与选择器逻辑
├── task.py                     # Task 与 Result 数据模型
├── parser.py                   # Markdown/JSON 提取与解析
├── validator.py                # 字段与模式校验器
├── config.py                   # 配置加载器
├── logger.py                   # 结构化 JSON 日志记录
├── requirements.txt            # 项目依赖
├── config.yaml                 # 配置文件
├── config.yaml.example         # 配置示例文件
├── test_unit.py                # 单元测试用例
├── README.md                   # 工程使用与说明文档
└── data/
    ├── profile/                # Chromium 持久化用户目录
    ├── logs/                   # 运行日志输出目录 (app.log)
    ├── screenshots/            # 异常与错误截图保存目录
    ├── results/                # 任务执行结果输出目录
    └── test_cases/             # 测试任务定义 (task_001_mvp.json)
```

---

## 3. 环境准备与安装

### 3.1 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3.2 配置文件说明 (`config.yaml`)

```yaml
browser:
  profile_path: "./data/profile"    # 浏览器持久化目录路径
  headless: false                   # 是否无头模式 (首次登录建议设为 false)
  timeout: 60                       # 浏览器操作超时时间 (秒)

gemini:
  url: "https://gemini.google.com"  # Gemini 访问地址

task:
  timeout: 300                      # 单个任务最大等待时间 (秒)

retry:
  max_retry: 3                      # 最大重试次数 (默认3次递进重试)
```

---

## 4. 首次登录与使用说明

### 4.1 首次人工登录

首次启动时，建议确保 `config.yaml` 中 `browser.headless: false`。
运行任意任务打开浏览器：
```bash
python main.py
```
在弹出的 Chromium 浏览器中完成 Google/Gemini 账号的人工登录。登录成功后，用户数据与登录凭据将保存在 `./data/profile` 中。后续运行无需再次登录。

### 4.2 运行任务

#### 方式 1: 直接指定参数
```bash
python main.py --task-id "task_001" --goal "总结Python特性" --prompt "请列出Python的三大核心特性并给出简评。" --expected-output '{"features": [], "summary": ""}'
```

#### 方式 2: 通过 Task JSON 文件运行
```bash
python main.py --task-file "./data/test_cases/task_001_mvp.json"
```

---

## 5. 状态机与重试机制

Controller 状态流转如下：
`INIT` -> `BROWSER_STARTING` -> `BROWSER_READY` -> `OPEN_PAGE` -> `CHECK_LOGIN` -> `READY` -> `SEND_PROMPT` -> `WAIT_RESPONSE` -> `READ_RESPONSE` -> `PARSING` -> `VALIDATING` -> `SUCCESS` / `FAILED`

**递进式重试策略**:
1. **第 1 次尝试**: 标准发送任务目标与结构要求；
2. **第 2 次尝试**: 附带上一次校验失败的具体原因并提示纠正；
3. **第 3 次尝试**: 强制严格纯 JSON 约束。
若发生未捕获异常或超时，系统会自动捕获全屏截图至 `./data/screenshots/` 并记录结构化日志。

---

## 6. 测试与验证

运行单元测试：
```bash
python test_unit.py
```
