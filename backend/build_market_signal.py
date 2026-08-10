"""build_market_signal.py — 由 TEJ 未調整股價 xlsx 重建 data/market_signal.json

用法:
  1. 把股價 xlsx 放進 backend/data/prices/  (檔名不限,可放多個年度)
  2. python build_market_signal.py            合併既有公司 + 新公司,重算全體分位
     python build_market_signal.py --dry      只試算並印出差異,不寫檔
     python build_market_signal.py --only-new 保留既有公司的分位與分數,只補新公司

xlsx 必要欄位(TEJ 匯出格式):
  代號 / 名稱 / 年月日 / 收盤價(元) / 成交值(千元) / 報酬率％ / 週轉率％ / 市值(百萬元)

指標定義(與既有資料一致,已用重疊公司 6661 逐項比對驗證):
  vol_full_pct  全期年化波動度 = 簡單日報酬標準差 × √252 × 100
  vol_1y_pct    近一年年化波動度(最近 252 個交易日)
  mdd_pct       最大回撤 = min(收盤 / 期間累積高點 − 1) × 100
  mom_1y_pct    近一年報酬率
  turnover_pct  期間平均週轉率
  amihud        Amihud 非流動性 = mean(|日報酬| / 成交值(千元)) × 1e6,數值越小越流動
  mktcap        最後一個交易日市值(百萬元)

評分合成(說明書 §5):
  分位數 pctile 為同業排名百分位(越高越好);波動度與 amihud 為反向(值小者分位高)。
  market_score = 50 + Σ 權重 × 100 × (pctile − 0.5)
  權重:波動 0.30、回撤 0.25、規模 0.20、流動性 0.15、動能 0.10
  風險等級:≥67 低風險、≥45 中等、其餘偏高風險;交易日不足者不予評分。
"""
import json
import math
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
PRICE_DIR = BASE / "data" / "prices"
OUT = BASE / "data" / "market_signal.json"

DRY = "--dry" in sys.argv
ONLY_NEW = "--only-new" in sys.argv

WEIGHTS = {"vol": 0.30, "mdd": 0.25, "size": 0.20, "liq": 0.15, "mom": 0.10}
LABEL = {"vol": "波動度", "mdd": "回撤", "size": "規模", "liq": "流動性", "mom": "動能"}
# 分位方向:True = 值越小越好(反向)
REVERSE = {"vol": True, "mdd": False, "size": False, "liq": True, "mom": False}
METRIC_OF = {"vol": "vol_full_pct", "mdd": "mdd_pct", "size": "mktcap",
             "liq": "amihud", "mom": "mom_1y_pct"}

TRADING_DAYS = 252


