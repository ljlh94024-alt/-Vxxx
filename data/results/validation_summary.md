# Gemini Browser Client V1.3 实机验证总结

验证时间：2026-08-22（Asia/Shanghai）

## 结论

核心执行、结构化提取、浏览器复用、Headless 和故障恢复均通过实机验证；服务器远程观察未通过，因此 V1.3 冻结标准尚未满足。

## 实测结果

| 项目 | 结果 |
|---|---:|
| GUI 10 轮 | 10/10 成功，0 重试，提取复核 100% |
| Headless 10 轮 | 10/10 成功，0 重试，提取复核 100% |
| GUI 平均/峰值总 RSS | 1320.51 MB / 1569.67 MB |
| Headless 平均/峰值总 RSS | 970.06 MB / 1166.99 MB |
| 100 轮连续运行 | 100/100 成功，0 重试，提取复核 100% |
| 100 轮平均/峰值总 RSS | 1866.31 MB / 2038.32 MB |
| 故障恢复 | 页面关闭、Context 关闭、Chrome 进程关闭、网络中断均恢复成功 |

## Gemini 定向出口流量

- GUI 10 轮：400 个定向请求，应用层估算出口 837,535 字节。
- Headless 10 轮：402 个定向请求，应用层估算出口 579,864 字节。
- 本次捕获的目标主机仅为 `gemini.google.com`。
- 监控报告不保存完整 URL 查询参数、请求头值、Cookie 或请求正文。
- 出口字节为应用层估算，不包含 TLS 与 HTTP/2 封装开销；响应未提供 `Content-Length`，因此不能据此计算实际入站流量。

## 页面行为与模型切换观察

- 当前发送逻辑主要使用 Playwright `fill()` 一次性写入，再固定等待 300/400 ms；回退路径为 10 ms/字符，不能认定为真人输入节奏。
- 通过只读观察器确认页面显示 Flash，并看到 Flash-Lite、Flash、Pro、Extended thinking 选项。
- 已实机完成 Flash → Pro → Flash 切换，说明网页层面能够切换模型；当前 Controller 尚未把模型选择暴露为正式任务参数。
- 从页面取得的原始回复可重新解析为与 `Result.json_result` 相同的对象；GUI 与 Headless 10 轮提取复核均为 100%。

## 安全策略

观察接口仅绑定 `127.0.0.1:9222`，不向局域网或公网开放。流量监控执行最小化采集，只保存目标域名、方法计数和字节计数。禁止记录认证 Cookie、Authorization、请求正文、完整查询参数及用户 Prompt 内容。人工登录与持久化 Session 原规则保持不变，代码不得自动输入密码。

## 尚未完成或不通过项

1. “像真人”：不通过，当前是明显自动化输入节奏。
2. 独立服务器远程观察及人工接管：未执行；当前主机未启用 RDP，也未安装/配置 VNC/noVNC。
3. 网卡级精确出口量：未实现；当前数据是安全的应用层定向估算。
4. 100 轮流量数据：100 轮运行发生在流量监控接入前，不能补写；后续运行将自动包含该字段。

## 证据文件

- `benchmark_gui_10_v1.2.json`
- `benchmark_headless_10_v1.2.json`
- `benchmark_report.json`
- `recovery_test_report.json`
- `resource_compare_report.json`
- `server_validation_report.md`
