from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThreadItem:
    forum_name: str
    fid: str
    tid: str
    title: str
    url: str
    reply_count: int = 0


@dataclass(frozen=True)
class ThreadContent:
    item: ThreadItem
    page_title: str
    posts: list[str]
