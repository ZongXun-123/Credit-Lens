# eap_export.py — 精誠 EAP 知識圖譜查詢結果的資料層
#
# 為什麼是這條路:EAP 平台的真實介面是知識圖譜的 Cypher 查詢(見 data/eap_exports/query-1.json),
# 而非聊天 API。實務流程為「平台 UI 執行 Cypher → 匯出 xlsx/csv → 本模組讀取索引」。
# 圖譜結構(財務資料-model.gml):
#   (公司企業)-[申報的歷史財報]->(財報數據)
#            -[展現獲利的能力]->(獲利能力指標)
#            -[面臨經營風險]->(經營與償債風險能力)
#            -[展現擴張的潛力]->(企業成長指標)
#
# 匯出檔放進 backend/data/eap_exports/,本模組會自動掃描全部 .xlsx/.csv
import csv
import json
import re
from pathlib import Path
from typing import Optional

EXPORT_DIR = Path(__file__).parent / "data" / "eap_exports"
_index: Optional[dict] = None

# 欄位名稱 → 內部代號(去掉「節點.」前綴後比對關鍵字)
FIELD_MAP = {
    "借款依存度": "borrow_dep",
    "流動比率": "current_ratio",
    "速動比率": "quick_ratio",
    "負債比率": "debt_ratio",
    "合併總損益": "net_income",
    "常續性稅後淨利": "recurring_income",
    "來自營運之現金流量": "cfo",
    "ROE綜合損益": "roe",
    "ROEA稅後": "roea",
    "已實現銷貨毛利成長率": "gp_growth",
    "稅後淨利成長率": "ni_growth",
    "營業利益率": "op_margin",
    "毛利率": "gross_margin",
}

# 顯示用中文名與單位
LABEL = {
    "borrow_dep": ("借款依存度", "%"), "current_ratio": ("流動比率", "%"),
    "quick_ratio": ("速動比率", "%"), "debt_ratio": ("負債比率", "%"),
    "net_income": ("合併總損益", "萬元"), "recurring_income": ("常續性稅後淨利", "萬元"),
    "cfo": ("營運現金流量", "萬元"), "roe": ("ROE 綜合損益", "%"),
    "roea": ("ROEA 稅後", "%"), "gp_growth": ("毛利成長率", "%"),
    "ni_growth": ("稅後淨利成長率", "%"), "op_margin": ("營業利益率", "%"),
    "gross_margin": ("毛利率", "%"),
}


def _norm_header(h: str) -> Optional[str]:
    """『經營與償債風險能力.償債能力指標_借款依存度』→ borrow_dep"""
    if not h:
        return None
    h = str(h).strip()
    if h.endswith("名稱"):
        return "_name"
    if h.endswith("代號"):
        return "_code"
    tail = h.split(".")[-1]
    for key, code in FIELD_MAP.items():
        if key in tail:
            return code
    return None


def _num(v) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[,\s%]", "", str(v))
    try:
        return float(s)
    except ValueError:
        return None


def _read_xlsx(path: Path) -> list:
    try:
        import openpyxl
    except ImportError:
        return []
    rows_out = []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 2:
            continue
        cols = [_norm_header(h) for h in rows[0]]
        if "_code" not in cols and "_name" not in cols:
            continue  # 非明細表(例如摘要頁),略過
        for r in rows[1:]:
            rec = {}
            for c, v in zip(cols, r):
                if not c:
                    continue
                rec[c] = str(v).strip() if c in ("_name", "_code") else _num(v)
            if rec.get("_name") or rec.get("_code"):
                rows_out.append(rec)
    return rows_out


def _read_csv(path: Path) -> list:
    rows_out = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if len(rows) < 2:
        return []
    cols = [_norm_header(h) for h in rows[0]]
    for r in rows[1:]:
        rec = {}
        for c, v in zip(cols, r):
            if not c:
                continue
            rec[c] = str(v).strip() if c in ("_name", "_code") else _num(v)
        if rec.get("_name") or rec.get("_code"):
            rows_out.append(rec)
    return rows_out


def build_index(force: bool = False) -> dict:
    """掃描匯出目錄,建立 {代號: 公司彙總} 與 {名稱: 公司彙總}。
    Cypher 多重關聯會產生笛卡兒展開(同公司多列),故以區間(min~max)彙總。"""
    global _index
    if _index is not None and not force:
        return _index

    raw = []
    if EXPORT_DIR.exists():
        for p in sorted(EXPORT_DIR.iterdir()):
            if p.suffix.lower() == ".xlsx":
                raw += _read_xlsx(p)
            elif p.suffix.lower() == ".csv":
                raw += _read_csv(p)

    by_key: dict = {}
    for rec in raw:
        code = str(rec.get("_code") or "").split(".")[0].strip()
        name = (rec.get("_name") or "").strip()
        key = code or name
        if not key:
            continue
        c = by_key.setdefault(key, {"code": code, "name": name, "rows": 0, "metrics": {}})
        c["rows"] += 1
        if name and not c["name"]:
            c["name"] = name
        for k, v in rec.items():
            if k.startswith("_") or v is None:
                continue
            m = c["metrics"].setdefault(k, {"min": v, "max": v, "vals": []})
            m["min"] = min(m["min"], v)
            m["max"] = max(m["max"], v)
            if len(m["vals"]) < 50:
                m["vals"].append(v)

    idx = {"by_code": {}, "by_name": {}}
    for c in by_key.values():
        if c["code"]:
            idx["by_code"][c["code"]] = c
        if c["name"]:
            idx["by_name"][c["name"].replace(" ", "")] = c
    _index = idx
    return idx