def _num(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _date(v):
    if isinstance(v, datetime):
        return v
    s = str(v or "").strip()[:10]
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def read_prices() -> dict:
    """讀取 data/prices/ 下所有 xlsx,回傳 {代號: {name, rows[]}}。"""
    try:
        import openpyxl
    except ImportError:
        print("需要 openpyxl:pip install openpyxl")
        sys.exit(1)

    if not PRICE_DIR.exists():
        print(f"找不到目錄 {PRICE_DIR},請建立後放入 TEJ 股價 xlsx。")
        sys.exit(1)
    files = sorted(p for p in PRICE_DIR.iterdir() if p.suffix.lower() in (".xlsx", ".xlsm"))
    if not files:
        print(f"{PRICE_DIR} 內沒有 xlsx 檔。")
        sys.exit(1)

    data: dict = {}
    for f in files:
        wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        header = [str(h or "").strip() for h in next(it)]

        def col(*names):
            for n in names:
                for i, h in enumerate(header):
                    if h.startswith(n):
                        return i
            return None

        ci = {"code": col("代號"), "name": col("名稱"), "date": col("年月日"),
              "close": col("收盤價"), "val": col("成交值"), "ret": col("報酬率％", "報酬率%"),
              "turn": col("週轉率"), "cap": col("市值")}
        missing = [k for k, v in ci.items() if v is None]
        if missing:
            print(f"  略過 {f.name}:缺少欄位 {missing}")
            continue

        n = 0
        for r in it:
            code = str(r[ci["code"]] or "").strip()
            d = _date(r[ci["date"]])
            close = _num(r[ci["close"]])
            if not code or d is None or close is None:
                continue
            e = data.setdefault(code, {"name": str(r[ci["name"]] or "").strip(), "rows": []})
            e["rows"].append({"d": d, "close": close, "val": _num(r[ci["val"]]),
                              "ret": _num(r[ci["ret"]]), "turn": _num(r[ci["turn"]]),
                              "cap": _num(r[ci["cap"]])})
            n += 1
        print(f"  讀入 {f.name}:{n:,} 列")

    for e in data.values():
        e["rows"].sort(key=lambda x: x["d"])
        # 同一日重複(兩檔期間重疊)時保留後者
        dedup = {}
        for x in e["rows"]:
            dedup[x["d"]] = x
        e["rows"] = [dedup[k] for k in sorted(dedup)]
    return data


def compute_metrics(rows: list) -> dict:
    closes = [x["close"] for x in rows]
    rets = [x["ret"] / 100 for x in rows if x["ret"] is not None]

    def vol(series):
        return round(st.stdev(series) * math.sqrt(TRADING_DAYS) * 100, 1) if len(series) > 2 else None

    peak, mdd = -1e18, 0.0
    for p in closes:
        peak = max(peak, p)
        if peak > 0:
            mdd = min(mdd, p / peak - 1)

    mom = None
    if len(closes) > TRADING_DAYS and closes[-TRADING_DAYS - 1]:
        mom = round((closes[-1] / closes[-TRADING_DAYS - 1] - 1) * 100, 1)

    turns = [x["turn"] for x in rows if x["turn"] is not None]
    am = [abs(x["ret"] / 100) / x["val"] * 1e6 for x in rows
          if x["ret"] is not None and x["val"]]
    caps = [x["cap"] for x in rows if x["cap"] is not None]

    return {
        "last_close": closes[-1],
        "vol_full_pct": vol(rets),
        "vol_1y_pct": vol(rets[-TRADING_DAYS:]),
        "mdd_pct": round(mdd * 100, 1),
        "mom_1y_pct": mom,
        "turnover_pct": round(st.mean(turns), 2) if turns else None,
        "amihud": round(st.mean(am), 4) if am else None,
        "mktcap": round(caps[-1]) if caps else None,
    }


def monthly_closes(rows: list, months: int = 72) -> list:
    """每月最後一個交易日的收盤價,取最近 months 個月。"""
    by_month = {}
    for x in rows:
        by_month[(x["d"].year, x["d"].month)] = x["close"]
    keys = sorted(by_month)[-months:]
    return [by_month[k] for k in keys]


def tier_of(n_days: int) -> str:
    if n_days >= 250:
        return "full"
    if n_days >= 60:
        return "partial"
    return "insufficient"


def pctiles(companies: list) -> None:
    """以排名百分位計算各構面分位(1 起算、同分取平均、除以有效家數)。
    此為標準做法;既有資料由組員離線產生,方法略有差異,故本腳本一律重算全體以保持一致。"""
    for key, mkey in METRIC_OF.items():
        vals = [(c["metrics"].get(mkey), c) for c in companies
                if c["tier"] != "insufficient" and c["metrics"].get(mkey) is not None]
        if not vals:
            continue
        n = len(vals)
        ordered = sorted(vals, key=lambda t: t[0], reverse=REVERSE[key])  # 由差到好
        # 同分取平均名次
        i = 0
        while i < n:
            j = i
            while j + 1 < n and ordered[j + 1][0] == ordered[i][0]:
                j += 1
            avg_rank = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ordered[k][1].setdefault("pctile", {})[key] = round(avg_rank / n, 2)
            i = j + 1


def score_of(c: dict) -> tuple:
    if c["tier"] == "insufficient":
        return None, [], "資料不足"
    wf = [{"label": "基準", "value": 50, "type": "base"}]
    total = 50
    for key, w in WEIGHTS.items():
        p = (c.get("pctile") or {}).get(key)
        if p is None:
            continue
        delta = round(w * 100 * (p - 0.5))
        if delta == 0:
            continue
        wf.append({"label": LABEL[key], "value": delta, "type": "plus" if delta > 0 else "minus"})
        total += delta
    total = max(0, min(100, total))
    level = "低風險" if total >= 67 else ("中等" if total >= 45 else "偏高風險")
    return total, wf, level


def main():
    print("\n=== 重建市場訊號資料 ===\n")
    raw = read_prices()
    print(f"\n股價檔含 {len(raw)} 家公司")

    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"companies": [], "prices": {}, "meta": {}}
    old_by_code = {c["code"]: c for c in old.get("companies", [])}
    old_prices = old.get("prices", {})

    companies, prices, added, updated = [], {}, [], []

    # 1) 由股價檔計算
    for code, e in raw.items():
        rows = e["rows"]
        m = compute_metrics(rows)
        c = {"code": code, "name": e["name"], "tier": tier_of(len(rows)),
             "n_days": len(rows), "metrics": m}
        companies.append(c)
        prices[code] = monthly_closes(rows)
        (updated if code in old_by_code else added).append(f"{code} {e['name']}")

    # 2) 既有但股價檔沒有的公司:沿用原本的指標
    for code, c in old_by_code.items():
        if code in raw:
            continue
        keep = {"code": code, "name": c.get("name", ""), "tier": c.get("tier", "full"),
                "n_days": c.get("n_days", 0), "metrics": c.get("metrics", {})}
        if ONLY_NEW:      # 保留原分位與分數,不重算
            keep["pctile"] = c.get("pctile", {})
            keep["market_score"] = c.get("market_score")
            keep["level"] = c.get("level", "資料不足")
            keep["waterfall"] = c.get("waterfall", [])
        companies.append(keep)
        if code in old_prices:
            prices[code] = old_prices[code]

    # 3) 分位與評分
    if ONLY_NEW:
        pool = [c for c in companies if "market_score" not in c]
        pctiles(pool)
        for c in pool:
            c["market_score"], c["waterfall"], c["level"] = score_of(c)
    else:
        pctiles(companies)
        for c in companies:
            c["market_score"], c["waterfall"], c["level"] = score_of(c)

    companies.sort(key=lambda c: (c["market_score"] is None, -(c["market_score"] or 0)))

    # 期間
    all_dates = [x["d"] for e in raw.values() for x in e["rows"]]
    period = f"{min(all_dates):%Y-%m} ~ {max(all_dates):%Y-%m}" if all_dates else old["meta"].get("period", "")
    valid = sum(1 for c in companies if c["tier"] != "insufficient")

    out = {
        "meta": {"universe": valid, "total": len(companies), "weights": WEIGHTS, "base": 50,
                 "industry": old.get("meta", {}).get("industry", "生技製藥"), "period": period},
        "companies": companies,
        "prices": prices,
    }

    print(f"\n新增 {len(added)} 家:{', '.join(added[:20])}")
    print(f"更新 {len(updated)} 家:{', '.join(updated[:20])}")
    print(f"合計 {len(companies)} 家(可評分 {valid} 家)")

    # 分數變動比較
    print("\n--- 分數變動(前 12 家)---")
    shown = 0
    for c in companies:
        o = old_by_code.get(c["code"])
        if not o:
            print(f"  {c['code']:>6} {c['name'][:8]:<10} 新增 → {c['market_score']} 分 {c['level']}")
        elif o.get("market_score") != c["market_score"]:
            print(f"  {c['code']:>6} {c['name'][:8]:<10} {o.get('market_score')} → {c['market_score']} 分")
        else:
            continue
        shown += 1
        if shown >= 12:
            break

    if DRY:
        print("\n【預覽模式,未寫檔】確認無誤後拿掉 --dry 再執行。\n")
        return
    if OUT.exists():
        bak = OUT.with_suffix(".json.bak")
        bak.write_text(OUT.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"\n已備份原檔 → {bak.name}")
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"已寫入 {OUT.name}({OUT.stat().st_size / 1024:.0f} KB)")
    print("重啟後端即生效(market.py 於啟動時載入)。\n")


main()
