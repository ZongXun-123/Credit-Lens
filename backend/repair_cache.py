"""repair_cache.py — 修復既有快取紀錄(v1.6 資料契約升級)
用法:
  python repair_cache.py --dry     只檢視會改什麼,不寫入(建議先跑這個)
  python repair_cache.py           實際修復(會先自動備份成 credit_lens.db.bak)

修復項目:
  1. 「知識庫查無」卻被打低分的 finance/tech 紀錄
     → coverage 標為 none、score 校正為 50(中性值)
     理由:查不到資料不等於體質不良,舊版把兩者混為一談,導致大量 5 分。
  2. judge 的負分與瀑布圖不一致
     → 以等比縮減扣分項的方式修正到 0-100,並維持 基礎分+增減項=最終分
  3. judge 的基礎分重算
     → 舊版由模型自行計算(同一家公司每次都不同,實測 12 與 25 並存),
       改以該公司修復後的 finance/tech 分數,依 財務×0.6 + 技術×0.4 重算
  4. 補上 v1.6 新欄位的預設值(sentiment=neutral、coverage=full)
"""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).parent / "data" / "credit_lens.db"
DRY = "--dry" in sys.argv

NO_DATA_HINT = ("查無", "無法評估", "未涵蓋", "沒有查到", "查不到", "無相關資料")


def looks_no_data(payload: dict) -> bool:
    """判斷是否為「知識庫查無」而非真的體質差:所有 finding 都指向查無。"""
    fs = payload.get("findings") or []
    if not fs:
        return False
    hit = 0
    for f in fs:
        blob = f"{f.get('text','')} {f.get('cite','')}"
        if any(k in blob for k in NO_DATA_HINT):
            hit += 1
    return hit == len(fs)


def fix_wf(wf: list, base: int) -> tuple:
    total = base + sum(w.get("value", 0) for w in wf[1:])
    if total < 0:
        minus = sum(w["value"] for w in wf[1:] if w.get("value", 0) < 0)
        plus = sum(w["value"] for w in wf[1:] if w.get("value", 0) > 0)
        room = base + plus
        if minus < 0 and room >= 0:
            ratio = room / abs(minus)
            for w in wf[1:]:
                if w.get("value", 0) < 0:
                    w["value"] = -max(1, round(abs(w["value"]) * ratio))
        total = base + sum(w.get("value", 0) for w in wf[1:])
        if total < 0 and len(wf) > 1:
            worst = min(wf[1:], key=lambda w: w.get("value", 0))
            worst["value"] -= total
            total = base + sum(w.get("value", 0) for w in wf[1:])
    return wf, max(0, min(100, total))


