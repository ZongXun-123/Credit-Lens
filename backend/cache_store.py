# cache_store.py — 成功結果快取(Demo 保命符)
#
# 解決的問題:EAP 平台回應不穩(逾時、JSON 格式跑掉、Token 過期),
# 現場 Demo 不能賭。策略:平時反覆測試,每次「成功」的結果自動落地存檔;
# Demo 當天開啟重播模式,直接讀存好的結果——秒回、必成功、內容與當時實測完全一致。
#
# 三種模式(以 .env 之 CACHE_MODE 控制):
#   off     不使用快取,每次都真打 EAP(開發初期釐清問題時用)
#   record  真打 EAP,成功才寫入快取(預設,平時測試就在累積素材)
#   replay  優先讀快取;快取沒有才真打 EAP,成功後一樣寫入(Demo 當天用)
#
# 儲存體為單一 SQLite 檔 data/credit_lens.db,零安裝、可直接複製給組員。
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

DB = Path(__file__).parent / "data" / "credit_lens.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,      -- finance / tech / judge / pre_brief / extract / score / market_read / universe
    company_id  TEXT NOT NULL,      -- 證券代號優先,無則統編或名稱
    company_name TEXT DEFAULT '',
    req_key     TEXT NOT NULL,      -- 同一 kind 下辨識輸入的鍵(如面談判定的題號)
    payload     TEXT NOT NULL,      -- 成功的回應 JSON
    pinned      INTEGER DEFAULT 0,  -- 1 = 釘選,Demo 指定使用這一筆
    note        TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lookup ON results(kind, company_id, req_key, pinned, id);
