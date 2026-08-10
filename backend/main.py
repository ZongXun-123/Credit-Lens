# main.py — Credit-Lens FastAPI 後端(規格書 v1.1 第 5 章全部 API + 情資/報告中心三支)
# 執行:uvicorn main:app --reload --port 8000
# MOCK_MODE=true(.env)時所有 API 回傳規格書範例 JSON(Demo 保險絲,7.3)
import json
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import mock_data as MOCK
import models as M
import opendata
import eap_export
import market
import tfda
import cache_store
from envtools import env, env_bool
from eap import EapError, ask_agent, chat_raw as eap_chat_raw, status as eap_status_info

load_dotenv()
MOCK_MODE = env_bool("MOCK_MODE", False)            # 預設 false:直接呼叫 EAP
# 展示防禦(組員版構想的誠實化):EAP 呼叫失敗時自動降級回規格書範例 JSON,
# Demo 現場網路/平台出狀況也不會中斷;設 false 則回傳 5.2 錯誤格式讓前端顯示重試。
FALLBACK_ON_ERROR = env_bool("FALLBACK_ON_ERROR", True)
# 成功結果快取:off=不用 / record=成功即存(平時測試) / replay=優先讀快取(Demo 當天)
CACHE_MODE = (env("CACHE_MODE") or "record").lower()
# 展示白名單:逗號分隔的證券代號。設定後案件總覽只列出這些公司,
# 避免現場點到沒有素材的案件。留空則列出知識庫全部公司。
DEMO_COMPANIES = [x.strip() for x in (env("DEMO_COMPANIES") or "").split(",") if x.strip()]
# 情資查詢是否呼叫真實政府開放資料(TWSE / 商工登記);失敗會逐區塊降級,不影響整體
OPEN_DATA = env_bool("OPEN_DATA", True)             # 預設 true:直接打政府開放資料
REPORT_DIR = Path(__file__).parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Credit-Lens API", version="1.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in (env("ALLOW_ORIGINS") or "*").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/reports", StaticFiles(directory=REPORT_DIR), name="reports")


# ---------- 統一錯誤格式(5.2) ----------
def err(status: int, code: str, message: str):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "INTERNAL_ERROR", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(Exception)
async def any_exc_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "系統發生未預期錯誤"}})


