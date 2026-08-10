# opendata.py — 政府開放資料介接(免金鑰)
# 已介接:
#   1. 經濟部商工登記(data.gov.tw / GCIS):以統一編號查公司登記基本資料
#   2. TWSE OpenAPI:上市公司基本資料(統編→股票代號)+ 每月營業收入
# 設計原則:任一來源失敗只影響該區塊(回 None),不讓整個查詢炸掉;
#          呼叫端負責把 None 區塊以內建資料或「未介接」狀態呈現。
import asyncio
import re
from typing import Optional

import httpx

import httpx_ssl

# 官方 API 公式(商工行政資料開放平臺開發指引):$filter 僅支援 Business_Accounting_NO
# 應用一=基本資料;應用二=含公司現況代碼。兩支都試,任一有結果即可。
GCIS_APIS = [
    "https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6",  # 應用一
    "https://data.gcis.nat.gov.tw/od/data/api/F05D1060-7D57-4763-BDCE-0DAF5975AFE0",  # 應用二
]
LAST_ERROR = {}  # 供 check_sources.py 顯示實際失敗原因
TWSE_COMPANY_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"  # 上市公司基本資料(含統編)
TWSE_REVENUE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"  # 上市公司每月營業收入

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# TWSE 公司清單快取(千餘筆,啟動後抓一次即可)
_twse_companies: Optional[list] = None
_twse_lock = asyncio.Lock()


def _fmt_capital(raw: str) -> str:
    """GCIS 資本額為「元」字串 → 轉成「X.X 億」顯示。"""
    try:
        n = int(str(raw).replace(",", ""))
        return f"{n / 1e8:.1f} 億" if n >= 1e8 else f"{n / 1e4:,.0f} 萬"
    except (ValueError, TypeError):
        return str(raw)


def _roc_date(raw) -> str:
    """GCIS 日期格式 {'year':108,'month':3,'day':15} 或 '1080315' → '108-03-15'。"""
    if isinstance(raw, dict):
        return f"{raw.get('year', '')}-{int(raw.get('month', 0)):02d}-{int(raw.get('day', 0)):02d}"
    s = str(raw)
    if len(s) >= 7:
        return f"{s[:-4]}-{s[-4:-2]}-{s[-2:]}"
    return s


async def fetch_gcis_registration(ban: str) -> Optional[dict]:
    """商工登記基本資料。成功回傳與前端 reg 區塊相同形狀;失敗/查無回 None。"""
    for url in GCIS_APIS:
        try:
            params = {"$format": "json", "$filter": f"Business_Accounting_NO eq {ban}", "$skip": "0", "$top": "1"}
            async with httpx_ssl.client(timeout=_TIMEOUT, follow_redirects=True) as client:
                r = await client.get(url, params=params)
            if r.status_code != 200:
                LAST_ERROR["gcis"] = f"HTTP {r.status_code}:{r.text[:120]}"
                continue
            rows = r.json()
            if not rows:
                LAST_ERROR["gcis"] = "API 回傳空陣列(查無此統編)"
                continue
            row = rows[0] if isinstance(rows, list) else rows
            status_desc = row.get("Company_Status_Desc") or ""
            status_code = str(row.get("Company_Status", ""))
            return {
                "capital": _fmt_capital(row.get("Capital_Stock_Amount") or row.get("Paid_In_Capital_Stock_Amount", "")),
                "founded": _roc_date(row.get("Company_Setup_Date", "")),
                "chairman": row.get("Responsible_Name", ""),
                "directors": [],  # 董監事為另一支 API(公司登記董監事資料),列 roadmap
                "status": status_desc or ("核准設立" if status_code == "01" else status_code or "—"),
                "address": row.get("Company_Location") or row.get("Company_Location_Address", ""),
                "name": row.get("Company_Name", ""),
            }
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as e:
            LAST_ERROR["gcis"] = f"{type(e).__name__}: {e}"
    return None


async def _get_twse_companies(client: httpx.AsyncClient) -> Optional[list]:
    global _twse_companies
    async with _twse_lock:
        if _twse_companies is None:
            r = await client.get(TWSE_COMPANY_URL)
            r.raise_for_status()
            _twse_companies = r.json()
    return _twse_companies


