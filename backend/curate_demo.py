"""curate_demo.py — 現場展示資料整理

把資料庫巡過一輪，只留下「可完整走完一次展示」的公司，其餘全部清除；
並為留下的每家公司補上一筆會議紀錄與拜訪後評分，讓展示流程不會中斷。

用法:
  python curate_demo.py --dry     只檢視結果，不寫入（建議先跑）
  python curate_demo.py           修復 + 為素材足夠的公司產生會議紀錄（預設不刪任何公司）
  python curate_demo.py --prune   額外把素材不足的公司整批刪除
  python curate_demo.py --keep 4105,1786   指定公司即使素材不足也視為保留

處理步驟:
  1. 修復  ─ 「查無資料」誤標為 full 者改為 none；裁決基礎分依 財務×0.6+技術×0.4
             重算；瀑布數學不一致者修正並確保落在 0-100。
  2. 評級  ─ 逐公司檢查五個項目是否具「實質內容」（有引用來源、非查無、
             雷達五維齊全、瀑布可驗算）。
  3. 分級  ─ 標出各公司的素材完整度。預設「不刪除」，僅供案件總覽排序使用
             （素材齊全者自動排在前面）；加 --prune 才會實際刪除。
  4. 補齊  ─ 為保留的每家公司產生一筆貼近其真實風險點的會議紀錄，
             並預先寫入萃取結果與拜訪後評分（replay 模式下可秒回）。
  5. 輸出  ─ 會議紀錄另存為 data/demo_notes/<代號>_<公司名>.txt，
             展示時可直接上傳或貼上。
"""
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
DB = BASE / "data" / "credit_lens.db"
NOTES_DIR = BASE / "data" / "demo_notes"

DRY = "--dry" in sys.argv
PRUNE = "--prune" in sys.argv        # 預設不刪除,僅分級與補齊
EXTRA_KEEP = set()
if "--keep" in sys.argv:
    i = sys.argv.index("--keep")
    if i + 1 < len(sys.argv):
        EXTRA_KEEP = {x.strip() for x in sys.argv[i + 1].split(",") if x.strip()}

KINDS = ["finance", "tech", "judge", "pre_brief", "market_read"]
LABEL = {"finance": "財務", "tech": "技術", "judge": "裁決", "pre_brief": "情資", "market_read": "市場"}
NO_DATA = ("查無", "無法評估", "無法進行", "無法評價", "無相關資料", "未涵蓋", "沒有查到")

OK, NG, WARN = "\033[92m○\033[0m", "\033[91m✗\033[0m", "\033[93m△\033[0m"


# ───────────────────────── 讀取 ─────────────────────────
def load(con):
    rows = con.execute("SELECT * FROM results ORDER BY id").fetchall()
    data, names = {}, {}
    for r in rows:
        if r["company_name"]:
            names.setdefault(r["company_id"], r["company_name"])
        data.setdefault(r["company_id"], {}).setdefault(r["kind"], []).append(dict(r))
    return data, names


def latest(recs):
    """取釘選優先、否則最新的一筆，回傳 (紀錄, payload)。"""
    r = sorted(recs, key=lambda x: (x["pinned"], x["id"]))[-1]
    try:
        return r, json.loads(r["payload"])
    except json.JSONDecodeError:
        return r, {}


def is_no_data(payload) -> bool:
    fs = payload.get("findings") or []
    if not fs:
        return True
    return all(any(k in (f.get("text", "") + f.get("cite", "")) for k in NO_DATA) for f in fs)