async def eap_or_fallback(agent: str, message: str, fallback: dict, session_name: str,
                          required: tuple = (), cache_id: str = "", cache_name: str = "",
                          cache_key: str = "", cache_first: bool = False, force: bool = False) -> dict:
    """呼叫 EAP 並驗證回應結構。
    失敗、資料不足、或缺少必要欄位時,依 FALLBACK_ON_ERROR 決定降級或回傳錯誤(7.3 保險絲)。
    required 為契約必要欄位,可避免格式不符時 Pydantic 直接拋 500。

    快取(Demo 保命符):CACHE_MODE=replay 時優先讀取先前存下的成功結果;
    record/replay 模式下,凡通過驗證的回應都會寫入 data/credit_lens.db。"""
    def degrade(reason: str, code: str = "LLM_FORMAT_ERROR", status: int = 502):
        # 降級前最後一搏:即使不在 replay 模式,也試著用過去存下的成功結果
        if CACHE_MODE != "off" and cache_id:
            hit = cache_store.load(agent, cache_id, cache_key)
            if hit:
                print(f"♻️ [快取救援] {agent}/{cache_id}:{reason} → 改用先前成功結果")
                return {**hit, "_from_cache": True, "_cache_reason": "rescue"}
        if FALLBACK_ON_ERROR:
            print(f"⚠️ [展示防禦] {agent}:{reason} → 自動降級回範例資料。")
            return dict(fallback)
        err(status, code, reason)

    # ---- 快取優先(v1.3 預設):有既有成功結果就直接用,除非 force 強制重跑 ----
    # cache_first 適用於「輸入不變、結果可重用」的端點(finance/tech/judge/pre_brief/market_read);
    # 輸入相依端點(assess/extract/score)不啟用,以免新輸入拿到舊結果。
    if CACHE_MODE != "off" and cache_id and not force and (cache_first or CACHE_MODE == "replay"):
        meta = cache_store.load_meta(agent, cache_id, cache_key)
        if meta:
            print(f"▶️ [既有紀錄] {agent}/{cache_id}:#{meta['id']}({meta['created_at']},未呼叫 EAP)")
            return {**meta["payload"], "_from_cache": True, "_rec_id": meta["id"],
                    "_cached_at": meta["created_at"], "_pinned": meta["pinned"]}

    try:
        data = await ask_agent(agent, message, session_name)
    except EapError as e:
        return degrade(f"EAP 呼叫失敗({e.code}: {e.message})", e.code, e.status)

    if not isinstance(data, dict):
        return degrade(f"回應非物件({type(data).__name__})")

    # EAP 明確表示知識庫查無此公司資料
    if str(data.get("error", "")).upper() == "INSUFFICIENT_DATA":
        return degrade("EAP 知識庫查無此公司資料(INSUFFICIENT_DATA)", "COMPANY_NOT_FOUND", 404)

    missing = [k for k in required if k not in data]
    if missing:
        preview = str(data)[:150]
        return degrade(f"回應缺少必要欄位 {missing};原始內容 {preview}")

    # v1.6:存檔前先補齊新欄位預設值,避免舊格式與髒資料進入資料庫
    if agent in ("finance", "tech"):
        data.setdefault("coverage", "full")
        for f in data.get("findings", []) or []:
            if isinstance(f, dict) and f.get("sentiment") not in ("positive", "negative", "neutral"):
                f["sentiment"] = "neutral"
        if data.get("coverage") == "none":
            data["score"] = 50           # 查無資料一律中性值,不得因此低分
    if agent == "judge" and isinstance(data.get("final_score"), int) and data["final_score"] < 0:
        data["final_score"] = 0          # 負分為模型算術錯誤,存檔前先夾住

    # ---- 通過驗證:存起來,供日後重播;回應附上紀錄中繼資料 ----
    if CACHE_MODE != "off" and cache_id:
        rid = cache_store.save(agent, cache_id, data, cache_name, cache_key)
        print(f"💾 [快取] {agent}/{cache_id} 已存檔 #{rid}")
        if rid:
            data = {**data, "_rec_id": rid, "_cached_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "_from_cache": False, "_pinned": False}
    return data


# ---------- 共用驗證 ----------
def _company_ref(req: "M.ReviewRequest") -> str:
    """組出送給 EAP 的公司識別:「名稱(code:代號)」。
    EAP 知識圖譜以證券代號(公司企業.代號)為鍵,用統編查會檢索不到;
    因此一律以代號識別:優先用 company_code,其次 company_id 若本身即為代號(≤6碼),
    再其次由統編透過對照表反查代號。都查不到時退回名稱,並於後端 log 提醒。"""
    cid = norm_code(req.company_id)
    code = norm_code(req.company_code)
    if not code and cid and cid.isdigit() and len(cid) <= 6:
        code = cid                                    # company_id 本身就是證券代號
    if not code and cid and len(cid) == 8 and cid.isdigit():
        code = opendata.resolve_code_by_ban(cid) or ""  # 統編 → 代號
    name = (req.company_name or "").strip()
    if code:
        return f"{name}(code:{code})" if name else f"code:{code} 之公司"
    print(f"⚠️ [公司識別] {name or cid}:無法取得證券代號,改以名稱查詢(知識圖譜可能檢索不到)")
    return name or cid


def _cid_any(company_id: str, company_code: str = "") -> str:
    """把任何形式的公司識別轉為統一的快取鍵(證券代號)。

    前端案件清單的 id 優先使用統一編號(如 15458455),但快取與 EAP 查詢皆以
    證券代號(1711)為鍵。先前 judge / assess / extract / score 直接拿 company_id
    當快取鍵,導致「存進去用代號、查出來用統編」而永遠對不上,
    每次進入案件頁都會重新呼叫 EAP。此函式統一兩邊的鍵。"""
    return _cache_id(M.ReviewRequest(company_id=company_id or "", company_code=company_code or ""))


def _with_meta(model, raw: dict) -> dict:
    """以 Pydantic 驗證契約後轉回 dict,並保留快取中繼欄位(_rec_id/_cached_at/_from_cache/_pinned),
    供前端顯示「既有紀錄」標示與歷次紀錄面板。"""
    out = model.model_dump()
    for k in ("_rec_id", "_cached_at", "_from_cache", "_pinned"):
        if k in raw:
            out[k] = raw[k]
    return out


def norm_code(v) -> str:
    """證券代號正規化。EAP 知識圖譜的「代號」欄位為數值型別,
    經 JSON 序列化後會變成 1711.0 這種浮點字串,直接拿去查股價會查無。
    一律轉成純數字字串:1711.0 → 1711、" 4105 " → 4105、01786 → 01786(保留前導零)。"""
    s = str(v if v is not None else "").strip()
    if not s:
        return ""
    if s.endswith(".0"):
        s = s[:-2]
    elif "." in s:
        try:
            f = float(s)
            if f.is_integer():
                s = str(int(f))
        except ValueError:
            pass
    return s


def _cache_id(req: "M.ReviewRequest") -> str:
    """快取鍵:一律用證券代號(與 EAP 查詢一致);無代號才退回統編或名稱。

    注意:_company_ref 在公司名稱從缺時會回「code:1711 之公司」這種描述句,
    早期版本直接以 rstrip(")") 取值會得到「1711 之公司」,導致快取永遠對不上。
    此處改以正規表示式只取代號本身,確保不論名稱有無都得到同一把鍵。"""
    ref = _company_ref(req)
    m = re.search(r"code[:：]\s*([0-9A-Za-z]+)", ref)
    if m:
        return norm_code(m.group(1))
    return norm_code(req.company_code) or norm_code(req.company_id) or (req.company_name or "").strip()


def drop_no_cite(findings: list[dict]) -> list[dict]:
    """防幻覺(10.1):無 cite 的發現直接丟棄。"""
    return [f for f in findings if f.get("cite")]


def _judge_base(fin, tech) -> tuple[int, str]:
    """基礎分確定性計算:財務 60%、技術 40%。
    任一方 coverage="none"(知識庫查無)時排除該面向,改由另一方單獨代表,
    兩方皆查無則以 50 分中性值計。這避免「查不到資料」被當成「體質不良」而拉低分數。"""
    fc = getattr(fin, "coverage", "full")
    tc = getattr(tech, "coverage", "full")
    if fc == "none" and tc == "none":
        return 50, "財務與技術面均查無資料,以中性值計"
    if fc == "none":
        return int(round(tech.score)), "財務面查無資料,基礎分以技術面為準"
    if tc == "none":
        return int(round(fin.score)), "技術面查無資料,基礎分以財務面為準"
    return int(round(fin.score * 0.6 + tech.score * 0.4)), f"財務 {fin.score}×0.6 + 技術 {tech.score}×0.4"


def fix_waterfall(waterfall: list[dict], base_value: int | None = None) -> tuple[list[dict], int]:
    """數學一致(5.5/5.10):基礎分 + 各增減項 = final_score,由後端驗算保證。
    base_value 給定時(5.10)強制第一筆 type=base 且 value=base_value。"""
    if not waterfall or waterfall[0].get("type") != "base":
        err(502, "LLM_FORMAT_ERROR", "waterfall 第一筆必須為 base")
    if base_value is not None:
        waterfall[0]["value"] = base_value
    base = waterfall[0]["value"]
    total = base + sum(w["value"] for w in waterfall[1:])

    # v1.6:模型有時把扣分加總得比基礎分還多,導致負分(實測資料庫中出現過 -23)。
    # 直接裁切到 0 會讓瀑布圖對不上;改為等比縮減所有扣分項,保留相對嚴重度且維持數學一致。
    if total < 0:
        minus_sum = sum(w["value"] for w in waterfall[1:] if w["value"] < 0)
        plus_sum = sum(w["value"] for w in waterfall[1:] if w["value"] > 0)
        room = base + plus_sum                      # 最多只能扣到 0
        if minus_sum < 0 and room >= 0:
            ratio = room / abs(minus_sum)
            for w in waterfall[1:]:
                if w["value"] < 0:
                    w["value"] = -max(1, round(abs(w["value"]) * ratio)) if ratio > 0 else 0
        total = base + sum(w["value"] for w in waterfall[1:])
        # 縮減後仍可能因四捨五入略為越界,最後再修正最大扣分項
        if total < 0 and len(waterfall) > 1:
            worst = min(waterfall[1:], key=lambda w: w["value"])
            worst["value"] -= total
            total = base + sum(w["value"] for w in waterfall[1:])
    if total > 100:
        total = 100
    return waterfall, max(0, min(100, total))


# ---------- 5.3 財務分析 Agent ----------
@app.post("/api/review/finance")
async def review_finance(req: M.ReviewRequest):
    if MOCK_MODE:
        return MOCK.FINANCE
    # 優先序 1:EAP 知識圖譜匯出資料(真實財報指標,附具體數字與欄位引用)
    hit = eap_export.find(code=req.company_code or req.company_id, name=req.company_name)
    if hit:
        print(f"[財務Agent] {hit['name']}({hit['code']}) ← EAP 知識圖譜 {hit['rows']} 列 / {len(hit['metrics'])} 指標")
        result = eap_export.analyze(hit)
        result["findings"] = drop_no_cite(result["findings"])
        result.setdefault("coverage", "full")
        return _with_meta(M.AgentResult(**result), result)

    # 優先序 2:EAP /chat API;失敗依 FALLBACK_ON_ERROR 決定降級
    data = await eap_or_fallback(
        "finance",
        f"目標企業:{_company_ref(req)}。請依 EAP 知識庫中該企業(以 code 代號檢索)之財報與信用資料進行分析。",
        MOCK.FINANCE, f"財務審查-{req.company_name or req.company_id}",
        required=("score", "findings"),
        cache_id=_cache_id(req), cache_name=req.company_name,
        cache_first=True, force=req.force)
    data["agent"] = "finance"
    data["findings"] = drop_no_cite(data.get("findings", []))
    return _with_meta(M.AgentResult(**data), data)


# ---------- 5.4 技術情報 Agent ----------
async def _tech_external_intel(company_id: str, company_name: str) -> str:
    """蒐集外部情資(新聞/許可證),組成餵給 EAP 的素材塊。
    任一來源失敗只影響該段;OPEN_DATA=false 時整段略過(只靠知識庫+產業通識)。"""
    if not OPEN_DATA or not company_name:
        return ""
    # v1.7:專利來源已移除(TIPO 需申請驗證碼、Google 無官方 API 且封鎖伺服器端請求),
    # 技術面改以知識庫財報、藥品許可證與新聞為依據。
    news_task = opendata.fetch_news(company_name, limit=5)
    news = await news_task

    parts = []

    # 新聞(Google News / GDELT,senti 為簡易情緒標記)
    if isinstance(news, list) and news:
        lines = ["近期新聞:"]
        for n in news[:5]:
            senti = f"[{n['senti']}]" if n.get("senti") else ""
            lines.append(f"  · {n.get('date','')} {senti}{n.get('title','')}")
        parts.append("\n".join(lines))

    # 藥品許可證(本地快取,同步呼叫;生技業的法規護城河訊號)
    try:
        lic = tfda.search_company(ban=company_id if company_id.isdigit() else "", name=company_name)
        if lic and lic["count"]:
            parts.append(f"食藥署藥品許可證:共 {lic['count']} 張(新藥/新成分 {lic['new_drug']} 張),"
                         f"最新:{'、'.join(p['name'] for p in lic['recent'][:3])}")
    except Exception:
        pass

    if not parts:
        return ""
    return "\n\n【外部情資(系統即時查得,可直接引用)】\n" + "\n\n".join(parts)


@app.post("/api/review/tech")
async def review_tech(req: M.ReviewRequest):
    if MOCK_MODE:
        return MOCK.TECH
    intel = await _tech_external_intel(req.company_id, req.company_name)
    if intel:
        print(f"[技術Agent] {req.company_name}:外部情資 {len(intel)} 字元(新聞/許可證)已併入")
    data = await eap_or_fallback(
        "tech",
        f"目標企業:{_company_ref(req)}。"
        f"請依 EAP 知識庫中該企業(以 code 代號檢索)之財務資料、下方外部情資、以及你的產業知識,評估技術護城河。{intel}",
        MOCK.TECH, f"技術審查-{req.company_name or req.company_id}",
        required=("score", "findings"),
        cache_id=_cache_id(req), cache_name=req.company_name,
        cache_first=True, force=req.force)
    data["agent"] = "tech"
    data["findings"] = drop_no_cite(data.get("findings", []))
    return _with_meta(M.AgentResult(**data), data)


# ---------- 5.5 風險審查官 ----------
@app.post("/api/review/judge")
async def review_judge(req: M.JudgeRequest):
    if MOCK_MODE:
        return MOCK.JUDGE
    fin, tech = req.finance_result, req.tech_result
    base, note = _judge_base(fin, tech)

    payload = json.dumps(
        {"finance_result": fin.model_dump(), "tech_result": tech.model_dump()},
        ensure_ascii=False,
    )
    data = await eap_or_fallback(
        "judge",
        f"系統計算之基礎分:{base} 分({note})。waterfall 第一筆請直接填入此數值。\n"
        f"以下是財務與技術兩位 Agent 的完整報告,請交叉質詢並裁決:\n{payload}",
        MOCK.JUDGE, f"交叉質詢-{req.company_id}",
        required=("contradictions", "verdict", "final_score", "waterfall"),
        cache_id=_cid_any(req.company_id, req.company_code), cache_first=True, force=req.force)
    data["agent"] = "judge"
    # 基礎分一律以後端計算值覆寫(模型自算會每次不同);扣分過度時等比縮減,避免負分
    data["waterfall"], data["final_score"] = fix_waterfall(data.get("waterfall", []), base_value=base)
    data["base_note"] = note
    return _with_meta(M.JudgeResult(**data), data)


# ---------- 5.6 產出授信審查報告 PDF ----------
@app.post("/api/report", response_model=M.ReportResult)
async def make_report(req: M.ReportRequest):
    # 檔名安全化:company_id 可能是「code:4105」(冒號在 Windows 為非法檔名字元)
    cid = _cache_id(M.ReviewRequest(company_id=req.company_id, company_name=req.company_name,
                                    company_code=req.company_code))
    safe = "".join(ch for ch in (cid or "case") if ch.isalnum()) or "case"

    # v1.4:未帶 judge_result 時自資料庫補;完全沒有任何素材才擋下
    D = _report_data(cid)
    judge = req.judge_result
    if judge is None and D.get("judge"):
        try:
            judge = M.JudgeResult(**D["judge"])
        except Exception:
            judge = None
    if judge is None and not any(D.get(k) for k in ("finance", "tech", "brief", "extract", "score")):
        err(422, "NO_MATERIAL",
            "此公司尚無任何分析結果,無法產出報告。請先執行 AI 審查會議或拜訪前情資。")

    filename = f"{safe}_{datetime.now():%Y%m%d%H%M%S}.pdf"
    _render_pdf(REPORT_DIR / filename, req, judge, D)
    cache_store.save("report", cid or safe, {
        "filename": filename, "company_name": req.company_name,
        "judge_score": judge.final_score if judge else None,
    }, req.company_name, req_key=filename)
    return {"report_url": f"/reports/{filename}"}


# 報告字型:優先使用標楷體(教育部/微軟 kaiu.ttf),其次專案內建 Noto Sans TC。
# 取得標楷體的兩種方式(擇一即可,系統會自動偵測):
#   1. 把 kaiu.ttf 複製到 backend/fonts/ (跨平台通用,建議正式交付採此法)
#   2. Windows 電腦免設定:系統會自動讀取 C:\Windows\Fonts\kaiu.ttf
_FONT_CANDIDATES = [
    (Path(__file__).parent / "fonts" / "kaiu.ttf", "Kaiu"),
    (Path(__file__).parent / "fonts" / "標楷體.ttf", "Kaiu"),
    (Path("C:/Windows/Fonts/kaiu.ttf"), "Kaiu"),
    (Path("C:/Windows/Fonts/KAIU.TTF"), "Kaiu"),
    (Path("/Library/Fonts/BiauKai.ttf"), "Kaiu"),          # macOS 標楷體
    (Path(__file__).parent / "fonts" / "NotoSansTC-Regular.ttf", "NotoTC"),
]
_font_reported = [False]


def _report_font() -> str:
    """回傳可用的字型名稱,並在首次使用時於 log 標示實際採用者。"""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for path, alias in _FONT_CANDIDATES:
        try:
            if not path.exists():
                continue
            if alias not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(alias, str(path)))
            if not _font_reported[0]:
                note = "" if alias == "Kaiu" else "(未找到標楷體 kaiu.ttf,改用 Noto Sans TC;" \
                                                 "如需標楷體請將 kaiu.ttf 放入 backend/fonts/)"
                print(f"📄 [報告字型] {alias} ← {path} {note}")
                _font_reported[0] = True
            return alias
        except Exception as e:
            print(f"⚠️ [報告字型] {path} 無法載入({type(e).__name__}: {e}),嘗試下一個")
    # 最後備援:Adobe CID
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    if "MSung-Light" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("MSung-Light"))
    return "MSung-Light"