async def fetch_twse_revenue(ban: str) -> Optional[list]:
    """以統編找上市公司代號,回傳近 6 個月營收(億元)。非上市/失敗回 None。"""
    try:
        async with httpx_ssl.client(timeout=_TIMEOUT) as client:
            companies = await _get_twse_companies(client)
            company = next(
                (c for c in companies if str(c.get("營利事業統一編號", "")).strip() == ban), None
            )
            if not company:
                return None
            code = str(company.get("公司代號", "")).strip()

            r = await client.get(TWSE_REVENUE_URL)
            r.raise_for_status()
            rows = [x for x in r.json() if str(x.get("公司代號", "")).strip() == code]
            out = []
            for x in rows:
                try:
                    rev = int(str(x.get("營業收入-當月營收", "0")).replace(",", ""))  # 千元
                    yoy = float(str(x.get("營業收入-去年同月增減(%)", "0")).replace(",", ""))
                    ym = f"{x.get('資料年月', '')}"  # 例 11406
                    m = f"{ym[:-2]}-{ym[-2:]}" if len(ym) >= 4 else ym
                    out.append({"m": m, "val": round(rev / 1e5, 1), "yoy": round(yoy)})  # 千元→億
                except (ValueError, TypeError):
                    continue
            return out[-6:] if out else None
    except (httpx.HTTPError, ValueError, KeyError):
        return None


async def fetch_all(ban: str) -> dict:
    """並行抓取全部來源;每個 key 為 None 代表該來源失敗或查無。"""
    reg, revenue = await asyncio.gather(fetch_gcis_registration(ban), fetch_twse_revenue(ban))
    return {"reg": reg, "revenue": revenue}


# ============================================================
# GDELT 全球新聞事件庫(免金鑰、免申請)
# DOC 2.0 API:以關鍵字查近期新聞,回傳標題、日期、來源網域
# ============================================================
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
# Google News RSS:免金鑰、免申請,對台灣中文新聞覆蓋遠優於 GDELT
GNEWS_URL = "https://news.google.com/rss/search"

# ============================================================
# 新聞極性判斷(關鍵字比對 + 否定偵測 + 加權計分)
# 說明:非情感分析模型,而是可稽核的規則比對。每則新聞會回傳命中的關鍵字,
#       前端以 tooltip 顯示,判斷依據完全透明可解釋。
# ============================================================

# ---- 否定詞:出現在正向詞前方時,將該正向詞反轉為負向 ----
_NEGATORS = "未|不予|不再|不會|沒有|沒|無法|無|難以|遭|被|恐|拒|停止|終止|中止|放棄|撤回|喊卡"

# ---- 強負向(權重 3):明確的重大負面事件 ----
_NEG_STRONG = [
    # 法律與監理
    "裁罰", "罰鍰", "重罰", "開罰", "違規", "違法", "起訴", "判賠", "敗訴", "假扣押", "假處分",
    "搜索", "羈押", "涉弊", "掏空", "背信", "內線交易", "財報不實", "撤照", "廢止許可", "註銷",
    "停權", "勒令停業", "GMP不合格", "查廠未通過", "列入黑名單",
    # 財務危機
    "跳票", "違約交割", "重整", "破產", "清算", "下市", "停止交易", "繼續經營疑慮",
    "保留意見", "無法表示意見", "掏空資產", "資金缺口", "財務危機",
    # 營運重大事故
    "停工", "停產", "關廠", "解散", "大量解僱", "無薪假", "罷工", "產品召回", "全面回收",
    "禁用", "強制下架", "重大職災", "火警", "爆炸",
    # 藥業重大挫敗
    "解盲失敗", "臨床失敗", "臨床中止", "試驗中止", "療效未達", "主要療效指標未達",
    "藥害", "嚴重不良反應", "藥證遭撤銷", "退件",
]

# ---- 一般負向(權重 1) ----
_NEG_WEAK = [
    # 財務表現
    "虧損", "赤字", "減資", "衰退", "下滑", "下跌", "大跌", "重挫", "跌停", "探底", "走弱",
    "認列損失", "資產減損", "呆帳", "調降", "下修", "不如預期", "低於預期", "轉虧", "由盈轉虧",
    "毛利下滑", "營收衰退", "獲利衰退", "虧損擴大", "現金流為負",
    # 營運與市場
    "訂單流失", "解約", "終止合作", "退貨", "缺料", "斷鏈", "延宕", "延後", "遞延", "卡關",
    "產能利用率下滑", "客戶流失", "市佔下滑", "裁員", "資遣", "勞資爭議", "爭議", "糾紛",
    "訴訟", "侵權", "專利訴訟", "專利到期", "學名藥競爭", "健保砍價", "藥價調降", "藥價下跌",
    # 監理與稽核
    "調查", "約談", "函送", "糾正", "警告", "限期改善", "缺失", "列管", "稽查", "違反",
    # 市場評價
    "看空", "賣超", "降評", "目標價下修", "減碼", "警示股", "處置股", "示警", "疑慮", "隱憂",
]

