from __future__ import annotations

import html
import re
import time
from html.parser import HTMLParser
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from .config import AppConfig, ForumConfig
from .models import ThreadContent, ThreadItem


THREAD_LINK_RE = re.compile(
    r"<a\b(?P<attrs>[^>]*\bhref=[\"'][^\"']*read\.php\?[^\"']*tid=\d+[^\"']*[\"'][^>]*)>"
    r"(?P<title>.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
HREF_RE = re.compile(r"href=[\"'](?P<href>[^\"']+)[\"']", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
TITLE_RE = re.compile(r"<title[^>]*>(?P<title>.*?)</title>", re.IGNORECASE | re.DOTALL)


class NgaClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self.base_url = config.nga.base_url

    def fetch_forum_threads(self, forum: ForumConfig, pages: int = 1) -> list[ThreadItem]:
        seen: set[str] = set()
        threads: list[ThreadItem] = []
        for page in range(1, max(1, pages) + 1):
            url = self._forum_url(forum.fid, page)
            body = self._get_text(url)
            for item in parse_thread_list(body, self.base_url, forum):
                if item.tid in seen:
                    continue
                seen.add(item.tid)
                threads.append(item)
                if len(threads) >= self.config.crawler.max_threads_per_forum:
                    break
            if len(threads) >= self.config.crawler.max_threads_per_forum:
                break
            self._sleep()
        return threads

    def fetch_thread_content(self, item: ThreadItem) -> ThreadContent:
        body = self._get_text(item.url)
        posts = extract_posts(body)
        if self.config.crawler.max_posts_per_thread > 0:
            posts = posts[: self.config.crawler.max_posts_per_thread]
        return ThreadContent(item=item, page_title=extract_title(body), posts=posts)

    def _forum_url(self, fid: str, page: int) -> str:
        query = {"fid": fid}
        if page > 1:
            query["page"] = str(page)
        return f"{self.base_url}/thread.php?{urlencode(query)}"

    def _get_text(self, url: str) -> str:
        headers = {
            "Connection": "close",
            "User-Agent": "Nga_Official/80023",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
            "Cookie": self.config.nga.cookie,
            "Referer": self.base_url + "/",
        }
        headers.update(self.config.nga.headers)
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=self.config.crawler.request_timeout_seconds) as response:
                raw = response.read()
                charset = response.headers.get_content_charset()
        except HTTPError as exc:
            raise RuntimeError(f"NGA request failed with HTTP {exc.code}: {url}") from exc
        except URLError as exc:
            raise RuntimeError(f"NGA request failed: {url}") from exc

        return decode_response(raw, charset)

    def _sleep(self) -> None:
        interval = self.config.crawler.request_interval_seconds
        if interval > 0:
            time.sleep(interval)


def parse_thread_list(body: str, base_url: str, forum: ForumConfig) -> list[ThreadItem]:
    reply_counts = _parse_reply_counts_by_tid(body)
    threads: list[ThreadItem] = []
    for match in THREAD_LINK_RE.finditer(body):
        attrs = match.group("attrs")
        if _is_non_topic_link(attrs):
            continue
        href_match = HREF_RE.search(match.group("attrs"))
        if not href_match:
            continue
        href = html.unescape(href_match.group("href"))
        if "page=e" in href:
            continue
        tid = extract_tid(href)
        if not tid:
            continue

        title = clean_html_text(match.group("title"))
        if not _looks_like_thread_title(title):
            continue

        start = max(0, match.start() - 500)
        end = min(len(body), match.end() + 700)
        reply_count = reply_counts.get(tid, parse_reply_count(body[start:end]))
        threads.append(
            ThreadItem(
                forum_name=forum.name,
                fid=forum.fid,
                tid=tid,
                title=title,
                url=urljoin(base_url + "/", href),
                reply_count=reply_count,
            )
        )
    return threads


def _parse_reply_counts_by_tid(body: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in THREAD_LINK_RE.finditer(body):
        attrs = match.group("attrs")
        if not _is_reply_count_link(attrs):
            continue
        href_match = HREF_RE.search(attrs)
        if not href_match:
            continue
        tid = extract_tid(html.unescape(href_match.group("href")))
        text = clean_html_text(match.group("title"))
        if tid and text.isdigit():
            counts[tid] = int(text)
    return counts


def choose_threads_for_content(threads: Iterable[ThreadItem], limit: int) -> list[ThreadItem]:
    items = list(threads)
    if any(item.reply_count > 0 for item in items):
        items.sort(key=lambda item: item.reply_count, reverse=True)
    return items[: max(0, limit)]


def extract_tid(href: str) -> str | None:
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    tid_values = query.get("tid")
    if tid_values and tid_values[0].isdigit():
        return tid_values[0]

    match = re.search(r"(?:\?|&)tid=(\d+)", href)
    if match:
        return match.group(1)
    return None


def parse_reply_count(fragment: str) -> int:
    text = clean_html_text(fragment)
    patterns = [
        r"(?:回复|回帖|reply|replies)[^\d]{0,20}(\d{1,6})",
        r"(\d{1,6})[^\d]{0,8}(?:回复|回帖)",
        r"\breplies[\"']?\s*[:=]\s*[\"']?(\d{1,6})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 0


def extract_posts(body: str) -> list[str]:
    parser = PostContentParser()
    parser.feed(body)
    parser.close()
    posts = [normalize_text(item) for item in parser.posts if normalize_text(item)]
    if posts:
        return posts

    fallback = normalize_text(strip_scripts_and_tags(body))
    return [fallback[:8000]] if fallback else []


def extract_title(body: str) -> str:
    match = TITLE_RE.search(body)
    if not match:
        return ""
    title = clean_html_text(match.group("title"))
    return re.sub(r"\s*[-_]\s*NGA.*$", "", title).strip()


def decode_response(raw: bytes, charset: str | None) -> str:
    encodings = [charset, "utf-8", "gb18030"]
    for encoding in encodings:
        if not encoding:
            continue
        try:
            return raw.decode(encoding, errors="replace")
        except LookupError:
            continue
    return raw.decode("utf-8", errors="replace")


def clean_html_text(value: str) -> str:
    value = TAG_RE.sub(" ", value)
    value = html.unescape(value)
    return normalize_text(value)


def strip_scripts_and_tags(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    return clean_html_text(value)


def normalize_text(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\r", "\n")
    value = re.sub(r"[ \t\f\v]+", " ", value)
    value = re.sub(r"\n\s*\n\s*\n+", "\n\n", value)
    return value.strip()


def _looks_like_thread_title(title: str) -> bool:
    if not title:
        return False
    lowered = title.lower()
    ignored = {"上一页", "下一页", "末页", "首页", "回复", "收藏", "只看楼主"}
    return title not in ignored and not lowered.startswith("javascript") and not title.isdigit()


def _is_non_topic_link(attrs: str) -> bool:
    lowered = attrs.lower()
    ignored_tokens = [
        "class='replies'",
        'class="replies"',
        "class='silver replydate'",
        'class="silver replydate"',
        "replydate",
        "id='t_rc",
        'id="t_rc',
        "id='t_rt",
        'id="t_rt',
    ]
    return any(token in lowered for token in ignored_tokens)


def _is_reply_count_link(attrs: str) -> bool:
    lowered = attrs.lower()
    return (
        "class='replies'" in lowered
        or 'class="replies"' in lowered
        or "id='t_rc" in lowered
        or 'id="t_rc' in lowered
    )


class PostContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._current: list[str] = []
        self.posts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        attr_blob = " ".join(attr_map.values()).lower()
        starts_post = (
            attr_map.get("id", "").lower().startswith("postcontent")
            or "postcontent" in attr_blob
            or "post_content" in attr_blob
        )
        if starts_post and self._depth == 0:
            self._current = []
            self._depth = 1
            return
        if self._depth > 0:
            self._depth += 1
            if tag in {"br", "p", "div", "li"}:
                self._current.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._depth <= 0:
            return
        if tag in {"p", "div", "li"}:
            self._current.append("\n")
        self._depth -= 1
        if self._depth == 0:
            text = normalize_text("".join(self._current))
            if text:
                self.posts.append(text)
            self._current = []

    def handle_data(self, data: str) -> None:
        if self._depth > 0:
            self._current.append(data)