def _report_data(cid: str) -> dict:
    """自快取資料庫組報告素材:各功能取「主要(釘選)優先、否則最新」的一筆。"""
    out = {}
    for kind in ("finance", "tech", "brief", "judge", "extract", "score"):
        k = "pre_brief" if kind == "brief" else kind
        meta = cache_store.load_meta(k, cid)
        if meta:
            out[kind] = meta["payload"]
            out[kind + "_at"] = meta["created_at"]
    return out


def _render_pdf(path: Path, req: M.ReportRequest, judge=None, data: dict | None = None):
    """完整版授信審查報告:封面摘要 → 拜訪前五維雷達與提問單 → 三 Agent 審查歷程
    (財務/技術發現、審查官矛盾點與裁決、評分瀑布)→ 拜訪後萃取與覆評。
    素材來源 = 請求中的裁決結果 + 快取資料庫中該公司各功能的主要/最新紀錄。"""
    import math
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfgen import canvas

    F = _report_font()

    # 色票:內文一律純黑以求清晰;標題用深色系並以疊印加粗
    NAVY, TEAL, AMBER, ROSE = ((0.04, 0.24, 0.37), (0.04, 0.36, 0.34),
                               (0.55, 0.25, 0.0), (0.60, 0.04, 0.15))
    BLACK, LGRAY = (0, 0, 0), (0.92, 0.94, 0.96)
    EMERALD = (0.02, 0.42, 0.30)
    GRAY = BLACK          # 舊呼叫沿用此名,一律改為黑色

    cid = _cache_id(M.ReviewRequest(company_id=req.company_id, company_name=req.company_name,
                                    company_code=req.company_code))
    D = data if data is not None else _report_data(cid)
    j = judge if judge is not None else req.judge_result
    name = req.company_name or _name_of(cid)

    c = canvas.Canvas(str(path), pagesize=A4)
    W, H = A4
    ML, MR, MT, MB = 46, 46, 52, 56
    y = H - MT
    page_no = [1]

    def footer():
        c.setFont(F, 8); c.setFillColorRGB(0, 0, 0)
        c.drawString(ML, 30, f"智貸先鋒 Credit-Lens 授信審查報告 · {name}(code:{cid})")
        c.drawRightString(W - MR, 30, f"第 {page_no[0]} 頁")

    def new_page():
        footer(); c.showPage(); page_no[0] += 1
        nonlocal y; y = H - MT

    def need(h):
        nonlocal y
        if y - h < MB:
            new_page()

    def put(x, yy, text, size, color=(0, 0, 0), bold=False, anchor="l"):
        """輸出文字。bold=True 時以極小位移疊印兩次,模擬粗體(單一 TTF 無 Bold 字面)。"""
        c.setFont(F, size); c.setFillColorRGB(*color)
        draw = {"l": c.drawString, "c": c.drawCentredString, "r": c.drawRightString}[anchor]
        draw(x, yy, text)
        if bold:
            draw(x + 0.35, yy, text)
            draw(x + 0.18, yy + 0.18, text)

    def wrap(text, size, width):
        out, line = [], ""
        for ch in str(text):
            if ch == "\n":
                out.append(line); line = ""; continue
            if pdfmetrics.stringWidth(line + ch, F, size) > width:
                out.append(line); line = ch
            else:
                line += ch
        if line:
            out.append(line)
        return out or [""]

    def para(text, size=9.5, color=(0, 0, 0), lh=None, indent=0, width=None, bold=False):
        nonlocal y
        lh = lh or size + 4.5
        width = width or (W - ML - MR - indent)
        for ln in wrap(text, size, width):
            need(lh)
            put(ML + indent, y - size, ln, size, color, bold)
            y -= lh

    def section(title):
        nonlocal y
        need(34)
        y -= 8
        c.setFillColorRGB(*NAVY); c.rect(ML, y - 16, 4, 15, fill=1, stroke=0)
        put(ML + 10, y - 13.5, title, 13, NAVY, bold=True)
        y -= 25

    def sub(title, color=NAVY):
        nonlocal y
        need(22)
        put(ML, y - 11, title, 10.5, color, bold=True)
        y -= 18

    def gap(h=8):
        nonlocal y
        y -= h

    # ================= 封面摘要 =================
    c.setFillColorRGB(*NAVY); c.rect(0, H - 8, W, 8, fill=1, stroke=0)
    put(ML, y - 18, "授信審查報告", 20, NAVY, bold=True); y -= 27
    put(ML, y - 11, f"智貸先鋒 Credit-Lens · 產出時間 {datetime.now():%Y-%m-%d %H:%M}", 10.5, BLACK)
    y -= 26
    # 公司資訊卡 + 分數卡
    card_h = 62
    c.setFillColorRGB(*LGRAY); c.rect(ML, y - card_h, W - ML - MR, card_h, fill=1, stroke=0)
    c.setFillColorRGB(*NAVY); c.rect(ML, y - card_h, 3.5, card_h, fill=1, stroke=0)
    put(ML + 14, y - 24, name, 15, BLACK, bold=True)
    c.setFont(F, 9.5); c.setFillColorRGB(*BLACK)
    c.drawString(ML + 14, y - 42, f"證券代號 {cid}" + (f" · 統一編號 {req.company_id}" if len(req.company_id) == 8 and req.company_id.isdigit() else ""))
    post = D.get("score")
    box_w = 108
    bx = W - MR - box_w
    c.setFillColorRGB(*NAVY); c.rect(bx, y - card_h, box_w, card_h, fill=1, stroke=0)
    if post:
        label, score_v = "拜訪後綜合評分", post["final_score"]
    elif j:
        label, score_v = "審查裁決評分", j.final_score
    else:
        fin_s, tech_s = (D.get("finance") or {}).get("score"), (D.get("tech") or {}).get("score")
        if fin_s is not None and tech_s is not None:
            label, score_v = "Agent 加權評分", round(fin_s * 0.6 + tech_s * 0.4)
        elif fin_s is not None:
            label, score_v = "財務分析評分", fin_s
        else:
            label, score_v = "尚未評分", "—"
    put(bx + box_w / 2, y - 16, label, 8.5, (1, 1, 1), bold=True, anchor="c")
    put(bx + box_w / 2, y - 46, str(score_v), 26, (1, 1, 1), bold=True, anchor="c")
    y -= card_h + 6
    if post and j:
        para(f"裁決基準分 {j.final_score} 分 → 拜訪後覆評 {post['final_score']} 分。", 9, BLACK)
    elif not j:
        para("本報告尚未經 AI 審查會議裁決,以下為現有分析結果之彙整。", 9, BLACK)
    gap(4)

    # ================= 一、拜訪前情資 =================
    brief = D.get("brief")
    if brief and brief.get("radar"):
        section("一、拜訪前情資:五維護城河雷達")
        radar = brief["radar"]
        # ---- 雷達圖(左)+ 維度表(右) ----
        R = 66; cx = ML + R + 26
        chart_h = R * 2 + 34
        need(chart_h)
        cy = y - R - 14
        n = len(radar)
        def pt(i, val, rr=R):
            ang = -math.pi / 2 + i * 2 * math.pi / n
            return cx + math.cos(ang) * rr * val / 100, cy - math.sin(ang) * rr * val / 100 * -1 if False else cy + math.sin(ang) * (-1) * rr * val / 100
        def pt2(i, val):
            ang = -math.pi / 2 + i * 2 * math.pi / n
            return cx + math.cos(ang) * R * val / 100, cy - math.sin(ang) * R * val / 100
        # 網格
        c.setLineWidth(0.5)
        for ring in (20, 40, 60, 80, 100):
            c.setStrokeColorRGB(0.85, 0.87, 0.9)
            pts = [pt2(i, ring) for i in range(n)]
            pth = c.beginPath(); pth.moveTo(*pts[0])
            for q in pts[1:]:
                pth.lineTo(*q)
            pth.close(); c.drawPath(pth, stroke=1, fill=0)
        for i in range(n):
            c.setStrokeColorRGB(0.85, 0.87, 0.9)
            c.line(cx, cy, *pt2(i, 100))
        # 同業基準(虛線)
        c.setDash(3, 2); c.setStrokeColorRGB(*GRAY)
        pts = [pt2(i, d.get("benchmark", 0)) for i, d in enumerate(radar)]
        pth = c.beginPath(); pth.moveTo(*pts[0])
        for q in pts[1:]:
            pth.lineTo(*q)
        pth.close(); c.drawPath(pth, stroke=1, fill=0)
        c.setDash()
        # 本公司分數多邊形:改用「預先混色」的淡藍實色,而非 alpha 透明度。
        # ReportLab 的 fill alpha 是畫布層級的狀態,設定後會殘留到之後所有繪製
        # (包含文字),先前即因此讓整頁文字帶 18% 透明看似灰色。實色無此副作用。
        c.setFillColorRGB(0.828, 0.872, 0.897)   # NAVY 以 18% 比例混白的等效色
        c.setStrokeColorRGB(*NAVY); c.setLineWidth(1.4)
        pts = [pt2(i, d.get("score", 0)) for i, d in enumerate(radar)]
        pth = c.beginPath(); pth.moveTo(*pts[0])
        for q in pts[1:]:
            pth.lineTo(*q)
        pth.close(); c.drawPath(pth, stroke=1, fill=1)
        # 維度標籤
        for i, d in enumerate(radar):
            x, yy = pt2(i, 122)
            put(x, yy - 3, f"{d.get('label','')} {d.get('score','')}", 8.5, BLACK, bold=True, anchor="c")
        # 右側表:分數/基準
        tx = cx + R + 46
        ty = y - 10
        put(tx, ty, "維度", 8.5, BLACK, bold=True)
        put(tx + 78, ty, "本公司", 8.5, BLACK, bold=True)
        put(tx + 124, ty, "同業基準", 8.5, BLACK, bold=True)
        ty -= 13
        for d in radar:
            put(tx, ty, d.get("label", ""), 9, BLACK)
            put(tx + 84, ty, str(d.get("score", "")), 9, NAVY, bold=True)
            put(tx + 134, ty, str(d.get("benchmark", "")), 9, BLACK)
            ty -= 13
        put(tx, ty - 2, "實線=本公司,虛線=同業基準", 7.5, BLACK)
        y -= chart_h
        # 各維評分理由
        for d in radar:
            need(16)
            para(f"◆ {d.get('label','')}({d.get('score','')} 分):{d.get('reason','')}", 9)
            if d.get("cites"):
                para("來源:" + "、".join(d["cites"]), 8, GRAY, indent=12)
        gap(4)
        if brief.get("questions"):
            sub("防禦提問單(拜訪時使用)")
            for q in brief["questions"]:
                para(f"Q{q.get('id','')}【{q.get('dim','')}】{q.get('q','')}", 9)
                para(f"出題依據:{q.get('why','')}", 8, GRAY, indent=12)
            gap(4)

    # ================= 二、AI 審查會議歷程 =================
    section("二、AI 審查會議:三 Agent 分析歷程")
    if not (D.get("finance") or D.get("tech") or j):
        para("本公司尚無 Agent 分析紀錄。", 9)

    def agent_block(title, data, color):
        if not data:
            sub(title, color); para("(本次未產出或無既存紀錄)", 9, GRAY); gap(4); return
        sub(f"{title} — 評分 {data.get('score','—')} 分", color)
        for f in data.get("findings", []):
            conf = f.get("confidence")
            tail = f"(信心 {conf:.2f})" if isinstance(conf, (int, float)) else ""
            para(f"• {f.get('text','')}{tail}", 9)
            para(f"來源:{f.get('cite','')}", 8, GRAY, indent=12)
        gap(6)

    agent_block("財務分析 Agent", D.get("finance"), AMBER)
    agent_block("技術情報 Agent", D.get("tech"), TEAL)

    if j:
        sub("風險審查官(交叉質詢與裁決)", ROSE)
        if j.contradictions:
            for x in j.contradictions:
                sev = {"high": "高", "medium": "中", "low": "低"}.get(x.severity, x.severity)
                para(f"▣ 矛盾點【嚴重度 {sev}】{x.title}", 9, ROSE)
                para(x.detail, 9, indent=12)
        else:
            para("• 兩位 Agent 結論無重大矛盾。", 9)
        gap(2)
        para(f"裁決:{j.verdict}", 9.5)
        gap(6)
    else:
        sub("風險審查官(交叉質詢與裁決)", ROSE)
        para("尚未召開 AI 審查會議,本節從缺。可於案件頁「AI 審查會議」執行後重新產出報告。", 9)
        gap(6)

    def wf_get(w, key, default=None):
        """瀑布項可能是 Pydantic 物件(請求帶入)或 dict(快取取出),統一取值。"""
        if isinstance(w, dict):
            return w.get(key, default)
        return getattr(w, key, default)

    def waterfall_chart(title, wf, final):
        nonlocal y
        sub(title)
        rows = len(wf) + 1
        need(rows * 16 + 8)
        vals = [abs(int(wf_get(w, "value", 0))) for w in wf] + [int(final), 60]
        # 累計值也可能超過單項最大,取瀑布累計峰值
        cum_peak, cum_t = 0, 0
        for w in wf:
            v = int(wf_get(w, "value", 0))
            cum_t = v if wf_get(w, "type") == "base" else cum_t + v
            cum_peak = max(cum_peak, cum_t)
        maxv = max(*vals, cum_peak)
        scale = 200 / max(maxv, 1)
        bx = ML + 118
        cum = 0
        for w in wf:
            t = wf_get(w, "type")
            v = int(wf_get(w, "value", 0))
            lbl = wf_get(w, "label", "")
            need(16)
            put(bx - 8, y - 10, lbl, 8.5, BLACK, anchor="r")
            if t == "base":
                x0, wd, col, cum = bx, v * scale, NAVY, v
            elif v >= 0:
                x0, wd, col = bx + cum * scale, v * scale, EMERALD; cum += v
            else:
                cum += v
                x0, wd, col = bx + cum * scale, -v * scale, ROSE
            c.setFillColorRGB(*col); c.rect(x0, y - 12, max(wd, 1.2), 9, fill=1, stroke=0)
            put(bx + max(cum, (cum - v) if v < 0 else cum) * scale + 6, y - 10.5,
                f"{'+' if t != 'base' and v > 0 else ''}{v}", 8.5, col, bold=True)
            y -= 16
        need(16)
        put(bx - 8, y - 10, "最終分數", 9, NAVY, bold=True, anchor="r")
        c.setFillColorRGB(*NAVY); c.rect(bx, y - 12, final * scale, 9, fill=1, stroke=0)
        put(bx + final * scale + 6, y - 10.5, str(final), 9, NAVY, bold=True)
        y -= 20

    if j:
        waterfall_chart("裁決評分瀑布", list(j.waterfall), j.final_score)

    # ================= 三、拜訪後 =================
    ext = D.get("extract")
    if ext or post:
        section("三、拜訪後:面談結果與覆評")
    if ext:
        if ext.get("commitments"):
            sub("客戶承諾事項")
            for m in ext["commitments"]:
                para(f"• {m.get('item','')}(承諾人:{m.get('owner','—')},期限 {m.get('due','—')})", 9)
        if ext.get("responses"):
            sub("風險回應判定")
            VD = {"resolved": "已化解", "partial": "部分化解", "unresolved": "未化解"}
            for r_ in ext["responses"]:
                para(f"• {r_.get('risk','')}:{r_.get('summary','')}【{VD.get(r_.get('verdict'), r_.get('verdict',''))}】", 9)
        if ext.get("new_risks"):
            sub("面談新發現風險", ROSE)
            for r_ in ext["new_risks"]:
                para(f"• {r_.get('text','')}", 9, ROSE)
        gap(4)
    if post:
        waterfall_chart("拜訪後評分瀑布(以裁決分為基準)", post.get("waterfall", []), post["final_score"])
        para(f"審查官建議:{post.get('recommendation','')}", 9.5)

    gap(8)
    para("本報告由多代理 AI 系統產生:每筆發現皆附引用來源,無來源內容已自動剔除;"
         "評分瀑布經後端數學驗算。AI 輸出僅供授信人員參考,最終決策仍由審查人員為之。", 8, GRAY)

    footer()
    c.showPage()
    c.save()