# ---- 強正向(權重 3):明確的重大利多 ----
_POS_STRONG = [
    # 藥證與法規(藥業最關鍵的利多)
    "取得藥證", "藥證取得", "獲藥證", "核發藥證", "FDA核准", "EMA核准", "TFDA核准",
    "查驗登記通過", "上市許可", "藥品許可證", "突破性療法", "孤兒藥資格", "快速審查",
    "優先審查", "加速核准", "GMP認證", "PIC/S", "查廠通過", "國際認證",
    # 臨床
    "解盲成功", "臨床成功", "試驗成功", "達主要療效指標", "達標", "期中分析正面",
    "進入三期", "進入二期", "收案完成",
    # 重大商業事件
    "獨家授權", "技術授權", "里程碑金", "權利金", "技轉", "策略聯盟", "併購", "取得專利",
    "專利獲准", "重大訂單", "大單", "得標", "簽約", "量產", "投產",
    # 財務轉機
    "轉虧為盈", "扭虧為盈", "首度獲利", "創新高", "歷史新高", "營收創高",
]

# ---- 一般正向(權重 1) ----
_POS_WEAK = [
    "核准", "獲准", "通過", "許可", "認證", "取證", "拿證", "掛牌", "上櫃", "上市",
    "成長", "增長", "提升", "改善", "回升", "回溫", "上揚", "上漲", "大漲", "飆漲", "漲停",
    "獲利", "盈餘", "賺", "營收成長", "毛利提升", "EPS成長", "超預期", "優於預期",
    "上修", "調升", "看好", "看多", "買超", "升評", "目標價調升", "加碼", "法人青睞",
    "擴產", "增資", "募資完成", "投資", "布局", "合作", "結盟", "簽署", "開發成功",
    "突破", "領先", "第一", "獲獎", "認列收益", "挹注",
]

# 否定 + 正向詞 → 反轉為強負向(例:未通過、不予核准、遭駁回)
_NEGATED_POS = re.compile(f"({_NEGATORS})\\s*({'|'.join(_POS_STRONG + _POS_WEAK)})")
# 額外的否定型負面用語(直接列舉,避免漏接)
_NEG_PATTERNS = [
    "未通過", "未獲准", "未核准", "不予核准", "不予通過", "遭駁回", "遭否決", "遭退件",
    "未達標", "未達預期", "未如預期", "無法取得", "喊卡", "破局", "告吹", "生變",
]


def _senti(title: str):
    """回傳 (極性, 命中關鍵字)。極性為 pos / neg / neu。
    規則:強訊號權重 3、一般訊號權重 1;正向詞若被否定詞修飾則反轉為負向。
    """
    if not title:
        return "neu", ""
    t = str(title)
    neg_score, pos_score = 0, 0
    neg_hits, pos_hits = [], []

    # 1) 否定型:未通過、不予核准…(優先處理,權重 3)
    for p in _NEG_PATTERNS:
        if p in t:
            neg_score += 3
            neg_hits.append(p)
    for m in _NEGATED_POS.finditer(t):
        neg_score += 3
        neg_hits.append(m.group(0))

    # 2) 一般比對
    for w in _NEG_STRONG:
        if w in t:
            neg_score += 3
            neg_hits.append(w)
    for w in _NEG_WEAK:
        if w in t:
            neg_score += 1
            neg_hits.append(w)
    for w in _POS_STRONG:
        if w in t and not any(w in h for h in neg_hits):   # 已被否定者不重複計正分
            pos_score += 3
            pos_hits.append(w)
    for w in _POS_WEAK:
        if w in t and not any(w in h for h in neg_hits):
            pos_score += 1
            pos_hits.append(w)

    # 3) 判定:負向優先(授信情境下寧可誤報風險,不可漏報)
    if neg_score == 0 and pos_score == 0:
        return "neu", ""
    hits = neg_hits if neg_score >= pos_score else pos_hits
    hit_txt = "、".join(dict.fromkeys(hits))[:40]
    if neg_score >= pos_score and neg_score > 0:
        return "neg", hit_txt
    if pos_score > neg_score:
        return "pos", hit_txt
    return "neu", ""


