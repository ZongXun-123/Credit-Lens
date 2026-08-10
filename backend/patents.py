# patents.py — 專利檢索介接(TIPO GPSS + Google Patents)
#
# 三層策略,由上而下自動降級,任何一層失敗都不影響情資查詢其他區塊:
#
#  1. TIPO GPSS API(需免費驗證碼)
#     端點:https://tiponet.tipo.gov.tw/gpss1/gpsskmc/gpss_api
#     官方格式:?userCode=驗證碼&參數=值,各參數以 & 串接
#     檢索條件採「欄位 + 關鍵字」成對指定:searchitem1=PA & searchquery1=基亞
#       searchitem 可用 PA(申請人)、TI(名稱)、AB(摘要)、CL(申請專利範圍)
#       跨欄位預設 AND;參數前加 + 為 OR、加 - 為 NOT
#     其他參數:patDB 資料庫、patAG 公開(A)/公告(B)、patTY 專利類型(I 發明/M 新型/D 設計)
#               expFld 輸出欄位、expFmt 格式(json/xml)、expQty 筆數、skip 略過筆數
#     申請驗證碼:https://gpss.tipo.gov.tw/ → API → 使用說明(免費,審核後核發)
#     系統另提供「網址工具」可視覺化產生 API 網址,可用於比對本程式組出的網址。
#
#  2. Google Patents(免金鑰)
#     Google 未提供官方公開 API。https://patents.google.com/xhr/query 是網頁自用的
#     JSON 端點,對伺服器端請求常回 403/429(判定為自動化流量),且格式可能隨時變動。
#     因此本層定位為「能通就用,不通即降級」,失敗只記錄 LAST_ERROR,不影響其他區塊。
#     可用 .env 之 GOOGLE_PATENTS_LIVE=false 整個關閉此層。
#     實務上第 3 層的深層連結才是主力:由使用者瀏覽器直接開啟,不受伺服器端封鎖影響。
#
#  3. 深層連結(永遠可用)
#     產生 Google Patents 與 TIPO GPSS 的檢索網址與布林檢索式,一鍵開新分頁。
import json
import re
from typing import Optional
from urllib.parse import quote, urlencode

import httpx

from envtools import env, env_bool

_TIMEOUT = httpx.Timeout(20.0, connect=8.0)

# --- 深層連結(模式 3)---
GOOGLE_PATENTS_BASE = "https://patents.google.com/"
# 布林檢索頁(供使用者手動貼上檢索式)
TIPO_GPSS_BASE = env("TIPO_GPSS_URL") or "https://tiponet.tipo.gov.tw/gpss1/gpsskmc/gpssbkm"

# --- TIPO GPSS API(模式 1)---
# 官方有兩個對外入口,內容相同;預設用 tiponet,連不上時可用 .env 的 TIPO_API_URL 換成 gpss1。
TIPO_API_URL = env("TIPO_API_URL") or "https://tiponet.tipo.gov.tw/gpss1/gpsskmc/gpss_api"
TIPO_API_URL_ALT = "https://gpss1.tipo.gov.tw/gpsskmc/gpss_api"

# --- Google Patents 查詢端點(模式 2)---
GOOGLE_XHR_URL = "https://patents.google.com/xhr/query"
# 帶瀏覽器 UA,避免被當成爬蟲直接擋下
_G_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://patents.google.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "X-Requested-With": "XMLHttpRequest",
}

LAST_ERROR: dict = {}


def _clean_name(name: str) -> str:
    """去掉組織型態字樣,避免檢索過窄(專利申請人多以簡稱登記)。"""
    n = re.sub(r"\s+", "", str(name or ""))
    for suffix in ["股份有限公司", "有限公司", "公司", "集團", "控股"]:
        n = n.replace(suffix, "")
    return n.strip()


def _core_name(short: str) -> str:
    """再去掉產業通用詞,取最核心的商號。
    例:基亞生物科技 → 基亞;台灣東洋藥品工業 → 東洋。
    專利申請人的登記寫法與公司全名常有落差,核心短名的命中率高得多。"""
    n = short
    for w in ["生物科技", "生技醫藥", "生醫科技", "生物醫學", "生技新藥", "化學製藥", "藥品工業",
              "生技製藥", "科技製藥", "生物製藥", "醫藥生技", "藥業", "製藥", "生技", "生醫",
              "化學工業", "化學", "科技", "工業", "國際", "實業", "投資", "醫療", "醫藥"]:
        n = n.replace(w, "")
    n = n.replace("台灣", "").replace("臺灣", "")
    return n.strip() or short


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", str(s or "")).strip()