# ---------- 5.7 拜訪前情資 ----------
@app.post("/api/pre/brief")
async def pre_brief(req: M.ReviewRequest):
    if MOCK_MODE:
        return MOCK.BRIEF
    data = await eap_or_fallback(
        "pre_brief",
        f"目標企業:{_company_ref(req)}。請依 EAP 知識庫(以 code 代號檢索)產出五維雷達與防禦提問單。",
        MOCK.BRIEF, f"拜訪前情資-{req.company_name or req.company_id}",
        required=("radar", "questions"),
        cache_id=_cache_id(req), cache_name=req.company_name,
        cache_first=True, force=req.force)
    return _with_meta(M.BriefResult(**data), data)


# ---------- 5.8 拜訪中即時判定 ----------
@app.post("/api/interview/assess", response_model=M.AssessResult)
async def interview_assess(req: M.AssessRequest):
    if MOCK_MODE:
        return MOCK.ASSESS
    data = await eap_or_fallback(
        "assess", f"風險提問:{req.question}\n客戶回答:{req.answer}",
        MOCK.ASSESS, f"面談判定-{req.company_id}",
        required=("verdict", "reason", "follow"),
        cache_id=_cid_any(req.company_id, req.company_code), cache_key=str(req.question_id))
    return M.AssessResult(**data)


