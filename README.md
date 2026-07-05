# NGA Summary

[本项目完全由vibe coding 生成]

NGA Summary 用于定时浏览 NGA 指定板块，抓取热帖标题和高回复帖子内容，并通过 LLM 生成每日论坛热点与近期讨论动向的 Markdown 摘要。

当前规划来自 [agent.md](agent.md)，目标板块包括：

- 网事杂谈
- 手机 网页游戏综合讨论

## 配置

仓库只提交公开模板 [config.example.toml](config.example.toml)。真实 cookie 和 LLM API 信息必须写入本地配置文件，并由 `.gitignore` 屏蔽。

初始化本地配置：

```bash
cp config.example.toml config.local.toml
```

然后编辑 `config.local.toml`：

- `nga.cookie`：从已登录 NGA 的浏览器请求中复制完整 `Cookie` 请求头值。
- `nga.cookie` 必须是合法 TOML 字符串。推荐写成单行：`cookie = "ngaPassportUid=...; ngaPassportCid=..."`
- 如果 cookie 太长，也可以使用三引号多行字符串：`cookie = """..."""`。
- `nga.headers`：抓取请求使用的额外 HTTP headers，默认包含 `Connection = "close"` 和 `User-Agent = "Nga_Official/80023"`。
- `nga.target_forums`：填写或修正目标板块的 NGA `fid`。
- `llm.provider`：填写使用的 LLM 服务类型。
- `llm.base_url`：OpenAI 兼容接口地址。
- `llm.api_key`：LLM API key。
- `llm.model`：用于总结的模型名。
- `summary.daily_run_time`：每日自动总结时间。
- `summary.output_dir`：Markdown 摘要输出目录。
- `crawler.max_content_threads_per_forum`：每个板块抓取正文内容的热帖数量。

不要提交 `config.local.toml`、`config.toml`、`.env` 或任何包含 cookie/API key 的文件。

## 安装

Python 版本建议使用 3.10 或更高。Python 3.10 需要安装 `tomli` 来读取 TOML 配置：

```bash
python3 -m pip install -r requirements.txt
```

## 使用

检查配置是否完整：

```bash
python3 -m nga_summary check-config
```

手动抓取并生成一次 LLM 摘要：

```bash
python3 -m nga_summary run
```

只抓取并输出原始 Markdown 摘要，不调用 LLM：

```bash
python3 -m nga_summary run --no-llm
```

每天按 `config.local.toml` 中的 `summary.daily_run_time` 自动运行：

```bash
python3 -m nga_summary schedule
```

可选参数：

- `--config PATH`：指定配置文件路径。
- `--pages-per-forum N`：每个目标板块扫描的页数，默认 `1`。

生成的 Markdown 默认写入 `summaries/`，该目录不会进入版本控制。

## 预期工作流

后续实现代码时建议按以下顺序读取配置：

1. 优先读取 `config.local.toml`，用于本地开发和运行。
2. 如不存在，再读取 `config.toml`，用于部署环境的显式配置。
3. 保留 `config.example.toml` 仅作为字段说明和默认值参考。

程序应支持两种触发方式：

- 定时任务：每天在配置的固定时间生成一次摘要。
- 手动触发：用户主动运行命令后立即抓取并总结。

生成结果建议写入 `summaries/`，本地缓存和浏览记录建议写入 `.cache/nga_summary/` 或 `data/`。这些目录默认不进入版本控制。

## 隐私与安全

- NGA cookie 等同于登录凭据，泄露后可能导致账号风险。
- LLM API key 可能产生费用，必须只保存在本地私密配置中。
- 日志中不要打印完整 cookie、API key 或原始请求头。
- 提交代码前先检查 `git status`，确认没有隐私配置被加入版本控制。

## 远端仓库

计划远端仓库：

```text
https://github.com/kahuuchino/nga_summary.git
```
