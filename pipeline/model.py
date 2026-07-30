"""统一数据模型：所有采集器产出 Item，去重后聚合成 Digest。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from zoneinfo import ZoneInfo

CN_TZ = ZoneInfo("Asia/Shanghai")

CATEGORIES = {
    "startup_project": "AI Agent创业项目",
    "investment_direction": "投资机构看好的AI Agent方向",
    "new_product": "涌现的新AI应用/Agent产品",
    "hackathon_online": "线上AI应用/Agent黑客松",
    "hackathon_offline_cn": "线下（中国大陆）AI应用/Agent黑客松",
}


@dataclass
class Item:
    title: str
    url: str
    summary: str = ""
    source_id: str = ""
    source_name: str = ""
    published_at: str = ""          # ISO8601，尽量精确到分钟
    category_hints: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)   # stars / votes / author 等源特有字段

    @property
    def uid(self) -> str:
        return hashlib.sha1(self.url.strip().lower().encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["uid"] = self.uid
        return d


def today_str() -> str:
    return datetime.now(CN_TZ).strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")
