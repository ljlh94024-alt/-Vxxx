# Gemini Browser Client v0.2.1-V1.1 实机验证与验收指南（验证冻结版）

Gemini Browser Client v0.2.1-V1.1 是进入 v0.3 多Worker架构前经过真实环境稳定性验证的冻结版本。
本版本旨在证明**单网页AI执行节点具备长期稳定运行、会话持久保持、自动异常恢复、可追踪复盘及人工随时可接管的能力**。

---

## 1. 验证目标与验收清单

| 验收维度 | 验证项 | 验收标准 | 验证工具/方式 |
| :--- | :--- | :--- | :--- |
| **功能闭环** | 登录保持 | 首次人工登录后，后续任务无需重复登录，Cookie/Session持久化在 `./data/profile` | `python main.py` |
| **功能闭环** | 标准任务闭环 | 支持简单结构化、长文本、复杂嵌套 JSON 各类任务 | `data/test_cases/task_A~D` |
| **稳定性** | 连续多轮任务 | 连续 10 轮及 100 轮基准任务成功率 ≥ 95% | `python benchmark_runner.py` |
| **容错自愈** | 异常自动恢复 | 页面失效/浏览器进程断开自动触发热重启并恢复 Profile | `Controller.recover_runtime` |
| **可观测性** | SQLite Trace | `tasks` 记录任务状态，`executions` 记录每次尝试的 duration 与 error | `python main.py --query-executions` |
| **可运营性** | GUI 与远程观察 | 支持本地 GUI 与 Linux 远程桌面/VNC 观察执行画面与人工接管 | Chromium 窗口 / VNC |

---

## 2. 固定验证任务集 (`data/test_cases/`)

- **Task A (`task_A_simple_json.json`)**: 简单结构化输出，验证基础 JSON Parser 与 Validator。
- **Task B (`task_B_long_text.json`)**: 长文本对比分析，验证动态等待与 Response 稳定截取机制。
- **Task C (`task_C_complex_format.json`)**: 嵌套对象与列表结构，验证复杂 JSON 提取。
- **Task D (`task_D_error_recovery.json`)**: 格式校验约束，验证递进式 Prompt 重试机制。

---

## 3. 运行实机验证

### 3.1 步骤 1：首次人工登录与 Profile 保持
确保 `config.yaml` 中 `browser.headless: false`，运行：
```bash
python main.py
```
在弹出的浏览器中登录 Google/Gemini 账号。完成后关闭，再次运行验证无需重新登录。

### 3.2 步骤 2：执行单任务验证
```bash
# 验证 Task A
python main.py --task-file "data/test_cases/task_A_simple_json.json"

# 验证 Task B
python main.py --task-file "data/test_cases/task_B_long_text.json"
```

### 3.3 步骤 3：连续稳定性基准压测 (Benchmark)
```bash
# 运行 10 轮连续稳定性测试 (默认 GUI 模式)
python benchmark_runner.py --rounds 10

# 运行 Headless 模式对比测试
python benchmark_runner.py --rounds 10 --headless --output "data/results/benchmark_headless.json"
```
测试结束后将在 `data/results/benchmark_report.json` 输出汇总成功率、平均耗时与内存指标。

### 3.4 步骤 4：复盘与 Trace 历史查询
```bash
# 查看任务整体状态
python main.py --query-task "task_mock_retry"

# 查询单任务所有重试执行过程（包含各尝试耗时与错误记录）
python main.py --query-executions "task_mock_retry"
```

---

## 4. 远程观察与服务器部署建议

在 Linux 服务器（作为 Worker 节点）上部署时：
- 推荐使用 `Xvfb` + `x11vnc` / `noVNC` 暴露 Web 界面，以便远程观察浏览器实际渲染与执行过程。
- 发生异常或需要人工重新登录时，运维人员可通过 VNC 远程接管页面。

---

## 5. 单元与流程测试

```bash
python test_unit.py
```
