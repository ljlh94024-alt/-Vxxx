# Gemini Browser Client v0.2.1 (AI Worker Runtime 稳定补丁版)

Gemini Browser Client v0.2.1 是面向长期驻留运行的单 AI Worker Runtime 节点系统。
在 v0.2 基础上，v0.2.1 进一步补齐了持续任务循环（Runtime Loop）、详细 Execution 历史追踪表、Worker 工厂抽象、以及完整的 Controller 核心流程 Mock 测试。

---

## 1. v0.2.1 核心升级

1. **Runtime Loop (`runtime.py`)**:
   - 提供后台持续任务接收与执行循环（`Runtime.run_loop` / `submit_task` / `enqueue_task`）。
   - 保持 BrowserWorker 常驻，连续处理多任务无缝衔接。
2. **Execution 历史系统 (`store.py`)**:
   - 在 SQLite 中新增 `executions` 表，完整追踪每次重试（`attempt`、`state`、`error`、`duration`）。
   - 支持多层级复盘：单任务生命周期 + 每次尝试的独立执行状态。
3. **WorkerFactory (`worker_factory.py`)**:
   - 将具体模型 Worker 实例化与 Controller 解耦，统一工厂接口。
4. **Browser 健康检查与安全恢复 (`browser.py`, `controller.py`)**:
   - 新增 `health_check()` 主动感知页面活性与异常；
   - 确保恢复后 Page 状态合法再继续重试流程。
5. **Controller 核心测试全覆盖 (`test_unit.py`)**:
   - 新增成功链路与递进重试链路的 Mock 流程单元测试。

---

## 2. 目录结构

```text
C:\code\
├── main.py                     # CLI 入口（支持单任务与 --loop 常驻循环）
├── runtime.py                  # Runtime 持续任务循环调度器
├── controller.py               # 控制器、状态机与异常恢复
├── browser.py                  # BrowserManager (Playwright 常驻管理与健康检查)
├── worker_factory.py           # WorkerFactory 工厂类
├── worker.py                   # BaseWorker 基类与 GeminiWorker
├── gemini.py                   # 模块别名兼容层
├── store.py                    # SQLite 状态与 Execution 历史存储 (StateStore)
├── task.py                     # Task 与 Result 数据协议
├── parser.py                   # Markdown/JSON 提取与解析
├── validator.py                # 模式与字段校验器
├── config.py                   # 配置加载器
├── logger.py                   # 结构化 JSON 追踪日志记录
├── requirements.txt            # 项目依赖
├── config.yaml                 # 配置文件
├── config.yaml.example         # 配置示例文件
├── test_unit.py                # 完整单元与流程测试套件
├── README.md                   # 说明文档
├── selectors/
│   └── gemini.yaml             # Gemini 页面选择器映射
└── data/
    ├── profile/                # 用户登录持久化目录
    ├── logs/                   # 结构化运行日志目录 (app.log)
    ├── screenshots/            # 错误与异常截图
    ├── results/                # 结果输出目录
    ├── state.db                # SQLite 任务与执行历史数据库
    └── test_cases/             # 测试任务定义 (task_001_mvp.json)
```

---

## 3. 安装与运行

### 3.1 依赖安装
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3.2 常驻 Worker Loop 模式
```bash
python main.py --loop
```

### 3.3 运行单任务并保留浏览器
```bash
python main.py --task-id "task_003" --goal "总结Python特性" --prompt "请列出Python的三大核心特性并给出简评。" --expected-output '{"features": [], "summary": ""}'
```

### 3.4 历史记录与执行查询
```bash
# 查询任务汇总状态
python main.py --query-task "task_003"

# 查询单任务所有重试执行记录 (executions 历史)
python main.py --query-executions "task_003"

# 列出最近任务
python main.py --list-tasks
```

---

## 4. 测试与验证

```bash
python test_unit.py
```