"""


def _conn() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    return c


def save(kind: str, company_id: str, payload: dict, company_name: str = "", req_key: str = "") -> int:
    """存一筆成功結果,回傳紀錄 id(失敗回 0)。任何例外都吞掉——快取失敗絕不能拖垮主流程。"""
    try:
        with _conn() as c:
            cur = c.execute(
                "INSERT INTO results(kind,company_id,company_name,req_key,payload,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (kind, str(company_id), company_name, req_key,
                 json.dumps(payload, ensure_ascii=False),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            return int(cur.lastrowid or 0)
    except Exception as e:
        print(f"⚠️ [快取] 寫入失敗({type(e).__name__}: {e}),不影響本次回應")
        return 0


def load(kind: str, company_id: str, req_key: str = "") -> Optional[dict]:
    """取最適合的一筆:釘選優先,其次最新。查無回 None。"""
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT payload FROM results WHERE kind=? AND company_id=? AND req_key=? "
                "ORDER BY pinned DESC, id DESC LIMIT 1",
                (kind, str(company_id), req_key),
            ).fetchone()
        return json.loads(row["payload"]) if row else None
    except Exception as e:
        print(f"⚠️ [快取] 讀取失敗({type(e).__name__}: {e}),改為即時呼叫")
        return None


def load_meta(kind: str, company_id: str, req_key: str = "") -> Optional[dict]:
    """同 load,但連同紀錄中繼資料一起回傳:{id, created_at, pinned, payload}。"""
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT id, created_at, pinned, payload FROM results "
                "WHERE kind=? AND company_id=? AND req_key=? "
                "ORDER BY pinned DESC, id DESC LIMIT 1",
                (kind, str(company_id), req_key),
            ).fetchone()
        if not row:
            return None
        return {"id": row["id"], "created_at": row["created_at"], "pinned": bool(row["pinned"]),
                "payload": json.loads(row["payload"])}
    except Exception:
        return None


def get(result_id: int) -> Optional[dict]:
    """依 id 取單筆完整紀錄(歷次紀錄面板「載入」用)。"""
    try:
        with _conn() as c:
            row = c.execute("SELECT * FROM results WHERE id=?", (int(result_id),)).fetchone()
        if not row:
            return None
        return {"id": row["id"], "kind": row["kind"], "company_id": row["company_id"],
                "company_name": row["company_name"], "req_key": row["req_key"],
                "pinned": bool(row["pinned"]), "created_at": row["created_at"],
                "payload": json.loads(row["payload"])}
    except Exception:
        return None


def stats() -> dict:
    """快取盤點:哪些公司、哪些功能已經有成功結果(Demo 前檢查用)。"""
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT kind, company_id, company_name, COUNT(*) n, "
                "MAX(created_at) latest, MAX(pinned) pinned "
                "FROM results GROUP BY kind, company_id ORDER BY company_id, kind"
            ).fetchall()
            total = c.execute("SELECT COUNT(*) n FROM results").fetchone()["n"]
        return {"total": total, "items": [dict(r) for r in rows]}
    except Exception as e:
        return {"total": 0, "items": [], "error": f"{type(e).__name__}: {e}"}


def coverage() -> dict:
    """以公司為主軸的覆蓋率:每家公司集滿哪些功能(Demo 前一眼看出缺口)。"""
    KINDS = ["finance", "tech", "judge", "pre_brief", "extract", "score", "market_read"]
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT DISTINCT kind, company_id, company_name FROM results"
            ).fetchall()
    except Exception:
        return {"companies": [], "kinds": KINDS}

    by_company: dict = {}
    for r in rows:
        cid = r["company_id"]
        entry = by_company.setdefault(cid, {"company_id": cid, "company_name": r["company_name"], "kinds": []})
        if r["company_name"] and not entry["company_name"]:
            entry["company_name"] = r["company_name"]
        entry["kinds"].append(r["kind"])
    out = []
    for e in by_company.values():
        have = [k for k in KINDS if k in e["kinds"]]
        out.append({**e, "kinds": have, "have": len(have), "need": len(KINDS),
                    "ready": len(have) >= 4})   # 集滿四項即可完整走一次 Demo 流程
    out.sort(key=lambda x: (-x["have"], x["company_id"]))
    return {"companies": out, "kinds": KINDS}


def pin(kind: str, company_id: str, result_id: int) -> bool:
    """釘選指定紀錄:Demo 時該功能固定使用這一筆(挑出表現最好的那次)。"""
    try:
        with _conn() as c:
            c.execute("UPDATE results SET pinned=0 WHERE kind=? AND company_id=?", (kind, str(company_id)))
            cur = c.execute("UPDATE results SET pinned=1 WHERE id=?", (result_id,))
        return cur.rowcount > 0
    except Exception:
        return False


def latest_all(kind: str) -> list:
    """取每家公司在某功能下的最新一筆完整 payload(釘選優先)。
    供報告中心彙總使用,例如把所有 extract 的承諾事項攤平成追蹤清單。"""
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT r.company_id, r.company_name, r.payload, r.created_at FROM results r "
                "JOIN (SELECT company_id, MAX(pinned) mp, MAX(id) mi FROM results WHERE kind=? "
                "      GROUP BY company_id) t ON r.company_id = t.company_id "
                "WHERE r.kind=? AND r.id = (SELECT id FROM results WHERE kind=? AND company_id=r.company_id "
                "                           ORDER BY pinned DESC, id DESC LIMIT 1)",
                (kind, kind, kind),
            ).fetchall()
        out = []
        for r in rows:
            try:
                out.append({"company_id": r["company_id"], "company_name": r["company_name"],
                            "created_at": r["created_at"], "payload": json.loads(r["payload"])})
            except json.JSONDecodeError:
                continue
        return out
    except Exception:
        return []


def listing(kind: str = "", company_id: str = "", limit: int = 50) -> list:
    """列出紀錄(供挑選釘選對象)。payload 只回前 200 字預覽。"""
    sql = "SELECT id,kind,company_id,company_name,req_key,pinned,created_at,substr(payload,1,200) preview FROM results"
    where, args = [], []
    if kind:
        where.append("kind=?"); args.append(kind)
    if company_id:
        where.append("company_id=?"); args.append(str(company_id))
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    try:
        with _conn() as c:
            rows = [dict(r) for r in c.execute(sql.replace("substr(payload,1,200) preview", "payload"), args).fetchall()]
        out = []
        for r in rows:
            raw = r.pop("payload", "")
            r["preview"] = raw[:200]
            try:
                pl = json.loads(raw)
                r["score"] = pl.get("final_score", pl.get("score", pl.get("market_score")))
            except json.JSONDecodeError:
                r["score"] = None
            out.append(r)
        return out
    except Exception:
        return []


# 判定「查無資料」的字樣:模型在知識庫沒有該公司時會這樣描述
_NO_DATA = ("查無", "無法評估", "無法進行", "無法評價", "無相關資料", "未涵蓋", "沒有查到")


def _is_no_data(payload: dict) -> bool:
    fs = payload.get("findings") or []
    if not fs:
        return True
    return all(any(k in (f.get("text", "") + f.get("cite", "")) for k in _NO_DATA) for f in fs)


def readiness() -> dict:
    """回傳每家公司的素材完整度,供案件總覽排序使用。

    等級定義(數字越大越前面):
      3 = 財務與技術皆有實質內容,且裁決、拜訪前情資齊備   → 可完整展示
      2 = 技術有實質內容且裁決齊備,但財務為知識庫查無      → 可展示,財務顯示資料不足
      1 = 有部分素材                                      → 需補跑
      0 = 完全沒有素材
    """
    out = {}
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT r.kind, r.company_id, r.payload FROM results r "
                "WHERE r.id = (SELECT id FROM results WHERE kind=r.kind AND company_id=r.company_id "
                "              ORDER BY pinned DESC, id DESC LIMIT 1)"
            ).fetchall()
    except Exception:
        return out

    agg: dict = {}
    for r in rows:
        try:
            p = json.loads(r["payload"])
        except json.JSONDecodeError:
            continue
        e = agg.setdefault(r["company_id"], {})
        if r["kind"] in ("finance", "tech"):
            e[r["kind"]] = "none" if _is_no_data(p) else "real"
        else:
            e[r["kind"]] = "have"

    for cid, e in agg.items():
        core = e.get("judge") and e.get("pre_brief")
        if e.get("finance") == "real" and e.get("tech") == "real" and core:
            lv = 3
        elif e.get("tech") == "real" and core:
            lv = 2
        elif e:
            lv = 1
        else:
            lv = 0
        out[cid] = {"level": lv, "kinds": sorted(e.keys()),
                    "finance": e.get("finance", ""), "tech": e.get("tech", "")}
    return out