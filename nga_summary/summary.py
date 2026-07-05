from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import AppConfig
from .llm import summarize_with_llm
from .models import ThreadContent, ThreadItem
from .nga import NgaClient, choose_threads_for_content


@dataclass(frozen=True)
class SummaryResult:
    output_path: Path
    fetched_threads: int
    fetched_thread_contents: int
    used_llm: bool


def generate_summary(config: AppConfig, pages_per_forum: int = 1, use_llm: bool = True) -> SummaryResult:
    client = NgaClient(config)
    threads_by_forum: dict[str, list[ThreadItem]] = {}
    contents: list[ThreadContent] = []

    for forum in config.nga.target_forums:
        print(f"Fetching forum: {forum.name}", flush=True)
        threads = client.fetch_forum_threads(forum, pages=pages_per_forum)
        threads_by_forum[forum.name] = threads

        selected = choose_threads_for_content(threads, config.crawler.max_content_threads_per_forum)
        for item in selected:
            print(f"Fetching thread: [{item.forum_name}] {item.title[:60]}", flush=True)
            try:
                contents.append(client.fetch_thread_content(item))
            except RuntimeError as exc:
                print(f"Warning: skipped thread {item.tid}: {exc}", flush=True)
            client._sleep()

    source = build_source_digest(config, threads_by_forum, contents)
    if use_llm:
        prompt = build_llm_prompt(config, source)
        body = summarize_with_llm(config.llm, prompt)
    else:
        body = source

    output_path = write_summary(config, body)
    return SummaryResult(
        output_path=output_path,
        fetched_threads=sum(len(items) for items in threads_by_forum.values()),
        fetched_thread_contents=len(contents),
        used_llm=use_llm,
    )


def build_llm_prompt(config: AppConfig, source_digest: str) -> str:
    now = datetime.now(ZoneInfo(config.summary.timezone))
    return f"""请根据下面抓取到的 NGA 帖子列表与部分帖子内容，生成一份中文 Markdown 摘要。

当前时间：{now.strftime('%Y-%m-%d %H:%M:%S %Z')}

要求：
- 直接输出 Markdown 正文，不要寒暄、不要说明“好的”。
- 总结今日或最近的论坛热点，按重要性排序。
- 给出近几日讨论动向；如果抓取内容不足以判断，请明确写出样本限制。
- 每个热点尽量附带相关帖子链接。
- 提炼主要争议点、核心论点和情绪走向。
- 不要泄露 cookie、API key 或任何配置内容。

抓取内容：

{source_digest}
"""


def build_source_digest(
    config: AppConfig,
    threads_by_forum: dict[str, list[ThreadItem]],
    contents: list[ThreadContent],
    max_chars: int = 60000,
) -> str:
    lines: list[str] = ["# NGA 抓取样本", ""]
    for forum_name, threads in threads_by_forum.items():
        lines.extend([f"## {forum_name} 帖子列表", ""])
        for item in threads:
            reply = f"，回复数约 {item.reply_count}" if item.reply_count else ""
            lines.append(f"- [{item.title}]({item.url}){reply}")
        lines.append("")

    grouped: dict[str, list[ThreadContent]] = defaultdict(list)
    for content in contents:
        grouped[content.item.forum_name].append(content)

    for forum_name, forum_contents in grouped.items():
        lines.extend([f"## {forum_name} 高回复帖内容摘录", ""])
        for content in forum_contents:
            item = content.item
            reply = f" / 回复数约 {item.reply_count}" if item.reply_count else ""
            lines.extend([f"### [{item.title}]({item.url}){reply}", ""])
            for index, post in enumerate(content.posts[: config.crawler.max_posts_per_thread], start=1):
                snippet = post[:1200]
                lines.extend([f"楼层 {index}：", snippet, ""])

    digest = "\n".join(lines).strip() + "\n"
    if len(digest) <= max_chars:
        return digest
    return digest[:max_chars] + "\n\n[内容因长度限制已截断]\n"


def write_summary(config: AppConfig, body: str) -> Path:
    output_dir = config.summary.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(ZoneInfo(config.summary.timezone))
    output_path = output_dir / f"{now.strftime('%Y-%m-%d_%H%M')}_nga_summary.md"
    output_path.write_text(body.rstrip() + "\n", encoding="utf-8")
    return output_path
