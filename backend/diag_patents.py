"""diag_patents.py — 專利檢索逐層診斷
用法:
  python diag_patents.py 基亞生物科技股份有限公司
  python diag_patents.py 基亞生物科技股份有限公司 --raw     連原始回應一併印出

會逐層檢查並指出「卡在哪一層」:
  L1 名稱處理    公司全名 → 檢索用簡稱 / 核心短名
  L2 網路連通    能不能連到 patents.google.com
  L3 端點回應    xhr/query 回什麼狀態碼、內容型別
  L4 結構解析    回應能不能解析出件數與清單
  L5 查詢命中    三種查法(全文簡稱 / 全文短名 / 申請人欄位)各自幾筆
  L6 TIPO API    有無設定驗證碼、呼叫結果
"""
import asyncio
import json
import sys
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv

load_dotenv()
import patents  # noqa: E402

OK, NG, SKIP, WARN = "\033[92m通過\033[0m", "\033[91m失敗\033[0m", "\033[93m略過\033[0m", "\033[93m注意\033[0m"
RAW = "--raw" in sys.argv


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    name = args[0] if args else "基亞生物科技股份有限公司"
    print(f"\n=== 專利檢索診斷:{name} ===\n")

    # ---------- L1 名稱處理 ----------
    short = patents._clean_name(name)
    core = patents._core_name(short)
    print(f"[L1] 名稱處理    {OK}")
    print(f"     公司全名 : {name}")
    print(f"     檢索簡稱 : {short}")
    print(f"     核心短名 : {core}")
    if len(core) <= 1:
        print(f"     {WARN} 核心短名過短,可能檢索過寬。建議於畫面上手動輸入名稱。")

    # ---------- L2 網路連通 ----------
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as c:
            r = await c.get("https://patents.google.com/", headers=patents._G_HEADERS)
        print(f"[L2] 網路連通    {OK}  patents.google.com HTTP {r.status_code}")
    except httpx.HTTPError as e:
        print(f"[L2] 網路連通    {NG}  {type(e).__name__}: {e}")
        print("     → 公司網路或防火牆可能擋住 Google。請改用手機熱點測試,")
        print("       或於畫面上改用一鍵檢索連結(瀏覽器直接開,不經後端)。")
        return

    # ---------- L3 + L4 + L5 三種查法逐一實測 ----------
    attempts = [(short, "q", "全文檢索·簡稱"), (core, "q", "全文檢索·核心短名"),
                (short, "assignee", "申請人欄位·簡稱"), (core, "assignee", "申請人欄位·核心短名")]
    hit_any = False
    for term, mode, label in attempts:
        params = {"num": 10}
        params["q" if mode == "q" else "assignee"] = f'"{term}"' if mode == "q" else term
        inner = urlencode(params)
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as c:
                r = await c.get(patents.GOOGLE_XHR_URL, params={"url": inner, "exp": ""},
                                headers=patents._G_HEADERS)
        except httpx.HTTPError as e:
            print(f"[L5] {label:<20} {NG}  連線失敗 {type(e).__name__}")
            continue

        ctype = r.headers.get("content-type", "")
        if r.status_code != 200:
            print(f"[L3] {label:<20} {NG}  HTTP {r.status_code} ({ctype[:30]})")
            print(f"     回應前 200 字:{r.text[:200]}")
            if r.status_code in (403, 429):
                print("     → Google 判定為自動化流量而擋下。這是端點本身的限制,")
                print("       畫面上的一鍵檢索連結仍可正常使用(由瀏覽器直接開啟)。")
            continue

        try:
            data = r.json()
        except ValueError:
            print(f"[L3] {label:<20} {NG}  回應非 JSON({ctype[:30]})")
            print(f"     前 200 字:{r.text[:200]}")
            continue

        out = patents._parse_google(data, 10)
        if out is None:
            print(f"[L4] {label:<20} {NG}  結構無法解析")
            print(f"     頂層鍵:{list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
            if RAW:
                print(json.dumps(data, ensure_ascii=False)[:1500])
            else:
                print("     → 加 --raw 參數可印出完整回應,貼給開發者即可對齊欄位。")
            continue

        n = out.get("count", 0)
        mark = OK if n else WARN
        print(f"[L5] {label:<20} {mark}  {n} 件")
        for p in out.get("recent", [])[:3]:
            print(f"        · {p['date']:>12}  {p['no']:<16} {p['title'][:34]}")
        if n:
            hit_any = True

    if not hit_any:
        print(f"\n     {WARN} 四種查法皆 0 筆。最可能的原因(依機率排序):")
        print("       1. 該公司專利以英文名登記(台灣公司在 Google Patents 多為羅馬拼音)")
        print("          → 於情資查詢頁的「改用其他名稱查」欄位輸入英文名再試")
        print("       2. 該公司確實沒有專利(生技新藥公司常以技術移轉或授權方式運作)")
        print("       3. 端點格式已變動 → 用 --raw 印出回應貼給開發者")

    # ---------- L6 TIPO GPSS API ----------
    print()
    if not patents.api_enabled():
        print(f"[L6] TIPO GPSS   {SKIP} 未設定 TIPO_API_KEY(僅提供檢索連結)")
        print("     免費申請:https://gpss.tipo.gov.tw/ → API → 使用說明 → 驗證碼線上申請")
        print("     核發後填入 backend/.env 的 TIPO_API_KEY,即可自動取得專利件數與清單。")
    else:
        url = patents.tipo_api_url(name)
        print(f"[L6] 組出的 API 網址(可直接貼瀏覽器比對):")
        print(f"     {url}")
        t = await patents.fetch_tipo(name)
        if t:
            print(f"[L6] TIPO GPSS   {OK}  {t['count']} 件"
                  f"(以「{t.get('_term','')}」查得)")
            for pt in t.get("recent", [])[:3]:
                print(f"        · {pt['date']:>12}  {pt['no']:<16} {pt['title'][:34]}")
        else:
            print(f"[L6] TIPO GPSS   {NG}  {patents.LAST_ERROR.get('tipo', '無回傳')}")
            print("     排查順序:")
            print("       1. 驗證碼是否已通過審核(未核准會回權限訊息)")
            print("       2. 把上面那條網址貼進瀏覽器,看 GPSS 直接回什麼")
            print("       3. 到 GPSS 網站的 API → 網址工具,用相同條件產生一次網址,")
            print("          與上面比對參數差異(官方若調整參數名,以工具產生者為準)")

    # ---------- 產出可直接點的連結 ----------
    L = patents.build_links(name)
    print("\n--- 以下連結可直接貼到瀏覽器驗證(不經後端,最能確認資料是否真的存在)---")
    print(f"  Google 全文(簡稱):{L['google_url']}")
    if L.get("google_alt_url"):
        print(f"  Google 全文(短名):{L['google_alt_url']}")
    print(f"  TIPO 檢索式(需貼入檢索框):{L['tipo_expr']}")
    print(f"  TIPO 檢索頁:{L['tipo_url']}")
    if L.get("tipo_api_url"):
        print(f"  TIPO API  :{L['tipo_api_url']}")
    print()


asyncio.run(main())