def _gdelt_date(raw: str) -> str:
    """GDELT 日期 20260715T093000Z → 民國 115-07-15。"""
    try:
        y, m, d = int(raw[0:4]), raw[4:6], raw[6:8]
        return f"{y - 1911}-{m}-{d}"
    except (ValueError, IndexError):
        return raw[:8]


def _name_variants(name: str) -> list:
    """公司全名在新聞中少見,退化成常用簡稱一併嘗試。"""
    n = name.replace("【示範資料】", "").strip()
    out = [n]
    for suffix in ["股份有限公司", "有限公司", "工業", "科技", "生技", "製藥", "化學"]:
        n = n.replace(suffix, "")
    n = n.strip()
    if n and n not in out and len(n) >= 2:
        out.append(n)
    return out


async def _fetch_gnews(client, query: str, limit: int) -> list:
    """Google News RSS(主要來源)。回傳文章清單。"""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime

    params = {"q": query, "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"}
    r = await client.get(GNEWS_URL, params=params)
    if r.status_code != 200:
        LAST_ERROR["news"] = f"Google News HTTP {r.status_code}"
        return []
    root = ET.fromstring(r.content)
    out = []
    for item in list(root.iterfind(".//item"))[:limit]:
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        try:
            dt = parsedate_to_datetime(item.findtext("pubDate") or "")
            date = f"{dt.year - 1911}-{dt.month:02d}-{dt.day:02d}"
        except (TypeError, ValueError):
            date = ""
        senti, hit = _senti(title)
        out.append({"date": date, "title": title, "senti": senti, "senti_hit": hit,
                    "url": (item.findtext("link") or "").strip()})
    return out


async def _fetch_gdelt(client, query: str, limit: int) -> list:
    """GDELT DOC 2.0(備援來源)。"""
    params = {"query": query, "mode": "artlist", "format": "json",
              "maxrecords": str(limit), "sort": "datedesc"}
    r = await client.get(GDELT_URL, params=params)
    if r.status_code != 200:
        LAST_ERROR["news"] = f"GDELT HTTP {r.status_code}"
        return []
    try:
        arts = r.json().get("articles", [])
    except ValueError:
        LAST_ERROR["news"] = f"GDELT 非 JSON:{r.text[:100]}"
        return []
    out = []
    for a in arts:
        title = (a.get("title") or "").strip()
        if not title:
            continue
        senti, hit = _senti(title)
        out.append({"date": _gdelt_date(a.get("seendate", "")), "title": title,
                    "senti": senti, "senti_hit": hit, "url": a.get("url", "")})
    return out


async def fetch_news(company_name: str, limit: int = 6) -> Optional[list]:
    """近期新聞。主來源 Google News RSS,失敗才退 GDELT;皆失敗回 None。"""
    if not company_name:
        return None
    variants = _name_variants(company_name)
    async with httpx_ssl.client(timeout=httpx.Timeout(20.0, connect=10.0), follow_redirects=True) as client:
        for fetcher, label in [(_fetch_gnews, "GoogleNews"), (_fetch_gdelt, "GDELT")]:
            for q in variants:
                try:
                    out = await fetcher(client, q, limit)
                    if out:
                        LAST_ERROR.pop("news", None)
                        return out
                except (httpx.HTTPError, ValueError, KeyError) as e:
                    LAST_ERROR["news"] = f"{label} {type(e).__name__}: {e}"
    LAST_ERROR.setdefault("news", "兩個新聞來源皆查無結果")
    return None


# ============================================================
# 證券代號 ↔ 統一編號 對照表(免金鑰)
# 來源:TWSE 上市公司基本資料(t187ap03_L)+ TPEx 上櫃公司基本資料(t187ap03_O)
# 兩份清單都含「公司代號」與「營利事業統一編號」,建成本地快取供即時查詢
# ============================================================
import json as _json
from pathlib import Path as _Path

TPEX_COMPANY_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
CODE_BAN_CACHE = _Path(__file__).parent / "data" / "code_ban_map.json"
_code_ban: Optional[dict] = None

_F_CODE = ["公司代號", "SecuritiesCompanyCode", "Code"]
_F_BAN = ["營利事業統一編號", "統一編號", "BusinessAccountingNo"]
_F_NAME = ["公司名稱", "公司簡稱", "CompanyName"]


def _pick_field(row: dict, keys: list) -> str:
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return ""