# ───────────────────────── 修復 ─────────────────────────
def repair(con, data):
    stat = {"cov": 0, "base": 0, "math": 0, "senti": 0}
    agent_score = {}

    # 先修財務與技術，順便記下修復後的分數供裁決重算基礎分
    for cid, kinds in data.items():
        for k in ("finance", "tech"):
            if k not in kinds:
                continue
            for rec in kinds[k]:
                try:
                    p = json.loads(rec["payload"])
                except json.JSONDecodeError:
                    continue
                changed = False
                for f in p.get("findings") or []:
                    if f.get("sentiment") not in ("positive", "negative", "neutral"):
                        f["sentiment"] = "neutral"
                        changed = True
                        stat["senti"] += 1
                if is_no_data(p):
                    if p.get("coverage") != "none" or p.get("score") != 50:
                        p["coverage"], p["score"] = "none", 50
                        changed = True
                        stat["cov"] += 1
                elif "coverage" not in p:
                    p["coverage"] = "full"
                    changed = True
                if changed:
                    rec["payload"] = json.dumps(p, ensure_ascii=False)
                    if not DRY:
                        con.execute("UPDATE results SET payload=? WHERE id=?", (rec["payload"], rec["id"]))
        # 記錄修復後的最新分數
        for k in ("finance", "tech"):
            if k in kinds:
                _, p = latest(kinds[k])
                agent_score.setdefault(cid, {})[k] = (p.get("score"), p.get("coverage", "full"))

    # 再修裁決
    for cid, kinds in data.items():
        if "judge" not in kinds:
            continue
        d = agent_score.get(cid, {})
        f, t = d.get("finance"), d.get("tech")
        base_new = None
        if f and t:
            (fs, fc), (ts, tc) = f, t
            if fc == "none" and tc == "none":
                base_new = 50
            elif fc == "none":
                base_new = ts
            elif tc == "none":
                base_new = fs
            elif isinstance(fs, int) and isinstance(ts, int):
                base_new = round(fs * 0.6 + ts * 0.4)
        elif f or t:
            one = f or t
            base_new = one[0] if one[1] != "none" else 50

        for rec in kinds["judge"]:
            try:
                p = json.loads(rec["payload"])
            except json.JSONDecodeError:
                continue
            wf = p.get("waterfall") or []
            if not wf or wf[0].get("type") != "base":
                continue
            changed = False
            if base_new is not None and wf[0]["value"] != base_new:
                wf[0]["value"] = base_new
                changed = True
                stat["base"] += 1
            base = wf[0]["value"]
            total = base + sum(w.get("value", 0) for w in wf[1:])
            if total < 0:      # 扣分過度：等比縮減
                minus = sum(w["value"] for w in wf[1:] if w.get("value", 0) < 0)
                plus = sum(w["value"] for w in wf[1:] if w.get("value", 0) > 0)
                room = base + plus
                if minus < 0 and room >= 0:
                    ratio = room / abs(minus)
                    for w in wf[1:]:
                        if w.get("value", 0) < 0:
                            w["value"] = -max(1, round(abs(w["value"]) * ratio))
                total = base + sum(w.get("value", 0) for w in wf[1:])
                if total < 0:
                    worst = min(wf[1:], key=lambda w: w.get("value", 0))
                    worst["value"] -= total
                    total = base + sum(w.get("value", 0) for w in wf[1:])
            total = max(0, min(100, total))
            if p.get("final_score") != total:
                p["final_score"] = total
                changed = True
                stat["math"] += 1
            if changed:
                p["waterfall"] = wf
                rec["payload"] = json.dumps(p, ensure_ascii=False)
                if not DRY:
                    con.execute("UPDATE results SET payload=? WHERE id=?", (rec["payload"], rec["id"]))
    return stat


# ───────────────────────── 評級 ─────────────────────────
def grade(kinds) -> dict:
    g = {}
    if "finance" in kinds:
        _, p = latest(kinds["finance"])
        g["finance"] = "real" if not is_no_data(p) else "nodata"
    if "tech" in kinds:
        _, p = latest(kinds["tech"])
        g["tech"] = "real" if not is_no_data(p) else "nodata"
    if "judge" in kinds:
        _, p = latest(kinds["judge"])
        wf = p.get("waterfall") or []
        ok = (bool(p.get("verdict")) and len(wf) >= 2 and wf[0].get("type") == "base"
              and wf[0]["value"] + sum(w.get("value", 0) for w in wf[1:]) == p.get("final_score"))
        g["judge"] = "real" if ok else "bad"
    if "pre_brief" in kinds:
        _, p = latest(kinds["pre_brief"])
        g["pre_brief"] = "real" if len(p.get("radar", [])) == 5 and len(p.get("questions", [])) >= 2 else "bad"
    if "market_read" in kinds:
        _, p = latest(kinds["market_read"])
        g["market_read"] = "real" if p.get("summary") and p.get("recommendation") else "bad"
    return g


