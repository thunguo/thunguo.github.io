"""DeepSeek 当日分析（P1）：产品分析 + 黑客松风向标。输出 markdown 字符串。"""
from __future__ import annotations

import json
import os

import httpx

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

PRODUCT_PROMPT = """你是科技记者，写今日AI产品观察。下面是今天收集到的新产品/创业项目资讯（标题+简介）。
输出两部分（中文，markdown）：
## 今日值得注意的产品
挑 3~6 个最有意思的，每个一段：先讲事实（谁做的、做什么、给谁用），再讲你的判断（它解决了什么真实问题、和已有做法差在哪），判断要有依据，不许空泛。
## 可以借鉴的做法
3~5 条，每条先说具体做法，再说为什么成立，不超过两句话。
写作要求（严格遵守）：
- 禁止"它赌的是""它砍掉了""产品思维""产品哲学"这类句式
- 禁止破折号引出解释、禁止三段式排比
- 避免"赋能""闭环""抓手""生态"等词；形容词能删就删
只输出markdown正文。"""

BRIEF_PROMPT = """你是科技媒体主编，写今日导读。下面是今天筛选后的AI情报（标题+简介）。
输出 4~6 条 markdown 无序列表，按重要性排序，每条一条事实，带具体名字（公司/产品/人物/金额）。
写作要求：
- 每条句式不要雷同；不要每条都以"标志着""凸显""预示"收尾
- 只说发生了什么和为什么重要，不引申行业趋势大词
- 只输出列表本身。"""

HACKATHON_PROMPT = """你是赛事编辑。下面是今天收集到的AI黑客松/竞赛信息（标题+简介）。
输出（中文，markdown）：
## 主办方在关注什么
把赛事归成 3~5 个方向，每个方向一段：先下结论，再自然地带出有哪些赛事（把赛事名写进句子里，不要用"对应赛事："这种罗列格式）。
## 选题建议
2~3 条，每条先说做什么，再说为什么现在做合适，控制在两句话内。
写作要求：像编辑写给读者看的稿子，不要公文腔；避免"聚焦""赋能""赛道""闭环"这类词。
只输出markdown正文。输入没有有效赛事时只输出"今日暂无足够黑客松信息"。"""


def _chat_md(prompt: str, payload: str) -> str:
    r = httpx.post(
        API_URL,
        headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
                 "Content-Type": "application/json"},
        json={"model": MODEL, "temperature": 0.7,
              "messages": [{"role": "system", "content": prompt},
                           {"role": "user", "content": payload}]},
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _brief(e: dict) -> dict:
    return {"title": e["title"], "summary": e["summary"][:200],
            "source": e["sources"][0]["name"], "extra": e.get("extra", {})}


def analyze(by_cat: dict[str, list[dict]]) -> dict:
    """返回 {"daily_brief": md|None, "product_insights": md|None, "hackathon_trends": md|None}"""
    out = {"daily_brief": None, "product_insights": None, "hackathon_trends": None}
    if not os.environ.get("DEEPSEEK_API_KEY"):
        return out

    all_items = [e for lst in by_cat.values() for e in lst]
    top = sorted(all_items, key=lambda e: e.get("score", 0), reverse=True)[:50]
    if top:
        try:
            out["daily_brief"] = _chat_md(
                BRIEF_PROMPT, json.dumps([_brief(e) for e in top], ensure_ascii=False))
        except Exception as e:
            print(f"[analyze] daily_brief 失败: {e}")

    products = (by_cat.get("new_product", []) + by_cat.get("startup_project", []))[:60]
    if products:
        try:
            out["product_insights"] = _chat_md(
                PRODUCT_PROMPT, json.dumps([_brief(e) for e in products], ensure_ascii=False))
        except Exception as e:
            print(f"[analyze] product_insights 失败: {e}")

    hacks = (by_cat.get("hackathon_online", []) + by_cat.get("hackathon_offline_cn", []))[:40]
    try:
        out["hackathon_trends"] = _chat_md(
            HACKATHON_PROMPT, json.dumps([_brief(e) for e in hacks], ensure_ascii=False))
    except Exception as e:
        print(f"[analyze] hackathon_trends 失败: {e}")
    return out
