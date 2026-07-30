"""API 类采集器：HN Algolia / GitHub Search / Product Hunt GraphQL。"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import httpx

from ..model import Item, CN_TZ

UA = "agent-daily/0.1 (+https://github.com/)"


def hn_algolia(cfg: dict) -> list[Item]:
    """HN Algolia search_by_date：近24h AI agent 相关 story，点数>2 过滤噪音。"""
    since = int((datetime.now(CN_TZ) - timedelta(hours=24)).timestamp())
    items: list[Item] = []
    for query in ("AI agent", "LLM agent"):
        r = httpx.get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={"query": query, "tags": "story", "numericFilters": f"created_at_i>{since}"},
            headers={"User-Agent": UA}, timeout=30,
        )
        r.raise_for_status()
        for h in r.json().get("hits", []):
            if (h.get("points") or 0) < 2 or not h.get("url"):
                continue
            items.append(Item(
                title=h["title"], url=h["url"],
                summary=f"HN {h.get('points', 0)} points / {h.get('num_comments', 0)} comments",
                source_id="hn_algolia", source_name="Hacker News",
                published_at=datetime.fromtimestamp(h["created_at_i"], CN_TZ).isoformat(timespec="seconds"),
                category_hints=cfg.get("categories", []),
                extra={"hn_id": h.get("objectID"), "points": h.get("points"), "comments": h.get("num_comments")},
            ))
    return items


def github_search(cfg: dict) -> list[Item]:
    """近3天新建、star>=10 的 agent 相关 repo。窗口放宽到3天避免单日空窗。"""
    since = (datetime.now(CN_TZ) - timedelta(days=3)).strftime("%Y-%m-%d")
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if tok := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {tok}"
    r = httpx.get(
        "https://api.github.com/search/repositories",
        params={"q": f"(agent OR agents) (AI OR LLM) in:name,description,readme created:>{since} stars:>=10",
                "sort": "stars", "order": "desc", "per_page": 30},
        headers=headers, timeout=30,
    )
    r.raise_for_status()
    items = []
    for repo in r.json().get("items", []):
        items.append(Item(
            title=f"{repo['full_name']} — {repo.get('description') or ''}".strip(" —"),
            url=repo["html_url"],
            summary=(repo.get("description") or "")[:300],
            source_id="github_search", source_name="GitHub",
            published_at=repo["created_at"],
            category_hints=cfg.get("categories", []),
            extra={"stars": repo["stargazers_count"], "language": repo.get("language")},
        ))
    return items


def _ph_token() -> str:
    r = httpx.post(
        "https://api.producthunt.com/v2/oauth/token",
        json={"client_id": os.environ["PH_CLIENT_ID"],
              "client_secret": os.environ["PH_CLIENT_SECRET"],
              "grant_type": "client_credentials"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def product_hunt(cfg: dict) -> list[Item]:
    """近48h 的 posts，本地按 AI/agent 关键词过滤。"""
    token = _ph_token()
    since = (datetime.now(CN_TZ) - timedelta(hours=48)).isoformat()
    query = """
    query($after: DateTime!) {
      posts(order: VOTES, postedAfter: $after, first: 50) {
        nodes { name tagline url votesCount createdAt topics { nodes { name } } }
      }
    }"""
    r = httpx.post(
        "https://api.producthunt.com/v2/api/graphql",
        json={"query": query, "variables": {"after": since}},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    kw = ("agent", "ai", "llm", "gpt", "claude", "automation", "copilot", "assistant")
    items = []
    for p in r.json()["data"]["posts"]["nodes"]:
        text = (p["name"] + " " + (p.get("tagline") or "") + " "
                + " ".join(t["name"] for t in p["topics"]["nodes"])).lower()
        if not any(k in text for k in kw):
            continue
        items.append(Item(
            title=f"{p['name']} — {p.get('tagline') or ''}",
            url=p["url"], summary=p.get("tagline") or "",
            source_id="product_hunt", source_name="Product Hunt",
            published_at=p["createdAt"],
            category_hints=cfg.get("categories", []),
            extra={"votes": p["votesCount"],
                   "topics": [t["name"] for t in p["topics"]["nodes"]]},
        ))
    return items
