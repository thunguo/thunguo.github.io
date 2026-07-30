"""RSS 类采集器：36氪 / Readhub / HuggingFace。feedparser 统一解析，按发布时间过滤近48h。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import feedparser

from ..http_util import get_with_retry
from ..model import Item, CN_TZ

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

FEEDS = {
    "36kr": ("https://36kr.com/feed", "36氪"),
    "yingke": ("https://readhub.cn/rss", "Readhub"),   # 实测 /feed 返回HTML壳，/rss 才是真feed
    "huggingface": ("https://huggingface.co/feed", "Hugging Face"),
}

WINDOW_HOURS = 48
TAG_RE = re.compile(r"<[^>]+>")


def _to_dt(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=CN_TZ)
    return None


def collect(feed_id: str, cfg: dict) -> list[Item]:
    url, name = FEEDS[feed_id]
    resp = get_with_retry(url, retries=2, timeout=45,
                          headers={"User-Agent": UA}, follow_redirects=True)
    feed = feedparser.parse(resp.content)
    cutoff = datetime.now(CN_TZ) - timedelta(hours=WINDOW_HOURS)
    items: list[Item] = []
    for e in feed.entries:
        dt = _to_dt(e)
        if dt and dt < cutoff:
            continue
        summary = TAG_RE.sub("", getattr(e, "summary", "") or "").strip()[:500]
        items.append(Item(
            title=(e.get("title") or "").strip(),
            url=e.get("link", ""),
            summary=summary,
            source_id=feed_id, source_name=name,
            published_at=dt.isoformat(timespec="seconds") if dt else "",
            category_hints=cfg.get("categories", []),
        ))
    return [i for i in items if i.title and i.url]
