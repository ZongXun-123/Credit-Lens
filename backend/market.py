# market.py — 股價市場訊號模組(《Credit-Lens 股價市場訊號模組 產品說明書 v1.0》)
# 資料來源:TEJ 未調整股價 2020–2025,生技製藥 36 家;由離線計算產出 data/market_signal.json
# 本模組只做「讀取 + 組裝回應」,指標計算與評分合成已於離線階段完成(說明書 §4–5)
import json
from pathlib import Path
from typing import Optional

import opendata

DATA = Path(__file__).parent / "data" / "market_signal.json"
_db: Optional[dict] = None


def load() -> Optional[dict]:
    global _db
    if _db is None:
        if not DATA.exists():
            return None
        _db = json.loads(DATA.read_text(encoding="utf-8"))
    return _db


def available() -> bool:
    return load() is not None


def meta() -> dict:
    db = load()
    return db["meta"] if db else {}


def _find(company_id: str) -> Optional[dict]:
    db = load()
    if not db:
        return None
    cid = str(company_id if company_id is not None else "").strip()
    if cid.endswith(".0"):        # EAP 數值型代號:1711.0 → 1711
        cid = cid[:-2]
    return next((c for c in db["companies"] if c["code"] == cid), None)


# ---------- §5.5 授信解讀對應 ----------
def _recommendation(score: Optional[int]) -> str:
    if score is None:
        return "歷史交易日數不足,不予評分;建議以內部財務與信用資料為準。"
    if score >= 67:
        return "市場訊號偏正向,可作為放行方向的佐證之一;仍須以內部財務／負債資料為主要依據。"
    if score >= 45:
        return "市場訊號中性偏警戒;建議附條件,並於拜訪時針對波動與回撤成因提問。"
    return "市場訊號偏負向,屬需加強審查族群;建議提高擔保／保證條件或要求補充資金銜接方案。"


def _summary(c: dict) -> list:
    m = c.get("metrics", {})
    p = c.get("pctile", {})
    out = []

    def band(v, hi=0.67, lo=0.34):
        return "相對同業偏低" if v is None else ("相對同業偏低" if v >= hi else "相對同業偏高" if v <= lo else "與同業相當")

    if m.get("vol_full_pct") is not None:
        out.append(f"年化波動度 {m['vol_full_pct']}%,{band(p.get('vol'))},"
                   f"{'價格較穩定' if (p.get('vol') or 0) >= 0.5 else '價格波動較大'}。")
    if m.get("mdd_pct") is not None:
        out.append(f"最大回撤 {m['mdd_pct']}%,"
                   f"{'跌幅相對可控' if (p.get('mdd') or 0) >= 0.5 else '曾出現深度回撤,尾端風險需留意'}。")
    if m.get("mom_1y_pct") is not None:
        out.append(f"近一年報酬 {m['mom_1y_pct']:+.1f}%。")
    if m.get("mktcap") is not None:
        out.append(f"市值 {m['mktcap']:,} 百萬元,"
                   f"{'規模居同業前段、系統性風險較低' if (p.get('size') or 0) >= 0.5 else '規模居同業後段,抗風險能力相對弱'}。")
    return out


# ---------- §6.2 單一企業市場訊號 ----------
def signal(company_id: str, company_name: str = "") -> Optional[dict]:
    db = load()
    c = _find(company_id)
    if not db or not c:
        return None
    prices = db.get("prices", {}).get(c["code"], [])
    return {
        "company_id": c["code"],
        "company_name": c.get("name", company_name),
        "ban": opendata.resolve_ban_by_code(c["code"]),   # 統一編號(對照表未建或興櫃時為 None)
        "market_score": c.get("market_score"),
        "level": c.get("level"),
        "tier": c.get("tier"),
        "n_days": c.get("n_days", 0),
        "waterfall": c.get("waterfall", []),
        "metrics": c.get("metrics", {}),
        "pctile": c.get("pctile", {}),
        "prices_monthly": prices,
        "reading": {
            "summary": _summary(c),
            "recommendation": _recommendation(c.get("market_score")),
        },
        "meta": {"industry": db["meta"].get("industry"), "period": db["meta"].get("period"),
                 "universe": db["meta"].get("universe")},
    }


# ---------- §6.3 同業排行 ----------
def universe(industry: str = "") -> Optional[dict]:
    db = load()
    if not db:
        return None
    if industry and industry != db["meta"].get("industry"):
        return {"universe": 0, "industry": industry, "companies": []}
    rows = []
    for c in db["companies"]:
        m = c.get("metrics", {})
        rows.append({
            "company_id": c["code"], "company_name": c.get("name", ""),
            "ban": opendata.resolve_ban_by_code(c["code"]),
            "market_score": c.get("market_score"), "level": c.get("level"), "tier": c.get("tier"),
            "summary": {"vol_full_pct": m.get("vol_full_pct"), "mdd_pct": m.get("mdd_pct"),
                        "mom_1y_pct": m.get("mom_1y_pct"), "mktcap": m.get("mktcap")},
        })
    # 分數降冪,資料不足(None)沉底
    rows.sort(key=lambda r: (r["market_score"] is None, -(r["market_score"] or 0)))
    return {"universe": db["meta"].get("universe", 0), "industry": db["meta"].get("industry", ""),
            "period": db["meta"].get("period", ""), "companies": rows}