def tier_of(g) -> str:
    """A = 五項齊全且財務有實質內容；B = 五項齊全但財務為查無；其餘 = 淘汰。"""
    if not all(g.get(k) in ("real", "nodata") for k in KINDS):
        return "-"
    if any(g.get(k) == "bad" for k in KINDS):
        return "-"
    if g.get("tech") != "real" or g.get("judge") != "real" or g.get("pre_brief") != "real":
        return "-"
    return "A" if g.get("finance") == "real" else "B"


# ───────────────────── 會議紀錄產生 ─────────────────────
def pick_risks(kinds) -> list:
    """自財務與技術的負面發現挑出風險點，作為會議紀錄的主題。"""
    out = []
    for k in ("finance", "tech"):
        if k not in kinds:
            continue
        _, p = latest(kinds[k])
        for f in p.get("findings") or []:
            if f.get("sentiment") == "negative":
                txt = f.get("text", "")
                txt = re.sub(r"（[^）]*）|\([^)]*\)", "", txt)           # 去掉夾註
                txt = re.sub(r"[，,、]?\s*(?:須|需|應)?扣\s*\d+\s*分[。，,]?", "", txt)  # 去掉評分術語
                txt = re.sub(r"\s+", "", txt).strip("，,。、 ")
                if txt:
                    out.append(txt if txt.endswith("。") else txt + "。")
    return out[:3]


def brief_questions(kinds) -> list:
    if "pre_brief" not in kinds:
        return []
    _, p = latest(kinds["pre_brief"])
    return [q.get("q", "") for q in p.get("questions", [])][:3]


def make_notes(cid, name, kinds) -> str:
    risks = pick_risks(kinds)
    qs = brief_questions(kinds)
    today = datetime.now()
    roc = f"{today.year - 1911}-{today.month:02d}-{today.day:02d}"
    L = [f"{roc} 客戶拜訪會議紀錄", f"受訪企業：{name}（代號 {cid}）",
         "出席：財務長、研發長、本行授信人員", ""]
    def wrap(text, width=34, indent="       "):
        """長句依中文寬度斷行,避免展示時被硬截斷成半句話。"""
        text = re.sub(r"\s+", "", str(text))
        out, cur = [], ""
        for ch in text:
            cur += ch
            if len(cur) >= width and ch in "。；，、？!？":
                out.append(cur); cur = ""
            elif len(cur) >= width + 8:
                out.append(cur); cur = ""
        if cur:
            out.append(cur)
        return [out[0]] + [indent + x for x in out[1:]]

    L.append("一、拜訪前提問之回覆")
    if qs:
        for i, q in enumerate(qs, 1):
            seg = wrap(q)
            L.append(f"{i}. 提問：{seg[0]}")
            L.extend(seg[1:])
            if i == 1:
                L.append("   回覆：財務長說明已與往來銀行取得續約共識，並提供近三個月的資金運用表；")
                L.append("         承諾於下月十五日前補送已用印之額度續約承諾書。")
            elif i == 2:
                L.append("   回覆：研發長表示主力產品線已通過查驗登記，量產排程不受影響；")
                L.append("         惟坦承新產品的上市時程較原規劃延後一季。")
            else:
                L.append("   回覆：公司說明將調整資本支出優先序，優先確保既有產線稼動率，")
                L.append("         非急迫之擴廠計畫暫緩。")
    else:
        L.append("1. 就財務結構與產品線布局進行一般性訪談，客戶配合說明。")
    L.append("")
    L.append("二、針對風險點之說明")
    if risks:
        for i, r in enumerate(risks, 1):
            seg = wrap(r, 36, "   ")
            L.append(f"{i}. {seg[0]}")
            L.extend(seg[1:])
        L.append("   客戶回應：已提出具體改善時程，惟部分佐證文件尚未提供，")
        L.append("             同意於本月底前補齊相關證明。")
    else:
        L.append("1. 訪談中未發現重大新增風險，客戶營運狀況與知識庫資料相符。")
    L.append("")
    L.append("三、客戶承諾事項")
    L.append(f"1. 財務長承諾於 {today.year - 1911}-{(today.month % 12) + 1:02d}-15 前提供銀行額度續約承諾書。")
    L.append(f"2. 研發長承諾於 {today.year - 1911}-{(today.month % 12) + 1:02d}-28 前提供產品查驗登記進度證明。")
    L.append("")
    L.append("四、本行觀察")
    L.append("客戶配合度良好，對本行提問均正面回應並願意補件；")
    L.append("惟部分承諾尚停留於口頭階段，建議俟文件到齊後再行覆評。")
    return "\n".join(L)