# ---------- 5.9 會議紀錄結構化萃取 ----------
@app.post("/api/postvisit/extract", response_model=M.ExtractResult)
async def postvisit_extract(req: M.ExtractRequest):
    if MOCK_MODE:
        return MOCK.EXTRACT
    data = await eap_or_fallback(
        "extract", f"會議紀錄全文:\n{req.notes}",
        MOCK.EXTRACT, f"會議萃取-{req.company_id}",
        cache_id=_cid_any(req.company_id, req.company_code),
        required=("commitments", "responses", "new_risks"))
    return M.ExtractResult(**data)


# ---------- 5.10 拜訪後評分 ----------
@app.post("/api/postvisit/score", response_model=M.PostScoreResult)
async def postvisit_score(req: M.PostScoreRequest):
    if MOCK_MODE:
        return MOCK.POST_SCORE
    payload = json.dumps(req.extract_result.model_dump(), ensure_ascii=False)
    data = await eap_or_fallback(
        "score", f"拜訪前基準分:{req.base_score}\n萃取結果:\n{payload}",
        MOCK.POST_SCORE, f"拜訪後評分-{req.company_id}",
        cache_id=_cid_any(req.company_id, req.company_code),
        required=("final_score", "waterfall"))
    data["waterfall"], data["final_score"] = fix_waterfall(data.get("waterfall", []), base_value=req.base_score)
    return M.PostScoreResult(**data)


