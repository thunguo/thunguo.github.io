"""去重：URL 精确去重 + RapidFuzz 标题相似度合并（多源转载合并，保留全部来源）。"""
from __future__ import annotations

from rapidfuzz import fuzz

from .model import Item

TITLE_THRESHOLD = 85


def _norm_url(url: str) -> str:
    u = url.strip().lower()
    for p in ("https://", "http://"):
        if u.startswith(p):
            u = u[len(p):]
            break
    return u.rstrip("/").split("?")[0].split("#")[0]


def dedupe(items: list[Item]) -> list[dict]:
    """返回合并后的条目列表（dict），同一新闻多源报道合并为一条，sources 记录所有来源。"""
    merged: list[dict] = []
    seen_url: dict[str, dict] = {}

    for it in items:
        key = _norm_url(it.url)
        hit = seen_url.get(key)
        if hit is None:
            # 标题模糊匹配
            for m in merged:
                if fuzz.token_set_ratio(it.title, m["title"]) >= TITLE_THRESHOLD:
                    hit = m
                    break
        if hit is not None:
            if it.source_name not in [s["name"] for s in hit["sources"]]:
                hit["sources"].append({"id": it.source_id, "name": it.source_name, "url": it.url})
            # 保留信息更丰富的字段
            if len(it.summary) > len(hit["summary"]):
                hit["summary"] = it.summary
            for c in it.category_hints:
                if c not in hit["categories"]:
                    hit["categories"].append(c)
            continue
        entry = {
            "title": it.title,
            "url": it.url,
            "summary": it.summary,
            "published_at": it.published_at,
            "categories": list(dict.fromkeys(it.category_hints)),
            "sources": [{"id": it.source_id, "name": it.source_name, "url": it.url}],
            "extra": it.extra,
            "uid": it.uid,
        }
        merged.append(entry)
        seen_url[key] = entry

    merged.sort(key=lambda e: e["published_at"], reverse=True)
    return merged