def build_links(company_name: str, keyword: str = "") -> dict:
    """產生可直接點開就有結果的檢索連結(模式 3,永遠可用)。

    設計要點(前一版查不到東西的原因):
      · Google Patents 的 assignee= 參數比對的是「索引後的申請人名稱」,
        台灣公司多以英文羅馬拼音收錄(基亞→MEDIGEN BIOTECHNOLOGY),
        直接丟中文全名幾乎必然 0 筆。改用 q= 全文檢索,中文可命中 TW/CN 說明書。
      · 另備一組「核心短名」連結(基亞生物科技→基亞),因為專利申請人常以簡稱登記。
      · TIPO GPSS 的檢索式無法由網址帶入,只能貼進檢索框;因此明確提供可複製的檢索式。
    """
    short = _clean_name(company_name)
    if not short:
        return {}
    core = _core_name(short)

    def g(term: str) -> str:
        q = f'"{term}"'
        if keyword:
            q = f"{q} {keyword}"
        # country=TW,CN 讓中文說明書優先;不限制則英文專利會洗掉結果
        return f"{GOOGLE_PATENTS_BASE}?q={quote(q)}&country=TW,CN"

    out = {
        "company_short": short,
        "company_core": core,
        # 主連結:全文檢索完整簡稱
        "google_url": g(short),
        "google_label": f"Google Patents 檢索「{short}」",
        # 備援連結:核心短名(申請人常以此登記)
        "google_alt_url": g(core) if core != short else "",
        "google_alt_label": f"改用核心短名「{core}」再查一次" if core != short else "",
        # 英文申請人檢索(使用者可自行輸入英文名時最準)
        "google_assignee_hint": f"{GOOGLE_PATENTS_BASE}?assignee=",
        "tipo_url": TIPO_GPSS_BASE,
        "tipo_api_url": tipo_api_url(company_name, 20, keyword) if env("TIPO_API_KEY") else "",
        "tipo_expr": f"({core})@PA" + (f" AND ({keyword})@AB" if keyword else ""),
        "tipo_label": "開啟 TIPO 全球專利檢索系統",
        "note": "TIPO 需將下方檢索式貼入檢索框後送出(@PA 為申請人欄位)。"
                "Google Patents 以全文檢索中文名稱;若 0 筆,多半是該公司專利以英文名登記,"
                "可改用英文名稱於 assignee 欄位查詢。",
    }
    return out


def api_enabled() -> bool:
    return bool(env("TIPO_API_KEY"))


def google_live_enabled() -> bool:
    return env_bool("GOOGLE_PATENTS_LIVE", True)


# ============================================================
# 共用的寬鬆解析工具:兩個來源的回應結構都可能變動,不硬編死路徑
# ============================================================
def _find_first_list_of_dicts(obj, depth: int = 0) -> list:
    """遞迴找出回應中第一個「dict 組成的 list」,視為專利清單。"""
    if depth > 6:
        return []
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj[:3]):
            return obj
        for x in obj:
            hit = _find_first_list_of_dicts(x, depth + 1)
            if hit:
                return hit
    if isinstance(obj, dict):
        for v in obj.values():
            hit = _find_first_list_of_dicts(v, depth + 1)
            if hit:
                return hit
    return []


_TOTAL_KEYS = ("total", "total_num_results", "totalCount", "total-count", "count",
               "recordCount", "hits", "筆數", "總筆數")


def _find_total(obj, depth: int = 0) -> Optional[int]:
    if depth > 6 or not isinstance(obj, dict):
        return None
    for k in _TOTAL_KEYS:
        v = obj.get(k)
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.replace(",", "").isdigit():
            return int(v.replace(",", ""))
    for v in obj.values():
        if isinstance(v, dict):
            hit = _find_total(v, depth + 1)
            if hit is not None:
                return hit
    return None


def _pick(row: dict, keys: list) -> str:
    for k in keys:
        v = row.get(k)
        if isinstance(v, list) and v:
            v = v[0]
        if isinstance(v, dict):  # 例如 {"text": "..."} 或 {"#text": "..."}
            v = v.get("text") or v.get("#text") or ""
        if v not in (None, "", []):
            return _strip_tags(str(v))
    return ""


# ============================================================
# 模式 1:TIPO GPSS API
# ============================================================
# 欄位名稱在不同版本/格式(json 或 xml 轉 json)可能不同,逐一嘗試
_T_TITLE = ["專利名稱", "發明名稱", "TI", "title", "inventionTitle", "patent-title"]
_T_NO = ["公開公告號", "公告號", "證書號", "PN", "publicationNumber", "publication-number",
         "申請號", "AN", "applicationNumber"]