def available() -> bool:
    idx = build_index()
    return bool(idx["by_code"] or idx["by_name"])


def companies() -> list:
    idx = build_index()
    seen, out = set(), []
    for c in list(idx["by_code"].values()) + list(idx["by_name"].values()):
        k = c["code"] or c["name"]
        if k not in seen:
            seen.add(k)
            out.append({"code": c["code"], "name": c["name"], "rows": c["rows"],
                        "metrics": len(c["metrics"])})
    return out


def find(code: str = "", name: str = "") -> Optional[dict]:
    idx = build_index()
    if code and str(code).strip() in idx["by_code"]:
        return idx["by_code"][str(code).strip()]
    if name:
        key = name.replace(" ", "")
        if key in idx["by_name"]:
            return idx["by_name"][key]
        core = key.replace("股份有限公司", "").replace("有限公司", "")
        for k, v in idx["by_name"].items():
            if core and (core in k or k in core):
                return v
    return None


def fmt_range(m: dict, unit: str = "") -> str:
    lo, hi = m["min"], m["max"]
    f = (lambda x: f"{x:,.0f}") if abs(hi) >= 1000 else (lambda x: f"{x:.2f}")
    return f"{f(lo)}{unit}" if abs(hi - lo) < 1e-9 else f"{f(lo)} ~ {f(hi)}{unit}"


# ============================================================
# 由真實指標產出財務分析(供 /api/review/finance 使用)
# 每筆 finding 都附具體數字與圖譜欄位名稱作為引用來源(防幻覺)
# ============================================================
def analyze(company: dict) -> dict:
    m = company["metrics"]
    findings, deductions = [], 0

    def cite(field_code: str) -> str:
        label = LABEL.get(field_code, (field_code, ""))[0]
        return f"EAP 知識圖譜·{label}"

    # 償債能力
    if "borrow_dep" in m:
        v = m["borrow_dep"]
        txt = f"借款依存度 {fmt_range(v, '%')},"
        if v["max"] > 30:
            txt += "高度仰賴外部融資,再融資風險偏高。"
            deductions += 12
        elif v["max"] > 20:
            txt += "對外部資金有相當依賴,須追蹤借款到期結構。"
            deductions += 6
        else:
            txt += "外部資金依賴度尚屬可控。"
        findings.append({"text": txt, "cite": cite("borrow_dep"), "confidence": 0.95})

    if "debt_ratio" in m:
        v = m["debt_ratio"]
        txt = f"負債比率 {fmt_range(v, '%')},"
        txt += "負債結構偏重,須檢視長短期債務配置。" if v["max"] > 50 else "整體負債水準尚屬穩健。"
        if v["max"] > 50:
            deductions += 8
        findings.append({"text": txt, "cite": cite("debt_ratio"), "confidence": 0.95})

    if "current_ratio" in m and "quick_ratio" in m:
        cr, qr = m["current_ratio"], m["quick_ratio"]
        txt = f"流動比率 {fmt_range(cr, '%')}、速動比率 {fmt_range(qr, '%')},"
        if cr["min"] < 100:
            txt += "短期償債能力偏弱。"
            deductions += 10
        elif cr["min"] > 200:
            txt += "表面短期償債能力充裕,惟須檢視流動資產品質與變現性。"
        else:
            txt += "短期償債能力尚可。"
        findings.append({"text": txt, "cite": cite("current_ratio"), "confidence": 0.9})

    # 獲利
    if "net_income" in m:
        v = m["net_income"]
        if v["min"] < 0:
            findings.append({
                "text": f"合併總損益 {fmt_range(v, ' 萬元')},期間內出現虧損,獲利尚未轉正。",
                "cite": cite("net_income"), "confidence": 0.95})
            deductions += 15 if v["min"] < -50000 else 10

    if "roe" in m:
        v = m["roe"]
        if v["min"] < 0:
            findings.append({
                "text": f"ROE 綜合損益 {fmt_range(v, '%')},股東權益報酬為負,獲利能力待改善。",
                "cite": cite("roe"), "confidence": 0.92})
            deductions += 8

    # 現金流(授信最關鍵)
    if "cfo" in m:
        v = m["cfo"]
        if v["min"] < 0:
            findings.append({
                "text": f"營運現金流量 {fmt_range(v, ' 萬元')},本業尚未產生正向現金流,還款來源高度依賴外部籌資。",
                "cite": cite("cfo"), "confidence": 0.96})
            deductions += 18

    # 成長性
    if "ni_growth" in m:
        v = m["ni_growth"]
        if v["min"] < -50:
            findings.append({
                "text": f"稅後淨利成長率 {fmt_range(v, '%')},期間出現大幅衰退,獲利波動劇烈。",
                "cite": cite("ni_growth"), "confidence": 0.88})
            deductions += 7

    if not findings:
        findings.append({"text": "知識圖譜查得本公司資料,惟未涵蓋本次評分所需之財務指標欄位。",
                         "cite": "EAP 知識圖譜", "confidence": 0.5})

    score = max(5, min(95, 90 - deductions))
    return {
        "agent": "finance",
        "score": score,
        "findings": findings[:5],   # 契約 6.1:1–5 筆,依重要性排序
    }