# ---------- 5.11 情資查詢(v1.2 新增) ----------
@app.post("/api/intel/lookup")
async def intel_lookup(req: M.IntelRequest):
    key = req.query.strip()
    builtin = MOCK.INTEL.get(key) or next(
        (v for v in MOCK.INTEL.values() if key and key.replace(" ", "") in v["name"].replace(" ", "")), None
    )

    # 未開啟開放資料 → 只回內建示範資料(Demo 穩定)
    if not OPEN_DATA:
        if not builtin:
            err(404, "COMPANY_NOT_FOUND",
                "查無此公司(目前 OPEN_DATA=false,僅能查內建示範公司;如需查真實企業請於 .env 設 OPEN_DATA=true 並重啟後端)")
        return builtin

    # ---- OPEN_DATA=true:逐源查詢,任一來源有結果就回傳 ----
    is_ban = key.isdigit() and len(key) == 8
    live = await opendata.fetch_all(key) if is_ban else {"reg": None, "revenue": None}

    # 決定用來查許可證與新聞的公司名(商工登記 > 內建 > 使用者輸入)
    name = (live["reg"] or {}).get("name") or (builtin or {}).get("name") or ("" if is_ban else key)

    lic = tfda.search_company(ban=key if is_ban else "", name=name)
    news = await opendata.fetch_news(name)

    hits = {
        "商工登記": bool(live["reg"]),
        "TWSE營收": bool(live["revenue"]),
        "藥品許可證": bool(lic and lic["count"]),
        "GDELT新聞": bool(news),
        "內建資料": bool(builtin),
    }
    print(f"[情資查詢] {key} → " + " ".join(f"{k}={'O' if v else 'X'}" for k, v in hits.items()))

    if not any(hits.values()):
        err(404, "COMPANY_NOT_FOUND",
            "四個資料源皆查無此公司。請確認輸入的是 8 碼統一編號,或改以公司全名查詢。")

    base = dict(builtin) if builtin else {
        "id": key if is_ban else "", "name": name, "industry": "—",
        "reg": {}, "revenue": [], "lawsuits": [], "fines": [],
        "licenses": None, "news": [], "graph": None,
    }
    if live["reg"]:
        base["reg"] = {**live["reg"]}
        base["name"] = base["name"] or live["reg"].get("name", "")
        base["reg"].pop("name", None)
        base["reg"]["_source"] = "live"
    if live["revenue"]:
        base["revenue"] = live["revenue"]
    if lic and lic["count"]:
        base["licenses"] = lic
    if news:
        base["news"] = news
        base["news_source"] = "live"

    if is_ban:
        base["id"] = key
    return base


# ---------- 5.12 報告列表(v1.3:改讀真實產出物) ----------
def _roc(dt: datetime) -> str:
    return f"{dt.year - 1911}-{dt.month:02d}-{dt.day:02d}"


def _name_of(cid: str, hint: str = "") -> str:
    """公司名解析:報告中繼資料 → EAP 公司清單快取 → 市場資料 → 圖譜匯出 → 代號本身。"""
    if hint:
        return hint
    try:
        if EAP_UNIVERSE_CACHE.exists():
            for c in json.loads(EAP_UNIVERSE_CACHE.read_text(encoding="utf-8")).get("companies", []):
                if c.get("code") == cid and c.get("name"):
                    return c["name"]
    except (json.JSONDecodeError, OSError):
        pass
    sig = market.signal(cid) if market.available() else None
    if sig and sig.get("company_name"):
        return sig["company_name"]
    hit = eap_export.find(code=cid)
    if hit and hit.get("name"):
        return hit["name"]
    return cid


@app.post("/api/reports/list")
async def reports_list(req: M.ReportListRequest):
    if MOCK_MODE:
        return {"reports": MOCK.REPORTS}

    # 1) 掃描 reports/ 的真實 PDF;檔名格式 {safe_id}_{YYYYmmddHHMMSS}.pdf
    files = sorted(REPORT_DIR.glob("*.pdf"), key=lambda p: p.name, reverse=True)

    # 2) 由快取資料庫備妥各公司的最新分數與報告中繼資料
    meta_by_file = {}
    for row in cache_store.listing("report", limit=500):
        meta_by_file[row["req_key"]] = row
    post_score = {x["company_id"]: x["payload"].get("final_score") for x in cache_store.latest_all("score")}
    judge_score = {x["company_id"]: x["payload"].get("final_score") for x in cache_store.latest_all("judge")}

    # 3) 組清單:分數優先序 = 拜訪後評分 > 裁決分 > 產出當下分數
    ver_count: dict = {}
    items = []
    for f in files:
        stem = f.stem
        cid, _, ts = stem.rpartition("_")
        if not cid:
            cid, ts = stem, ""
        try:
            dt = datetime.strptime(ts, "%Y%m%d%H%M%S")
        except ValueError:
            dt = datetime.fromtimestamp(f.stat().st_mtime)
        meta = meta_by_file.get(f.name)
        meta_payload = {}
        if meta:
            full = cache_store.load("report", meta["company_id"], f.name)
            meta_payload = full or {}
            cid = meta["company_id"] or cid
        score, src = None, ""
        if cid in post_score and post_score[cid] is not None:
            score, src = post_score[cid], "拜訪後評分"
        elif cid in judge_score and judge_score[cid] is not None:
            score, src = judge_score[cid], "審查裁決"
        elif meta_payload.get("judge_score") is not None:
            score, src = meta_payload["judge_score"], "產出當下"
        star_row = cache_store.load("report_star", cid, f.name)
        items.append({
            "date": _roc(dt), "time": dt.strftime("%H:%M"),
            "company": _name_of(cid, meta_payload.get("company_name", "")),
            "id": cid, "filename": f.name, "report_url": f"/reports/{f.name}",
            "score": score, "score_src": src,
            "starred": bool((star_row or {}).get("starred")), "_dt": dt,
        })
    # 版次:同公司由舊到新編第 N 版
    for it in sorted(items, key=lambda x: x["_dt"]):
        ver_count[it["id"]] = ver_count.get(it["id"], 0) + 1
        it["version"] = f"第 {ver_count[it['id']]} 版"
    for it in items:
        it.pop("_dt")

    return {"reports": items, "source": "live"}