def make_extract(cid, name, kinds) -> dict:
    today = datetime.now()
    y, m = today.year - 1911, (today.month % 12) + 1
    risks = pick_risks(kinds)
    responses = []
    if risks:
        responses.append({"risk": risks[0][:30], "summary": "已提出改善時程，佐證文件尚未提供", "verdict": "partial"})
    if len(risks) > 1:
        responses.append({"risk": risks[1][:30], "summary": "客戶說明產線不受影響，並提供排程佐證", "verdict": "resolved"})
    if not responses:
        responses.append({"risk": "營運與財務結構", "summary": "訪談內容與知識庫資料相符", "verdict": "resolved"})
    return {
        "commitments": [
            {"item": "提供銀行額度續約承諾書", "owner": "財務長", "due": f"{y}-{m:02d}-15"},
            {"item": "提供產品查驗登記進度證明", "owner": "研發長", "due": f"{y}-{m:02d}-28"},
        ],
        "responses": responses,
        "new_risks": [{"text": "新產品上市時程較原規劃延後一季，需追蹤對營收預估之影響。"}],
    }


def make_score(base: int, ext: dict) -> dict:
    wf = [{"label": "拜訪前基準", "value": base, "type": "base"}]
    resolved = sum(1 for r in ext["responses"] if r.get("verdict") == "resolved")
    partial = sum(1 for r in ext["responses"] if r.get("verdict") == "partial")
    if resolved:
        wf.append({"label": "風險已化解", "value": 3 * resolved, "type": "plus"})
    if partial:
        wf.append({"label": "部分化解", "value": 1 * partial, "type": "plus"})
    if ext["commitments"]:
        wf.append({"label": "承諾具體", "value": 2, "type": "plus"})
    if ext["new_risks"]:
        wf.append({"label": "新增追蹤事項", "value": -2, "type": "minus"})
    final = max(0, min(100, base + sum(w["value"] for w in wf[1:])))
    return {
        "final_score": final, "waterfall": wf,
        "recommendation": "客戶對拜訪前提問均正面回應並承諾補件，主要風險由未化解轉為部分化解；"
                          "惟新產品時程遞延須列入追蹤。建議附條件核貸，俟承諾文件到齊後覆評。",
    }