async def build_code_ban_map(force: bool = False) -> dict:
    """下載上市+上櫃公司清單,建立 {證券代號: {ban, name, market}} 快取。"""
    global _code_ban
    if CODE_BAN_CACHE.exists() and not force:
        _code_ban = _json.loads(CODE_BAN_CACHE.read_text(encoding="utf-8"))
        return _code_ban

    mapping: dict = {}
    async with httpx_ssl.client(timeout=httpx.Timeout(60.0, connect=10.0), follow_redirects=True) as client:
        for url, market in [(TWSE_COMPANY_URL, "上市"), (TPEX_COMPANY_URL, "上櫃")]:
            try:
                r = await client.get(url)
                if r.status_code != 200:
                    LAST_ERROR[f"codemap_{market}"] = f"HTTP {r.status_code}:{r.text[:100]}"
                    continue
                for row in r.json():
                    if not isinstance(row, dict):
                        continue
                    code = _pick_field(row, _F_CODE)
                    ban = _pick_field(row, _F_BAN)
                    if code and ban:
                        mapping[code] = {"ban": ban, "name": _pick_field(row, _F_NAME), "market": market}
            except (httpx.HTTPError, ValueError, KeyError) as e:
                LAST_ERROR[f"codemap_{market}"] = f"{type(e).__name__}: {e}"

    if mapping:
        CODE_BAN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        CODE_BAN_CACHE.write_text(_json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    _code_ban = mapping
    return mapping


def code_ban_map() -> dict:
    """讀取已建立的對照表(未建立時回空 dict,不阻斷流程)。"""
    global _code_ban
    if _code_ban is None:
        _code_ban = _json.loads(CODE_BAN_CACHE.read_text(encoding="utf-8")) if CODE_BAN_CACHE.exists() else {}
    return _code_ban


def resolve_ban_by_code(code: str) -> Optional[str]:
    """證券代號 → 統一編號;查不到回 None(例如興櫃或已下市)。"""
    hit = code_ban_map().get(str(code).strip())
    return hit["ban"] if hit else None


def resolve_code_by_ban(ban: str) -> Optional[str]:
    """統一編號 → 證券代號(EAP 知識圖譜以代號為鍵,查詢前需先換算)。"""
    ban = str(ban).strip()
    if not ban:
        return None
    for code, info in code_ban_map().items():
        if info.get("ban") == ban:
            return code
    return None


# ============================================================
# 以公司名稱關鍵字查統一編號(GCIS 官方 API,免金鑰)
# API 公式(商工行政資料開放平臺開發指引):
#   /od/data/api/{id}?$format=json&$filter=Company_Name like {名稱} and Company_Status eq 01&$skip=0&$top=N
# 涵蓋全國所有登記公司,不限上市櫃
# ============================================================
GCIS_NAME_APIS = [
    "https://data.gcis.nat.gov.tw/od/data/api/6BBA2268-1367-4B42-9CCA-BC17499EBE8C",
    "https://data.gcis.nat.gov.tw/od/data/api/8813AADD-D020-4C55-A703-FC15B49F4262",
]


async def search_company_by_name(keyword: str, top: int = 30) -> list:
    """以公司名稱關鍵字查詢,回傳 [{name, ban, status}]。失敗或查無回空陣列。"""
    kw = (keyword or "").strip()
    if not kw:
        return []
    for url in GCIS_NAME_APIS:
        try:
            params = {
                "$format": "json",
                "$filter": f"Company_Name like {kw} and Company_Status eq 01",
                "$skip": "0",
                "$top": str(top),
            }
            async with httpx_ssl.client(timeout=_TIMEOUT, follow_redirects=True) as client:
                r = await client.get(url, params=params)
            if r.status_code != 200:
                LAST_ERROR["gcis_name"] = f"HTTP {r.status_code}:{r.text[:120]}"
                continue
            rows = r.json()
            if not isinstance(rows, list) or not rows:
                LAST_ERROR["gcis_name"] = "查無符合的公司"
                continue
            out = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                ban = str(row.get("Business_Accounting_NO") or "").strip()
                name = str(row.get("Company_Name") or "").strip()
                if ban and name:
                    out.append({"name": name, "ban": ban,
                                "status": row.get("Company_Status_Desc") or "核准設立"})
            if out:
                LAST_ERROR.pop("gcis_name", None)
                return out
        except (httpx.HTTPError, ValueError, KeyError) as e:
            LAST_ERROR["gcis_name"] = f"{type(e).__name__}: {e}"
    return []