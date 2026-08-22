# Gemini Browser Client v0.2.1 环境验收补充任务包 V1.3

版本：V0.2.1-V1.3

## 一、阶段定位

当前状态：

v0.2.1 Runtime ↓ 100轮稳定性验证通过 ↓ 环境能力验证 ↓ 版本冻结 ↓
v0.3多Worker

已完成： - GUI运行验证 - 100轮连续任务 - 成功率100% -
Parser/Validator验证100% - 资源监控修复

本阶段不修改核心Runtime。

------------------------------------------------------------------------

# 二、剩余目标

完成：

1.  Headless运行验证
2.  Browser异常恢复验证
3.  服务器远程观察验证

------------------------------------------------------------------------

# 三、Headless模式验证

目标：

确认服务器长期运行模式。

执行：

``` bash
python benchmark_runner.py --rounds 10 --headless
```

记录：

-   成功率
-   平均耗时
-   内存
-   CPU
-   浏览器进程数量

生成：

resource_compare_report.json

包含GUI与Headless资源对比。

------------------------------------------------------------------------

# 四、Recovery测试

## A 页面关闭

流程：

任务执行 →关闭Gemini页面 →检测异常 →恢复Browser →继续执行

记录： - 是否恢复 - 恢复时间 - 最终状态

## B 浏览器进程关闭

流程：

执行任务 →结束Chrome进程 →Browser Recovery →恢复Profile →继续任务

验证： - Cookie保持 - Session恢复

## C 网络异常

流程：

执行任务 →网络中断 →Retry →恢复网络 →继续执行

记录： - Retry次数 - 错误 - 最终结果

保存：

data/results/recovery_test_report.json

------------------------------------------------------------------------

# 五、服务器远程观察验证

目标：

证明服务器运行时：

服务器Browser →远程连接 →看到真实页面 →人工可以操作

方案：

-   VNC
-   noVNC
-   远程桌面

保存：

server_validation_report.md

包含： - 系统环境 - 浏览器模式 - 资源占用 - 远程方案 - 操作体验

------------------------------------------------------------------------

# 六、最终结果提交

data/results/

必须包含：

benchmark_report.json

resource_compare_report.json

recovery_test_report.json

server_validation_report.md

validation_summary.md

------------------------------------------------------------------------

# 七、禁止修改

禁止：

-   多Worker
-   ChatGPT Worker
-   Claude Worker
-   Scheduler
-   智能规划
-   架构重构

------------------------------------------------------------------------

# 八、冻结标准

满足：

100轮稳定运行 + Headless通过 + Recovery通过 + 服务器远程观察通过

则：

Gemini Browser Client v0.2.1正式冻结。

下一阶段：

v0.3 Worker Runtime Framework。