_T_DATE = ["公開公告日", "公告日", "ID", "publicationDate", "publication-date",
           "申請日", "AD", "applicationDate"]
_T_APPLICANT = ["申請人", "PA", "applicant", "assignee"]


def tipo_api_params(term: str, top: int = 20, keyword: str = "") -> dict:
    """組出 GPSS API 參數。官方格式為「欄位 + 關鍵字」成對指定,而非把欄位當參數名。
    先前誤用 {"PA": "基亞"} 的寫法,GPSS 不認得該參數,故永遠查不到資料。"""
    params = {
        "userCode": env("TIPO_API_KEY") or "",
        "patDB": env("TIPO_PATDB") or "TWA,TWB",   # 本國公開 + 本國公告
        "patAG": env("TIPO_PATAG") or "A,B",       # A 公開公報、B 公告公報
        "patTY": env("TIPO_PATTY") or "I,M",       # I 發明、M 新型(D 為設計,預設不納入)
        "searchitem1": "PA",                        # 申請人欄位
        "searchquery1": term,
        "expFld": "PN,AN,ID,AD,TI,PA",              # 公開號/申請號/公開日/申請日/名稱/申請人
        "expFmt": "json",
        "expQty": str(min(max(top, 1), 50)),
    }
    if keyword:
        params["searchitem2"] = "AB"                # 摘要欄位,與申請人為 AND 關係
        params["searchquery2"] = keyword
    return params


def tipo_api_url(company_name: str, top: int = 20, keyword: str = "") -> str:
    """產生完整 API 網址,可直接貼進瀏覽器驗證(診斷用)。"""
    term = _core_name(_clean_name(company_name))
    return f"{TIPO_API_URL}?{urlencode(tipo_api_params(term, top, keyword))}"


async def fetch_tipo(company_name: str, top: int = 20, keyword: str = "") -> Optional[dict]:
    """呼叫 TIPO GPSS API 取得專利件數與清單。
    未設定驗證碼回 None;呼叫失敗亦回 None 並記錄於 LAST_ERROR["tipo"]。
    依序嘗試核心短名與完整簡稱,兩者皆無結果才放棄(申請人登記寫法不一)。"""
    if not env("TIPO_API_KEY"):
        return None
    short = _clean_name(company_name)
    if not short:
        return None
    core = _core_name(short)

    async def _call(url: str, term: str):
        params = tipo_api_params(term, top, keyword)
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(url, params=params)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}:{r.text[:150]}"
        body = r.text.strip()
        if not body:
            return None, "回應為空"
        try:
            data = r.json()
        except ValueError:
            # GPSS 於參數錯誤時會回純文字訊息,直接帶回供使用者判讀
            return None, f"回應非 JSON:{body[:200]}"
        out = _normalize_tipo(data, top)
        if out is None:
            return None, f"回應結構無法解析:{str(data)[:200]}"
        return out, ""

    attempts = [(TIPO_API_URL, core)]
    if core != short:
        attempts.append((TIPO_API_URL, short))
    attempts.append((TIPO_API_URL_ALT, core))     # 主機連不上時的備援入口

    last = ""
    for url, term in attempts:
        try:
            out, e = await _call(url, term)
        except httpx.HTTPError as ex:
            last = f"{type(ex).__name__}: {ex}"
            continue
        if out and out.get("count"):
            out["_term"] = term
            out["_host"] = url
            return out
        last = e or f"以「{term}」查詢 0 筆"
    LAST_ERROR["tipo"] = last
    return None


def _normalize_tipo(data, top: int) -> Optional[dict]:
    """把 GPSS 回應轉成前端使用的統一結構;完全解析不出來時回 None。"""
    # 明確的錯誤訊息(驗證碼錯誤、逾量等)
    if isinstance(data, dict):
        for k in ("error", "errorMsg", "message", "錯誤訊息"):
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                LAST_ERROR["tipo"] = v[:200]
                return None

    rows = _find_first_list_of_dicts(data)
    total = _find_total(data) if isinstance(data, dict) else None
    if not rows and total is None:
        return None

    items = []
    for row in rows[:top]:
        rec = {
            "title": _pick(row, _T_TITLE),
            "no": _pick(row, _T_NO),
            "date": _pick(row, _T_DATE),
            "applicant": _pick(row, _T_APPLICANT),
        }
        if rec["title"] or rec["no"]:
            items.append(rec)
    return {"count": total if total is not None else len(items), "recent": items, "_source": "live"}


# ============================================================
# 模式 2:Google Patents 內部查詢端點(免金鑰、非官方)
# ============================================================
_G_TITLE = ["title"]
_G_NO = ["publication_number", "patent_number"]
_G_DATE = ["publication_date", "grant_date", "filing_date", "priority_date"]
_G_ASSIGNEE = ["assignee"]