def main():
    if not DB.exists():
        print(f"找不到資料庫:{DB}")
        return
    if not DRY:
        bak = DB.with_suffix(".db.bak")
        shutil.copy(DB, bak)
        print(f"已備份 → {bak.name}\n")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT id, kind, company_id, company_name, payload FROM results").fetchall()

    stat = {"no_data": 0, "neg": 0, "senti": 0, "rebase": 0, "unchanged": 0}
    samples = {"no_data": [], "neg": [], "rebase": []}

    # 先掃一遍 finance/tech,建立各公司修復後的分數(供 judge 重算基礎分)
    agent_score: dict = {}
    for r in rows:
        if r["kind"] not in ("finance", "tech"):
            continue
        try:
            p = json.loads(r["payload"])
        except json.JSONDecodeError:
            continue
        if not isinstance(p, dict):
            continue
        sc = 50 if looks_no_data(p) else p.get("score")
        cov = "none" if looks_no_data(p) else p.get("coverage", "full")
        if isinstance(sc, int):
            # 同公司取最新一筆(rows 依 id 遞增,後者覆寫前者)
            agent_score.setdefault(r["company_id"], {})[r["kind"]] = (sc, cov)


    def rebase(company_id):
        """依修復後的 finance/tech 重算基礎分;資料不足回 None 表示不動。"""
        d = agent_score.get(company_id) or {}
        f, t = d.get("finance"), d.get("tech")
        if not f and not t:
            return None
        if f and t:
            fs, fc = f
            ts, tc = t
            if fc == "none" and tc == "none":
                return 50
            if fc == "none":
                return ts
            if tc == "none":
                return fs
            return int(round(fs * 0.6 + ts * 0.4))
        return (f or t)[0]

    for r in rows:
        try:
            p = json.loads(r["payload"])
        except json.JSONDecodeError:
            continue
        if not isinstance(p, dict):
            continue
        changed = False

        if r["kind"] in ("finance", "tech"):
            for f in p.get("findings") or []:
                if isinstance(f, dict) and f.get("sentiment") not in ("positive", "negative", "neutral"):
                    f["sentiment"] = "neutral"
                    changed = True
                    stat["senti"] += 1
            if "coverage" not in p:
                p["coverage"] = "full"
                changed = True
            if looks_no_data(p):
                if p.get("coverage") != "none" or p.get("score") != 50:
                    old = p.get("score")
                    p["coverage"] = "none"
                    p["score"] = 50
                    changed = True
                    stat["no_data"] += 1
                    if len(samples["no_data"]) < 5:
                        samples["no_data"].append(f"#{r['id']} {r['company_name'] or r['company_id']} {r['kind']}: {old} → 50")

        elif r["kind"] == "judge":
            wf = p.get("waterfall") or []
            if wf and wf[0].get("type") == "base":
                base = wf[0].get("value", 0)
                nb = rebase(r["company_id"])
                if nb is not None and nb != base:
                    if len(samples["rebase"]) < 5:
                        samples["rebase"].append(
                            f"#{r['id']} {r['company_name'] or r['company_id']}: 基礎分 {base} → {nb}")
                    base = nb
                    wf[0]["value"] = nb
                    stat["rebase"] += 1
                    changed = True
                calc = base + sum(w.get("value", 0) for w in wf[1:])
                calc = base + sum(w.get("value", 0) for w in wf[1:])
                if calc < 0 or p.get("final_score", 0) < 0 or p.get("final_score") != max(0, min(100, calc)):
                    old = p.get("final_score")
                    wf, final = fix_wf(wf, base)
                    p["waterfall"], p["final_score"] = wf, final
                    changed = True
                    stat["neg"] += 1
                    if len(samples["neg"]) < 5:
                        samples["neg"].append(f"#{r['id']} {r['company_name'] or r['company_id']}: {old} → {final}")

        if changed and not DRY:
            con.execute("UPDATE results SET payload=? WHERE id=?",
                        (json.dumps(p, ensure_ascii=False), r["id"]))
        if not changed:
            stat["unchanged"] += 1

    if not DRY:
        con.commit()
    con.close()

    print(f"{'【預覽模式,未寫入】' if DRY else '【已完成修復】'}  共檢視 {len(rows)} 筆\n")
    print(f"  查無資料誤判低分  {stat['no_data']:>4} 筆 → coverage=none、score=50")
    for x in samples["no_data"]:
        print(f"      {x}")
    print(f"  裁決基礎分重算    {stat['rebase']:>4} 筆 → 財務×0.6 + 技術×0.4")
    for x in samples["rebase"]:
        print(f"      {x}")
    print(f"  裁決分數超出範圍  {stat['neg']:>4} 筆 → 等比縮減扣分項至 0-100")
    for x in samples["neg"]:
        print(f"      {x}")
    print(f"  補上正負意涵欄位  {stat['senti']:>4} 筆 → sentiment=neutral")
    print(f"  無須調整          {stat['unchanged']:>4} 筆")
    if DRY:
        print("\n確認無誤後,拿掉 --dry 再執行一次即可實際寫入。")
    else:
        print("\n注意:sentiment 一律補為 neutral(舊資料無此資訊)。")
        print("      若希望正負標示準確,請對重要公司重跑該 Agent。")


main()
