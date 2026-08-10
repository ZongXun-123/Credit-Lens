# tfda.py — 衛福部食藥署開放資料介接(免金鑰、免申請)
# 資料集:全部藥品許可證資料集(InfoId 36),官方 JSON 匯出端點
#   https://data.fda.gov.tw/data/opendata/export/36/json
# 授權:食藥署網站資料採「政府資料開放授權條款-第1版」,可免費加值利用(須註明出處)
#
# 因原始檔很大(全台藥品許可證),採「一次下載 → 本地快取 → 以統編/公司名建索引」策略:
#   · 第一次呼叫會自動下載並建立 data/tfda_licenses.json 快取
#   · 之後直接讀快取,查詢是毫秒級
#   · Demo 前請先執行 python prefetch.py 預先下載,避免現場等待
import io
import json
import os
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Optional

import httpx

import httpx_ssl

TFDA_URL = "https://data.fda.gov.tw/data/opendata/export/36/json"
CACHE = Path(__file__).parent / "data" / "tfda_licenses.json"
_index: Optional[dict] = None

# 原始欄位名稱在不同版本可能微調,逐一嘗試(不硬編死單一欄位)
F_BAN = ["申請商統一編號", "申請廠商統一編號", "統一編號", "營利事業統一編號"]
F_COMPANY = ["申請商名稱", "申請廠商名稱", "申請商", "許可證持有商"]
F_NAME = ["中文品名", "藥品名稱", "品名"]
F_NO = ["許可證字號", "許可證號", "證號"]
F_DATE = ["發證日期", "有效日期", "發證日"]
F_TYPE = ["藥品類別", "許可證種類", "類別"]


def _pick(row: dict, keys: list) -> str:
    for k in keys:
        v = row.get(k)
        if v not in (None, "", "　"):
            return str(v).strip()
    return ""


async def download(force: bool = False) -> int:
    """下載並建立本地快取,回傳筆數。已有快取且未 force 則直接跳過。"""
    if CACHE.exists() and not force:
        return json.loads(CACHE.read_text(encoding="utf-8")).get("_count", 0)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    async with httpx_ssl.client(timeout=httpx.Timeout(180.0, connect=15.0), follow_redirects=True) as client:
        r = await client.get(TFDA_URL)
        r.raise_for_status()
        raw = r.content

    # 端點可能直接回 JSON,也可能回 ZIP,兩種都處理
    try:
        rows = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            inner = z.namelist()[0]
            rows = json.loads(z.read(inner).decode("utf-8-sig"))
    if isinstance(rows, dict):  # 少數資料集外層包一層
        rows = next((v for v in rows.values() if isinstance(v, list)), [])

    # 只保留需要的欄位,壓小快取體積
    slim = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        slim.append({
            "ban": _pick(row, F_BAN),
            "company": _pick(row, F_COMPANY),
            "name": _pick(row, F_NAME),
            "no": _pick(row, F_NO),
            "date": _pick(row, F_DATE),
            "type": _pick(row, F_TYPE),
        })
    CACHE.write_text(json.dumps({"_count": len(slim), "rows": slim}, ensure_ascii=False), encoding="utf-8")
    global _index
    _index = None
    return len(slim)


def _load_index() -> Optional[dict]:
    """建立 {統編: [許可證...]} 與 {公司名: [許可證...]} 兩份索引。"""
    global _index
    if _index is not None:
        return _index
    if not CACHE.exists():
        return None
    data = json.loads(CACHE.read_text(encoding="utf-8"))
    by_ban, by_name = defaultdict(list), defaultdict(list)
    for r in data.get("rows", []):
        if r["ban"]:
            by_ban[r["ban"]].append(r)
        if r["company"]:
            by_name[r["company"].replace(" ", "")].append(r)
    _index = {"by_ban": dict(by_ban), "by_name": dict(by_name)}
    return _index


def search_company(ban: str = "", name: str = "") -> Optional[dict]:
    """以統編優先、公司名次之查詢許可證。
    回傳 None = 尚未建立快取;回傳 dict = 查詢結果(count 可能為 0)。"""
    idx = _load_index()
    if idx is None:
        return None

    rows = idx["by_ban"].get(ban, [])
    if not rows and name:
        key = name.replace(" ", "")
        rows = idx["by_name"].get(key, [])
        if not rows:  # 模糊比對(公司名可能含「股份有限公司」等差異)
            core = key.replace("股份有限公司", "").replace("有限公司", "")
            if len(core) >= 2:
                for k, v in idx["by_name"].items():
                    if core in k:
                        rows.extend(v)

    rows = sorted(rows, key=lambda r: r["date"], reverse=True)
    new_drug = sum(1 for r in rows if "新藥" in r["type"] or "新成分" in r["type"])
    return {
        "count": len(rows),
        "new_drug": new_drug,
        "recent": [{"name": r["name"], "no": r["no"], "date": r["date"]} for r in rows[:5]],
        "_source": "live",
    }