async def fetch_google(company_name: str, top: int = 10) -> Optional[dict]:
    """查詢 Google Patents(assignee=公司簡稱)。
    關閉、失敗或格式變動時回 None 並記錄於 LAST_ERROR["google"],由深層連結接手。"""
    if not google_live_enabled():
        return None
    short = _clean_name(company_name)
    if not short:
        return None

    # 端點的 url 參數 = 檢索頁網址列的 query string,整段再做一次 URL 編碼
    core = _core_name(short)

    async def _query(term: str, mode: str):
        """mode=q 全文檢索(中文可命中);mode=assignee 申請人欄位(英文名較準)。"""
        params = {"num": min(max(top, 10), 25)}
        params["q" if mode == "q" else "assignee"] = f'"{term}"' if mode == "q" else term
        inner = urlencode(params)
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(GOOGLE_XHR_URL, params={"url": inner, "exp": ""}, headers=_G_HEADERS)
        if r.status_code != 200:
            hint = ("(Google 判定為自動化流量而封鎖,屬端點本身限制;"
                    "畫面上的一鍵檢索連結由瀏覽器直接開啟,仍可正常使用)"
                    if r.status_code in (403, 429) else "")
            LAST_ERROR["google"] = f"HTTP {r.status_code}{hint}:{r.text[:120]}"
            return None
        try:
            data = r.json()
        except ValueError:
            LAST_ERROR["google"] = f"回應非 JSON:{r.text[:120]}"
            return None
        out = _parse_google(data, top)
        if out is None:
            LAST_ERROR["google"] = f"回應結構無法解析:{str(data)[:200]}"
        return out

    try:
        # 依序嘗試:全文簡稱 → 全文核心短名 → 申請人欄位;任一有結果即回傳
        attempts = [(short, "q")]
        if core != short:
            attempts.append((core, "q"))
        attempts.append((short, "assignee"))
        for term, mode in attempts:
            out = await _query(term, mode)
            if out and out.get("count"):
                out["_term"] = term
                out["_mode"] = "全文檢索" if mode == "q" else "申請人欄位"
                return out
        LAST_ERROR["google"] = f"以「{short}」與「{core}」查詢均為 0 筆(可能以英文名登記)"
        return None
    except httpx.HTTPError as e:
        LAST_ERROR["google"] = f"{type(e).__name__}: {e}"
        return None


def _parse_google(data, top: int) -> Optional[dict]:
    """實測結構:results.total_num_results 與 results.cluster[0].result[].patent{...};
    以寬鬆解析容錯,結構大改時回 None 降級。"""
    if not isinstance(data, dict):
        return None
    results = data.get("results", data)
    total = _find_total(results if isinstance(results, dict) else data)

    rows = []
    if isinstance(results, dict):
        for cl in results.get("cluster", []) or []:
            for it in (cl or {}).get("result", []) or []:
                pat = it.get("patent") if isinstance(it, dict) else None
                if isinstance(pat, dict):
                    rows.append(pat)
    if not rows:
        rows = [r.get("patent", r) for r in _find_first_list_of_dicts(data)
                if isinstance(r, dict)]

    if not rows and total is None:
        return None

    items = []
    for row in rows[:top]:
        rec = {
            "title": _pick(row, _G_TITLE),
            "no": _pick(row, _G_NO),
            "date": _pick(row, _G_DATE),
            "applicant": _pick(row, _G_ASSIGNEE),
        }
        if rec["title"] or rec["no"]:
            items.append(rec)
    return {"count": total if total is not None else len(items), "recent": items, "_source": "live"}


# ============================================================
# 組合入口:main.py 只需呼叫這一支
# ============================================================
async def enrich(company_name: str, keyword: str = "") -> dict:
    """深層連結(必有)+ TIPO 與 Google 的即時結果(盡力而為)。
    回傳結構向下相容:count / recent / _source 仍為 TIPO 資料,
    Google 結果放在 google 子物件。"""
    out = build_links(company_name, keyword)
    if not out:
        return {}

    tipo = await fetch_tipo(company_name)
    if tipo:
        out.update(tipo)   # count / recent / _source(與既有前端相容)
    google = await fetch_google(company_name)
    if google:
        out["google"] = google

    out["api_enabled"] = api_enabled()
    if not tipo and api_enabled():
        out["tipo_error"] = LAST_ERROR.get("tipo", "")
    if not google and google_live_enabled():
        out["google_error"] = LAST_ERROR.get("google", "")
    return out