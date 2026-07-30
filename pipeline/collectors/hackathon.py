"""黑客松信源采集器：DoraHacks(开放API) / WayToAGI / CompeteHub。

设计原则：采集层只做候选抓取 + 尽力而为的字段提取，
结构化（线上/线下判定、地点、报名链接清洗）交给 P1 的 classify.py LLM 步骤。
"""
from __future__ import annotations

import re
from datetime import datetime

import httpx
from selectolax.parser import HTMLParser

from ..model import Item, CN_TZ

UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")}

AI_KW = ("ai", "agent", "llm", "gpt", "大模型", "智能体", "aigc", "人工智能")
HK_KW = ("黑客松", "hackathon", "大赛", "挑战赛", "buildathon", "竞赛")
CN_PLACES = ("北京", "上海", "深圳", "广州", "杭州", "成都", "武汉", "南京", "苏州",
             "西安", "长沙", "重庆", "合肥", "厦门", "珠海", "香港", "澳门", "台湾",
             "beijing", "shanghai", "shenzhen", "hangzhou", "china")


def _has_any(text: str, kws) -> bool:
    t = text.lower()
    return any(k in t for k in kws)


def dorahacks(cfg: dict) -> list[Item]:
    """官方开放 API。status=1 进行中；Virtual→线上；In-person 且地点涉中国→线下CN。"""
    r = httpx.get("https://dorahacks.io/api/hackathon/",
                  params={"format": "json", "page_size": 50}, headers=UA, timeout=30)
    r.raise_for_status()
    now_ts = datetime.now(CN_TZ).timestamp()
    items = []
    for h in r.json().get("results", []):
        if h.get("status") != 1 or (h.get("end_time") or 0) < now_ts:
            continue
        title = (h.get("title") or "").strip()
        desc = re.sub(r"<[^>]+>", "", h.get("description") or "")
        if not (_has_any(title + " " + desc, AI_KW) or _has_any(title, HK_KW)):
            continue
        form = (h.get("participation_form") or "Virtual")
        venue = " ".join(filter(None, [h.get("venue_name"), h.get("venue_address")]))
        online = form.lower() == "virtual"
        cat = "hackathon_online" if online else "hackathon_offline_cn"
        if not online and not _has_any(venue + title, CN_PLACES):
            continue  # 海外线下不收录
        start = datetime.fromtimestamp(h["start_time"], CN_TZ).strftime("%Y-%m-%d") if h.get("start_time") else ""
        end = datetime.fromtimestamp(h["end_time"], CN_TZ).strftime("%Y-%m-%d") if h.get("end_time") else ""
        uname = h.get("uname") or ""
        items.append(Item(
            title=title,
            url=f"https://dorahacks.io/hackathon/{uname}/detail" if uname else "https://dorahacks.io/hackathon",
            summary=f"{start} ~ {end} · {'线上' if online else venue} · {desc[:200]}",
            source_id="dorahacks", source_name="DoraHacks",
            published_at=datetime.now(CN_TZ).isoformat(timespec="seconds"),
            category_hints=[cat],
            extra={"start": start, "end": end, "form": form, "venue": venue,
                   "register_url": h.get("register_form_url") or ""},
        ))
    return items


def waytoagi(cfg: dict) -> list[Item]:
    """活动列表页服务端渲染。卡片文本模式：开始日期 ~ 结束日期 + 标题 + 简介 + 查看活动详情。"""
    r = httpx.get("https://www.waytoagi.com/zh/events", headers=UA, timeout=30)
    r.raise_for_status()
    tree = HTMLParser(r.text)
    today = datetime.now(CN_TZ).date()
    items, seen = [], set()
    for a in tree.css("a[href]"):
        href = a.attributes.get("href", "")
        m = re.match(r"^/events/(\d+)$", href)
        if not m or m.group(1) in seen:
            continue
        card = a
        for _ in range(4):
            if card.parent is not None:
                card = card.parent
        text = " ".join((card.text() or "").split())
        dm = re.match(r"(?:(\d{4}-\d{2}-\d{2}))?\s*~\s*(?:(\d{4}-\d{2}-\d{2}))?(.*?)查看活动详情", text)
        if not dm:
            continue
        body = dm.group(3).strip()
        if not _has_any(body, HK_KW) and not _has_any(body, AI_KW):
            continue
        end = dm.group(2)
        if end:
            try:
                if datetime.strptime(end, "%Y-%m-%d").date() < today:
                    continue  # 已结束
            except ValueError:
                pass
        seen.add(m.group(1))
        online = "线上" in text
        offline = "线下" in text
        cat = ("hackathon_online" if online else "hackathon_offline_cn") if (online or offline) \
            else ("hackathon_offline_cn" if _has_any(body, CN_PLACES) else "hackathon_online")
        items.append(Item(
            title=body[:80], url=f"https://www.waytoagi.com{href}",
            summary=text[:300],
            source_id="waytoagi_events", source_name="WayToAGI",
            published_at=(dm.group(1) or "") + "T00:00:00+08:00" if dm.group(1) else "",
            category_hints=[cat],
            extra={"start": dm.group(1) or "", "end": end or "",
                   "format_hint": "线上" if online else ("线下" if offline else "unknown")},
        ))
    return items


def competehub(cfg: dict) -> list[Item]:
    """首页竞赛卡片：/zh/competitions/{slug}，文本含 标题/标签/地点/奖金/截止。"""
    r = httpx.get("https://www.competehub.dev/zh", headers=UA, timeout=30)
    r.raise_for_status()
    tree = HTMLParser(r.text)
    items, seen = [], set()
    for a in tree.css("a[href]"):
        href = a.attributes.get("href", "")
        if not href.startswith("/zh/competitions/") or href in seen:
            continue
        seen.add(href)
        text = " ".join((a.text() or "").split())
        if not _has_any(text, AI_KW):
            continue
        online = "线上" in text
        items.append(Item(
            title=text[:80],
            url=f"https://www.competehub.dev{href}",
            summary=text[:300],
            source_id="competehub", source_name="AI赛事通",
            published_at=datetime.now(CN_TZ).isoformat(timespec="seconds"),
            category_hints=["hackathon_online" if online else "hackathon_offline_cn"],
            extra={"format_hint": "线上" if online else "线下/待确认"},
        ))
    return items