# ---------- v1.4 報告星號標記 ----------
@app.post("/api/reports/star")
async def reports_star(body: dict):
    filename = str(body.get("filename", "")).strip()
    starred = bool(body.get("starred"))
    cid = str(body.get("id", "")).strip()
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        err(422, "INVALID_REQUEST", "filename 不合法")
    if not (REPORT_DIR / filename).exists():
        err(404, "NOT_FOUND", "報告檔案不存在")
    cache_store.save("report_star", cid or filename, {"starred": starred}, req_key=filename)
    return {"filename": filename, "starred": starred}


# ---------- v1.4 報告刪除 ----------
@app.post("/api/reports/delete")
async def reports_delete(body: dict):
    filename = str(body.get("filename", "")).strip()
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        err(422, "INVALID_REQUEST", "filename 不合法")
    target = (REPORT_DIR / filename).resolve()
    if REPORT_DIR.resolve() not in target.parents:
        err(422, "INVALID_REQUEST", "filename 不合法")
    if not target.exists():
        err(404, "NOT_FOUND", "報告檔案不存在")
    target.unlink()
    return {"deleted": filename}


# ---------- v1.4 會議紀錄檔案上傳(取代語音輸入):txt/md 前端直讀,docx 走此端點 ----------
@app.post("/api/notes/extract_text")
async def notes_extract_text(body: dict):
    """輸入 {filename, content_b64},回傳純文字。docx 以標準庫解壓 word/document.xml,免額外套件。"""
    import base64
    import re as _re
    import zipfile
    import io

    filename = str(body.get("filename", "")).lower()
    try:
        raw = base64.b64decode(str(body.get("content_b64", "")), validate=True)
    except Exception:
        err(422, "INVALID_REQUEST", "content_b64 無法解碼")
    if len(raw) > 5 * 1024 * 1024:
        err(422, "INVALID_REQUEST", "檔案過大(上限 5MB)")

    if filename.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                xml = z.read("word/document.xml").decode("utf-8", "ignore")
        except (zipfile.BadZipFile, KeyError):
            err(422, "INVALID_REQUEST", "docx 檔案無法解析")
        xml = _re.sub(r"</w:p>", "\n", xml)
        text = _re.sub(r"<[^>]+>", "", xml)
        text = _re.sub(r"\n{3,}", "\n\n", text).strip()
    else:  # txt / md / 其他純文字
        for enc in ("utf-8-sig", "utf-8", "big5", "cp950"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                text = ""
        if not text.strip():
            err(422, "INVALID_REQUEST", "無法以常見編碼讀取此檔,請確認為 txt/md/docx 文字檔")
    if not text.strip():
        err(422, "INVALID_REQUEST", "檔案內容為空")
    return {"text": text.strip(), "chars": len(text.strip())}


# ---------- 股價市場訊號模組 §6.2 單一企業 ----------
@app.post("/api/market/signal", response_model=M.MarketSignalResult)
async def market_signal(req: M.MarketSignalRequest):
    if not market.available():
        err(502, "DATA_SOURCE_ERROR", "股價資料檔不存在(backend/data/market_signal.json)")
    data = market.signal(req.company_id, req.company_name)
    if not data:
        err(404, "COMPANY_NOT_FOUND", f"查無證券代號 {req.company_id} 之股價資料")
    # 數學一致性驗算(說明書 §5.2):基準 50 + 各增減 = market_score
    wf = data["waterfall"]
    if wf and data["market_score"] is not None:
        total = wf[0]["value"] + sum(w["value"] for w in wf[1:])
        if total != data["market_score"]:
            print(f"⚠️ [市場訊號] {req.company_id} 瀑布圖不一致({total} != {data['market_score']}),已以瀑布圖為準")
            data["market_score"] = total
    return data


# ---------- 股價市場訊號模組 §6.3 同業排行 ----------
@app.post("/api/market/universe")
async def market_universe(req: M.MarketUniverseRequest):
    if not market.available():
        err(502, "DATA_SOURCE_ERROR", "股價資料檔不存在(backend/data/market_signal.json)")
    return market.universe(req.industry)


# ---------- 公司名模糊查統編(情資查詢的輔助工具)----------
@app.post("/api/company/search")
async def company_search(req: M.IntelRequest):
    """以公司名稱關鍵字查統一編號。
    優先使用 GCIS 官方名稱查詢(涵蓋全國登記公司),再補上本地三個來源的證券代號。"""
    kw = req.query.strip().replace(" ", "")
    if not kw:
        return {"companies": [], "keyword": kw}

    out, by_ban, by_name = [], {}, {}

    def add(name, ban="", code="", source="", status=""):
        if not name and not ban:
            return
        key = ban or f"name:{name}"
        if key in by_ban:                     # 已存在則補齊缺漏欄位
            hit = by_ban[key]
            hit["code"] = hit["code"] or code
            hit["name"] = hit["name"] or name
            if source and source not in hit["source"]:
                hit["source"] += f" · {source}"
            return
        rec = {"name": name, "ban": ban, "code": code, "source": source, "status": status}
        by_ban[key] = rec
        if name:
            by_name.setdefault(name.replace(" ", ""), rec)
        out.append(rec)

    # 1) GCIS 官方名稱查詢(權威來源,涵蓋全國)
    try:
        for c in await opendata.search_company_by_name(kw):
            add(c["name"], ban=c["ban"], source="商工登記", status=c.get("status", ""))
    except Exception as e:
        print(f"⚠️ [查統編] GCIS 名稱查詢失敗:{type(e).__name__}: {e}")

    # 2) 市場訊號母體(補證券代號)
    for c in (market.universe() or {"companies": []})["companies"]:
        nm = (c.get("company_name") or "").replace(" ", "")
        if kw in nm:
            existing = next((r for r in out if nm and nm in r["name"].replace(" ", "")), None)
            if existing:
                existing["code"] = existing["code"] or c.get("company_id") or ""
                if "市場訊號" not in existing["source"]:
                    existing["source"] += " · 市場訊號"
            else:
                add(c.get("company_name"), ban=c.get("ban") or "",
                    code=c.get("company_id") or "", source="市場訊號母體")

    # 3) 上市櫃代號↔統編對照表
    for code, info in opendata.code_ban_map().items():
        nm = (info.get("name") or "").replace(" ", "")
        if kw in nm:
            add(info.get("name"), ban=info.get("ban") or "", code=code,
                source=f"{info.get('market', '')}公司")

    # 4) EAP 知識圖譜
    for c in eap_export.companies():
        nm = (c.get("name") or "").replace(" ", "")
        if kw in nm:
            existing = by_name.get(nm)
            if existing:
                existing["code"] = existing["code"] or c.get("code") or ""
                if "EAP" not in existing["source"]:
                    existing["source"] += " · EAP 知識圖譜"
            else:
                add(c.get("name"), code=c.get("code") or "", source="EAP 知識圖譜")

    # 有統編者排前面
    out.sort(key=lambda r: (not r["ban"], r["name"]))
    return {"companies": out[:25], "keyword": kw}


@app.post("/api/cache/stats")
async def cache_stats():
    return {"mode": CACHE_MODE, **cache_store.stats()}


@app.post("/api/cache/coverage")
async def cache_coverage():
    """每家公司集滿哪些功能——Demo 前一眼看出還缺什麼。"""
    return {"mode": CACHE_MODE, **cache_store.coverage()}


@app.post("/api/cache/list")
async def cache_list(body: dict | None = None):
    b = body or {}
    return {"items": cache_store.listing(b.get("kind", ""), b.get("company_id", ""), int(b.get("limit", 50)))}


@app.post("/api/cache/get")
async def cache_get(body: dict):
    """依 id 取單筆完整紀錄(歷次紀錄面板「載入檢視」用)。"""
    rec = cache_store.get(int(body.get("id", 0)))
    if not rec:
        err(404, "NOT_FOUND", "找不到該筆紀錄")
    return rec


@app.post("/api/cache/pin")
async def cache_pin(body: dict):
    """釘選某一筆:Demo 時該公司該功能固定用這筆(挑表現最好的那次)。"""
    ok = cache_store.pin(body.get("kind", ""), body.get("company_id", ""), int(body.get("id", 0)))
    if not ok:
        err(404, "NOT_FOUND", "找不到該筆紀錄")
    return {"pinned": True}


# ---------- EAP 知識圖譜覆蓋範圍 ----------
@app.post("/api/eap/coverage")
async def eap_coverage():
    return {"available": eap_export.available(), "companies": eap_export.companies()}


# ---------- EAP 知識庫公司清單(案件總覽用)----------
# 以 prompt 請 EAP 列出知識庫全部公司,成功即寫入本地快取;之後直接讀快取(LLM 清點慢且耗額度)。
# body {"refresh": true} 可強制重問一次(知識庫更新後使用)。
EAP_UNIVERSE_CACHE = Path(__file__).parent / "data" / "eap_universe.json"


def _apply_demo_filter(companies: list) -> list:
    """為每家公司標上素材完整度並排序,素材齊全者排前面。

    readiness 等級:3 = 財務與技術皆有實質內容、4 項齊備;2 = 財務為知識庫查無;
    1 = 僅部分素材;0 = 尚未分析。清單一律完整呈現(不刪任何公司),
    只是把可直接展示的排在前面,其餘仍可點進去即時分析或補跑。

    DEMO_COMPANIES 若有設定,則該清單內的公司再優先於其他公司(供現場控制順序)。"""
    ready = cache_store.readiness()
    pri = {c: i for i, c in enumerate(DEMO_COMPANIES)}
    out = []
    for c in companies:
        code = str(c.get("code", ""))
        r = ready.get(code) or {"level": 0, "finance": "", "tech": ""}
        out.append({**c, "readiness": r["level"],
                    "finance_state": r.get("finance", ""), "tech_state": r.get("tech", "")})
    out.sort(key=lambda c: (pri.get(str(c.get("code", "")), 9999),
                            -c["readiness"], str(c.get("code", ""))))
    return out


@app.post("/api/eap/universe")
async def eap_universe(body: dict | None = None):
    refresh = bool((body or {}).get("refresh"))
    if not refresh and EAP_UNIVERSE_CACHE.exists():
        cached = json.loads(EAP_UNIVERSE_CACHE.read_text(encoding="utf-8"))
        return {**cached, "companies": _apply_demo_filter(cached.get("companies", [])), "source": "cache"}

    if MOCK_MODE:
        return {"companies": [], "source": "mock", "fetched_at": ""}
    try:
        data = await ask_agent("universe", "請列出知識庫中全部公司企業的名稱與代號。", "知識庫清點")
    except EapError as e:
        # 問失敗:有舊快取就用舊的,沒有就回空(前端自動退回市場檔清單)
        if EAP_UNIVERSE_CACHE.exists():
            cached = json.loads(EAP_UNIVERSE_CACHE.read_text(encoding="utf-8"))
            return {**cached, "companies": _apply_demo_filter(cached.get("companies", [])),
                    "source": "stale_cache", "error": e.message}
        return {"companies": [], "source": "error", "error": e.message}

    rows = data.get("companies") if isinstance(data, dict) else None
    companies = []
    seen = set()
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        code = norm_code(r.get("code"))
        name = str(r.get("name", "")).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        companies.append({"code": code, "name": name,
                          "ban": opendata.resolve_ban_by_code(code) if code else None})
    if not companies:
        return {"companies": [], "source": "empty",
                "error": "EAP 回覆中沒有可解析的公司清單"}

    out = {"companies": companies, "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    EAP_UNIVERSE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    EAP_UNIVERSE_CACHE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return {**out, "companies": _apply_demo_filter(out["companies"]), "source": "live"}


# ---------- 市場訊號 × EAP 財報 交叉解讀 ----------
# 量化分數維持離線確定性計算(可重現);LLM 只負責把指標拿去跟知識庫財報交叉判讀產生文字。
@app.post("/api/market/eap_read")
async def market_eap_read(req: M.MarketSignalRequest):
    sig = market.signal(req.company_id, req.company_name)
    if not sig:
        err(404, "COMPANY_NOT_FOUND", f"查無證券代號 {req.company_id} 之股價資料")
    m = sig["metrics"]
    facts = (
        f"目標企業:{sig['company_name']}(code:{sig['company_id']})\n"
        f"【系統離線計算之市場指標(直接引用)】\n"
        f"市場評分 {sig['market_score']} 分(基準50)、風險等級 {sig['level']}\n"
        f"年化波動度 {m.get('vol_full_pct')}%、最大回撤 {m.get('mdd_pct')}%、"
        f"近一年報酬 {m.get('mom_1y_pct')}%、市值 {m.get('mktcap')} 百萬元\n"
        f"請到知識庫檢索該公司(以 code 代號檢索)財報,交叉判讀後輸出 JSON。"
    )
    data = await eap_or_fallback(
        "market_read", facts,
        {"summary": sig["reading"]["summary"], "recommendation": sig["reading"]["recommendation"],
         "cites": [], "_degraded": True},
        f"市場交叉解讀-{sig['company_name']}",
        required=("summary", "recommendation"),
        cache_id=sig["company_id"], cache_name=sig["company_name"],
        cache_first=True, force=req.force)
    data.setdefault("cites", [])
    return data


# ---------- 知識問答:直接與 EAP 平台模型對話 ----------
# 與 5.3–5.10 的差別:不套 Agent 契約、不強制 JSON,回傳平台原始文字。
# chat_id 由前端保管並回送,同一串對話沿用同一個聊天室(平台端才有上下文)。
@app.post("/api/eap/chat")
async def eap_chat(req: M.EapChatRequest):
    if MOCK_MODE:
        return {"chat_id": "mock-session", "new_session": not req.chat_id,
                "reply": "【示範資料】目前為 MOCK_MODE,本回覆非 EAP 平台實際輸出。"
                         "請於 backend/.env 設定 MOCK_MODE=false 並填入有效的 EAP_TOKEN。"}
    try:
        return await eap_chat_raw(req.message, req.chat_id.strip(), req.session_name or "知識問答")
    except EapError as e:
        err(e.status, e.code, e.message)


# ---------- EAP 連線狀態(知識問答頁頁首顯示)----------
@app.post("/api/eap/status")
async def eap_status():
    st = eap_status_info()
    st["mock_mode"] = MOCK_MODE
    st["graph_companies"] = len(eap_export.companies())
    return st


@app.get("/")
async def root():
    return {"service": "Credit-Lens API", "mock_mode": MOCK_MODE, "fallback_on_error": FALLBACK_ON_ERROR,
            "eap_graph_companies": len(eap_export.companies()), "docs": "/docs"}