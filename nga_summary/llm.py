from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import LlmConfig


def summarize_with_llm(config: LlmConfig, prompt: str) -> str:
    endpoint = chat_completions_endpoint(config.base_url)
    payload = {
        "model": config.model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个中文论坛热点分析助手。只基于用户提供的抓取内容总结，"
                    "不要编造未出现的事实。输出结构清晰的 Markdown。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"LLM request failed with HTTP {exc.code}: {error_body}") from exc
    except URLError as exc:
        raise RuntimeError("LLM request failed") from exc

    data = json.loads(raw)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("LLM response did not match OpenAI-compatible chat format") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM returned an empty summary")
    return content.strip()


def chat_completions_endpoint(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    if base_url.endswith("/v1"):
        return f"{base_url}/chat/completions"
    return f"{base_url}/v1/chat/completions"
