"""DeepSeek 批量分类与清洗（P1）。

做什么：
1. 过滤无关条目（36氪/Readhub 是泛科技 feed，会混入火箭发射、银团贷款等）
2. 复核/重打 5 个类目（采集器的 category_hints 只是信源级别的粗标）
3. 黑客松条目抽取结构化字段：时间 / 线上或线下 / 地点 / 报名链接
4. 融资条目抽取：轮次 / 金额 / 投资方

没配置 DEEPSEEK_API_KEY 时整个步骤跳过，管道退化为 P0 行为。
"""
from __future__ import annotations

import json
import os

import httpx

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
CHUNK = 40

PROMPT = """你是信息分类器。下面是一批科技资讯条目（JSON数组，字段 uid/title/summary/source）。
对每条判断：
0. score：重要性评分 1-5。5=行业级大事（大厂Agent产品发布、重大融资、重磅政策）；4=权威机构/头部VC的重要观点、高关注度新产品；3=值得一看的新产品/新赛事；2=相关但增量信息少；1=擦边。
1. relevant：是否与「AI应用 / AI Agent / 大模型产品 / AI创业 / AI投融资 / AI黑客松」**直接**相关。标准从严：泛AI基建、芯片、航天、传统制造、股市公告、纯硬件、与Agent无关的模型跑分新闻都标 false。
2. categories：从以下选 0~2 个（relevant=false 时给空数组）：
   - startup_project：AI Agent创业项目、创业融资新闻
   - investment_direction：投资机构观点、赛道分析、VC看好的方向
   - new_product：新发布的AI应用/Agent产品/模型
   - hackathon_online：线上黑客松/竞赛（任何地区，线上即可）
   - hackathon_offline_cn：仅中国大陆（含港澳）的线下黑客松/竞赛。
     注意：海外线下赛事（如印度、美国、欧洲的线下活动）不属于用户需求，直接标 relevant=false。
3. 若为黑客松，填 hackathon 字段：{start,end,format(线上/线下),location,register_url}，从title/summary提取，没有给空字符串。
4. 若为融资新闻，填 funding 字段：{round,amount,investor}。

5. clean_title：清洗后的标题。有些来源标题粘着标签/奖金/团队数/地点等杂讯（如"黑客松创业26机器学习/AI物联网5 团队KothamangalamDEVFOLIO"），
   提取出赛事或产品本体名称即可（如"黑客松创业26"）；原标题干净时原样返回。

只输出JSON：{"results":[{"uid":"...","score":4,"relevant":true,"categories":["new_product"],"clean_title":"...","hackathon":null,"funding":null}, ...]}
"""

def available() -> bool:
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


def _chat(prompt: str, payload: str, temperature: float = 0.0) -> dict:
    r = httpx.post(
        API_URL,
        headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
                 "Content-Type": "application/json"},
        json={"model": MODEL, "temperature": temperature,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": prompt},
                           {"role": "user", "content": payload}]},
        timeout=120,
    )
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


def classify(merged: list[dict]) -> list[dict]:
    """就地过滤 + 重打类目，返回保留的条目。"""
    kept: list[dict] = []
    for i in range(0, len(merged), CHUNK):
        chunk = merged[i:i + CHUNK]
        payload = json.dumps(
            [{"uid": e["uid"], "title": e["title"], "summary": e["summary"][:200],
              "source": e["sources"][0]["name"]} for e in chunk],
            ensure_ascii=False)
        try:
            res = _chat(PROMPT, payload)
            verdict = {v["uid"]: v for v in res.get("results", [])}
        except Exception as e:
            print(f"[classify] chunk {i} 失败，本批保留原样: {e}")
            kept.extend(chunk)
            continue
        for e in chunk:
            v = verdict.get(e["uid"])
            if v is None:
                kept.append(e)
                continue
            if not v.get("relevant"):
                continue
            e["score"] = int(v.get("score") or 0)
            ct = (v.get("clean_title") or "").strip()
            if ct and ct != e["title"]:
                e["title"] = ct
            cats = [c for c in v.get("categories", []) if c in
                    ("startup_project", "investment_direction", "new_product",
                     "hackathon_online", "hackathon_offline_cn")]
            if cats:
                e["categories"] = cats
            if v.get("hackathon"):
                e["extra"]["hackathon"] = v["hackathon"]
            if v.get("funding"):
                e["extra"]["funding"] = v["funding"]
            kept.append(e)
    return kept
