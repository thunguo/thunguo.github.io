"""静态页 scrape 采集器：量子位 / Devpost。httpx + selectolax。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import httpx
from selectolax.parser import HTMLParser

from ..model import Item, CN_TZ

UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")}


def qbitai(cfg: dict) -> list[Item]:
    """首页文章链接 URL 自带 /YYYY/MM/ 日期，过滤近2天。"""
    r = httpx.get("https://www.qbitai.com/", headers=UA, timeout=30, follow_redirects=True)
    r.raise_for_status()
    tree = HTMLParser(r.text)
    cutoff = datetime.now(CN_TZ) - timedelta(days=2)
    items, seen = [], set()
    for a in tree.css("a[href]"):
        href = a.attributes.get("href", "")
        m = re.search(r"qbitai\.com/(\d{4})/(\d{2})/\d+\.html", href)
        if not m:
            continue
        # URL 只有年月精度，按 (year, month) 比较
        if (int(m.group(1)), int(m.group(2))) < (cutoff.year, cutoff.month):
            continue
        dt = datetime(int(m.group(1)), int(m.group(2)), 1, tzinfo=CN_TZ)
        title = (a.text() or "").strip()
        if len(title) < 8 or href in seen:
            continue
        seen.add(href)
        items.append(Item(
            title=title, url=href,
            source_id="qbitai", source_name="量子位",
            published_at=dt.isoformat(timespec="seconds"),
            category_hints=cfg.get("categories", []),
        ))
    return items


def _devpost_direct(cfg: dict) -> list[Item]:
    r = httpx.get("https://devpost.com/hackathons",
                  params={"themes[]": "Artificial Intelligence"},
                  headers=UA, timeout=30)
    r.raise_for_status()
    tree = HTMLParser(r.text)
    items = []
    for tile in tree.css("a.tile-anchor"):
        href = tile.attributes.get("href", "")
        title_el = tile.css_first("h3") or tile.css_first(".software-entry-name")
        title = (title_el.text() if title_el else "").strip()
        if not title or not href:
            continue
        desc_el = tile.css_first(".challenge-description") or tile.css_first("p")
        items.append(Item(
            title=title, url=href,
            summary=(desc_el.text().strip()[:300] if desc_el else ""),
            source_id="devpost", source_name="Devpost",
            published_at=datetime.now(CN_TZ).isoformat(timespec="seconds"),
            category_hints=cfg.get("categories", []),
        ))
    return items


def _devpost_via_jina(cfg: dict) -> list[Item]:
    """直连被 Cloudflare 拦（常见于数据中心 IP）时，走 Jina Reader 代理取 markdown 再解析链接。"""
    r = httpx.get("https://r.jina.ai/https://devpost.com/hackathons?themes[]=Artificial+Intelligence",
                  headers={"User-Agent": "curl/8.0"}, timeout=60)
    r.raise_for_status()
    items, seen = [], set()
    # Jina 输出为 markdown，条目形如 [标题](https://xxx.devpost.com/?ref_feature=...) 或 /hackathons/xxx
    for m in re.finditer(r"\[([^\[\]]{8,120}?)\]\((https?://[^)\s]+)\)", r.text):
        title, url = m.group(1).strip(), m.group(2)
        if "devpost.com" not in url or "/hackathons" in url and url.rstrip("/").endswith("hackathons"):
            pass
        if url in seen or "software" in url or "rules" in url:
            continue
        seen.add(url)
        items.append(Item(
            title=title, url=url,
            source_id="devpost", source_name="Devpost",
            published_at=datetime.now(CN_TZ).isoformat(timespec="seconds"),
            category_hints=cfg.get("categories", []),
        ))
    return items[:40]


def devpost(cfg: dict) -> list[Item]:
    """AI 主题黑客松列表页。直连优先，被反爬时降级走 Jina Reader 代理。"""
    try:
        items = _devpost_direct(cfg)
        if items:
            return items
    except Exception as e:
        print(f"[devpost] 直连失败({type(e).__name__})，尝试 Jina 代理")
    items = _devpost_via_jina(cfg)
    if not items:
        raise RuntimeError("devpost: 直连与 Jina 代理均未取到条目")
    return items