# ───────────────────────── 主流程 ─────────────────────────
def main():
    if not DB.exists():
        print(f"找不到資料庫：{DB}")
        return
    if not DRY:
        shutil.copy(DB, DB.with_suffix(".db.bak"))
        print(f"已備份 → {DB.with_suffix('.db.bak').name}\n")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    data, names = load(con)

    print(f"=== 步驟 1：修復既有紀錄（共 {len(data)} 家公司）===")
    st = repair(con, data)
    print(f"  覆蓋度校正 {st['cov']} 筆　基礎分重算 {st['base']} 筆　"
          f"瀑布修正 {st['math']} 筆　正負補值 {st['senti']} 筆\n")

    # 注意:repair() 已同步更新記憶體中的 payload,
    # 預覽模式不會寫入資料庫,故此處不可重新載入,否則會拿到未修復的內容。

    print("=== 步驟 2：逐公司評級 ===")
    print(f"{'等級':<5}{'代號':<7}{'公司':<16} " + " ".join(f"{LABEL[k]:<3}" for k in KINDS))
    keep, drop = [], []
    for cid in sorted(data):
        if cid in ("code:4105",) or not re.fullmatch(r"\d{4,8}", cid):
            drop.append((cid, names.get(cid, ""), "識別碼異常"))
            continue
        g = grade(data[cid])
        tier = "A" if cid in EXTRA_KEEP else tier_of(g)
        marks = []
        for k in KINDS:
            v = g.get(k)
            marks.append(OK if v == "real" else (WARN if v == "nodata" else NG))
        line = f"{tier:<5}{cid:<7}{(names.get(cid,'') or '')[:14]:<16} " + " ".join(f"{m:<3}" for m in marks)
        if tier in ("A", "B"):
            keep.append((cid, names.get(cid, ""), tier))
            print(line)
        else:
            drop.append((cid, names.get(cid, ""), "項目不全"))
    print(f"\n  {OK} 有實質內容　{WARN} 知識庫查無（顯示為資料不足）　{NG} 缺漏或不合格")
    print(f"\n保留 {len(keep)} 家（A 級 {sum(1 for x in keep if x[2]=='A')} 家、"
          f"B 級 {sum(1 for x in keep if x[2]=='B')} 家）／刪除 {len(drop)} 家")
    if drop:
        print("  刪除名單：" + "、".join(f"{c}{('('+n[:6]+')') if n else ''}" for c, n, _ in drop[:18]))

    keep_ids = {c for c, _, _ in keep}

    if PRUNE:
        print("\n=== 步驟 3：清除素材不足公司的紀錄（--prune）===")
        total_del = 0
        for cid, nm, why in drop:
            n = con.execute("SELECT COUNT(*) c FROM results WHERE company_id=?", (cid,)).fetchone()["c"]
            total_del += n
            if not DRY:
                con.execute("DELETE FROM results WHERE company_id=?", (cid,))
        print(f"  刪除 {total_del} 筆紀錄")
    else:
        print("\n=== 步驟 3：保留全部公司（未加 --prune）===")
        print(f"  {len(drop)} 家素材不足的公司保留於資料庫,案件總覽會自動排在後面,")
        print("  仍可點進去即時分析或以 warmup.py 補跑。")

    print("\n=== 步驟 4：為保留公司補上會議紀錄與拜訪後評分 ===")
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    made = 0
    for cid, nm, tier in keep:
        kinds = data[cid]
        _, jp = latest(kinds["judge"])
        base = jp.get("final_score", 50)
        notes = make_notes(cid, nm or cid, kinds)
        ext = make_extract(cid, nm or cid, kinds)
        sc = make_score(base, ext)

        safe = re.sub(r"[^\w\u4e00-\u9fff]", "", (nm or cid))[:12]
        fp = NOTES_DIR / f"{cid}_{safe}.txt"
        if not DRY:
            fp.write_text(notes, encoding="utf-8")
            for kind, payload in (("extract", ext), ("score", sc)):
                con.execute("DELETE FROM results WHERE company_id=? AND kind=?", (cid, kind))
                con.execute(
                    "INSERT INTO results(kind,company_id,company_name,req_key,payload,pinned,created_at) "
                    "VALUES(?,?,?,?,?,1,?)",
                    (kind, cid, nm, "", json.dumps(payload, ensure_ascii=False), now))
        made += 1
        print(f"  {cid} {(nm or '')[:12]:<14} 基準 {base:>3} → 覆評 {sc['final_score']:>3} 分"
              f"　承諾 {len(ext['commitments'])} 項　紀錄 {len(notes)} 字")

    if not DRY:
        if PRUNE and keep_ids:
            con.execute("DELETE FROM results WHERE kind IN ('report','report_star') "
                        "AND company_id NOT IN (%s)" % ",".join("?" * len(keep_ids)), tuple(keep_ids))
        con.commit()
    con.close()

    print(f"\n=== 完成 ===")
    print(f"保留公司：{'、'.join(c for c, _, _ in keep)}")
    if not DRY:
        print(f"會議紀錄已輸出至 {NOTES_DIR}（共 {made} 份，展示時可直接上傳）")
        print("\n說明:")
        print("  · 案件總覽預設依「素材完整度」排序,上面這些公司會自動排在最前面,")
        print("    並標示「素材齊全」或「部分素材」;其餘公司排在後面,標示「尚未分析」。")
        print("  · 素材不足的公司仍可正常點入使用,系統會即時呼叫 EAP 分析。")
        print("  · 若想再補齊其他公司:python warmup.py --list 看缺口,再執行 warmup.py。")
        print("  · 展示當天把 CACHE_MODE 設為 replay,已有素材者全程秒回。")
    else:
        print("\n【預覽模式，未寫入】確認無誤後拿掉 --dry 再執行一次。")


main()