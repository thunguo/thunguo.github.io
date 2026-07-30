"""主编排：加载 sources.json → 采集 → 去重 → 按类目分组 → 落 digest/YYYY-MM-DD.json。

P0 不接 LLM：category 直接采用信源在 sources.json 里声明的 category_hints，
P1 再由 classify.py 用 DeepSeek 复核打标、analyze.py 生成分析。

用法：
    python -m pipeline.run                 # 跑今天
    python -m pipeline.run --date 2026-07-30
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from .dedupe import dedupe
from .model import CATEGORIES, Item, now_iso, today_str
from .collectors import api as api_c
from .collectors import hackathon as hk_c
from .collectors import rss as rss_c
from .collectors import scrape as scrape_c

ROOT = Path(__file__).resolve().parent.parent

# source_id → 采集函数。新增信源 = sources.json 加配置 + 这里注册一个函数
COLLECTORS = {
    "hn_algolia": lambda cfg: api_c.hn_algolia(cfg),
    "github_search": lambda cfg: api_c.github_search(cfg),
    "product_hunt": lambda cfg: api_c.product_hunt(cfg),
    "36kr": lambda cfg: rss_c.collect("36kr", cfg),
    "yingke": lambda cfg: rss_c.collect("yingke", cfg),
    "huggingface": lambda cfg: rss_c.collect("huggingface", cfg),
    "qbitai": lambda cfg: scrape_c.qbitai(cfg),
    "devpost": lambda cfg: scrape_c.devpost(cfg),
    "dorahacks": lambda cfg: hk_c.dorahacks(cfg),
    "waytoagi_events": lambda cfg: hk_c.waytoagi(cfg),
    "competehub": lambda cfg: hk_c.competehub(cfg),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD，默认今天（Asia/Shanghai）")
    args = ap.parse_args()
    date = args.date or today_str()

    sources = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    enabled = [s for s in sources["sources"] if s.get("enabled")]

    items: list[Item] = []
    degraded: list[dict] = []
    for src in enabled:
        fn = COLLECTORS.get(src["id"])
        if fn is None:
            degraded.append({"id": src["id"], "reason": "no collector registered"})
            continue
        try:
            got = fn(src)
            items.extend(got)
            print(f"[ok] {src['id']}: {len(got)} items", file=sys.stderr)
        except Exception as e:  # 单源失败不阻塞整体
            degraded.append({"id": src["id"], "reason": f"{type(e).__name__}: {e}"})
            print(f"[degraded] {src['id']}: {e}", file=sys.stderr)
            traceback.print_exc(limit=1)

    merged = dedupe(items)

    # P1：DeepSeek 分类清洗（无 key 时跳过，退化为 P0 行为）
    from . import analyze, classify
    if classify.available():
        before = len(merged)
        merged = classify.classify(merged)
        print(f"[classify] {before} → {len(merged)}", file=sys.stderr)
    else:
        print("[classify] 未配置 DEEPSEEK_API_KEY，跳过（P0 模式）", file=sys.stderr)

    # 精选标记：黑客松类目已人工信源筛选过，全量进精选；
    # 资讯类按 LLM 高分 / 多源交叉验证 / 高社区热度，三者居其一
    HK_CATS = {"hackathon_online", "hackathon_offline_cn"}

    def is_featured(e: dict) -> bool:
        if set(e["categories"]) & HK_CATS:
            return True
        if e.get("score", 0) >= 4:
            return True
        if len(e["sources"]) >= 2:
            return True
        ex = e.get("extra", {})
        return bool((ex.get("points") or 0) >= 50
                    or (ex.get("votes") or 0) >= 30
                    or (ex.get("stars") or 0) >= 300)

    by_cat: dict[str, list] = {k: [] for k in CATEGORIES}
    for e in merged:
        e["featured"] = is_featured(e)
        for c in e["categories"]:
            if c in by_cat:
                by_cat[c].append(e)
    n_feat = sum(1 for e in merged if e["featured"])
    print(f"[featured] {n_feat}/{len(merged)}", file=sys.stderr)

    analysis = analyze.analyze(by_cat)

    digest = {
        "date": date,
        "generated_at": now_iso(),
        "stats": {"raw_items": len(items), "after_dedupe": len(merged)},
        "degraded_sources": degraded,
        "categories": [
            {"key": k, "label": CATEGORIES[k], "items": v} for k, v in by_cat.items()
        ],
        # P1 由 analyze.py 填充；无 key 时为 None，前端显示占位
        "analysis": analysis,
    }

    out = ROOT / "digest" / f"{date}.json"
    out.write_text(json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8")

    # 维护 History 用的日期索引
    dates = sorted(p.stem for p in (ROOT / "digest").glob("????-??-??.json"))
    (ROOT / "digest" / "index.json").write_text(
        json.dumps({"dates": dates}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"done: {out} (raw={len(items)}, merged={len(merged)}, degraded={len(degraded)})",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
