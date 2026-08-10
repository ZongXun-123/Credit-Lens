"""check_sources.py — 一次檢查所有外部資料源是否接得上
用法:python check_sources.py [統一編號]     例:python check_sources.py 22099131

檢查項目(全部免金鑰、免申請):
  1. 經濟部商工登記(data.gcis.nat.gov.tw)
  2. TWSE OpenAPI 月營收(openapi.twse.com.tw)
  3. 食藥署藥品許可證(data.fda.gov.tw,需先跑 prefetch.py)
  4. GDELT 新聞(api.gdeltproject.org)
  5. 精誠 EAP 平台(需 .env 有 EAP_TOKEN)
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

OK = "\033[92m通過\033[0m"
NG = "\033[91m失敗\033[0m"
SKIP = "\033[93m略過\033[0m"
WARN = "\033[93m注意\033[0m"


REQUIRED = {
    "opendata": ["fetch_gcis_registration", "fetch_twse_revenue", "fetch_all", "fetch_news",
                 "build_code_ban_map", "code_ban_map", "resolve_ban_by_code"],
    "tfda": ["download", "search_company"],
    "market": ["signal", "universe", "available"],
    "eap": ["call_chat", "ask_agent"],
}


def integrity_check() -> bool:
    """模組完整性檢查:確認各模組該有的函式都在(防止改檔時誤刪)。"""
    import importlib
    bad = []
    for mod, funcs in REQUIRED.items():
        try:
            m = importlib.import_module(mod)
            bad += [f"{mod}.{f}" for f in funcs if not hasattr(m, f)]
        except ImportError as e:
            bad.append(f"{mod}(無法匯入:{e})")
    if bad:
        print(f"[0] 模組完整性    {NG}  缺少:{', '.join(bad)}")
        print("      → 請重新解壓縮後端檔案,或回報此訊息。\n")
        return False
    print(f"[0] 模組完整性    {OK}  所有必要函式齊備")
    return True


def config_check():
    """設定健檢:抓出 .env 常見寫法問題(行末註解、非 ASCII、Token 未填)。"""
    from envtools import env, env_ascii
    import eap as _eap

    issues = []
    raw_tenant = os.getenv("EAP_TENANT", "") or ""
    if raw_tenant and not raw_tenant.isascii():
        issues.append("EAP_TENANT 讀到中文(.env 把註解寫在同一行),已自動改用 Token 解析")
    token = env("EAP_TOKEN")
    if not token:
        issues.append("EAP_TOKEN 未設定")
    elif not token.startswith("ey"):
        issues.append(f"EAP_TOKEN 格式可疑(開頭 {token[:10]}…)")

    tenant = env_ascii("EAP_TENANT") or (_eap.tenant_from_token(token) if token else "")
    mark = OK if not issues else WARN
    api_url = env("EAP_API_BASE") or "(預設 /api/v1)"
    tenant_txt = tenant or "未解析"
    print(f"[0b] 設定檢查     {mark}  API={api_url} | tenant={tenant_txt}")
    for i in issues:
        print(f"      · {i}")


async def main():
    ban = sys.argv[1] if len(sys.argv) > 1 else "22099131"
    print(f"\n=== Credit-Lens 資料源檢查(統一編號 {ban})===\n")
    integrity_check()
    config_check()
    results = []

    # 1 商工登記
    import opendata
    try:
        reg = await opendata.fetch_gcis_registration(ban)
        if reg:
            print(f"[1] 商工登記      {OK}  {reg.get('name','')} / 資本額 {reg.get('capital','')}")
            results.append(True)
        else:
            print(f"[1] 商工登記      {NG}  {opendata.LAST_ERROR.get('gcis', '查無此統編')}")
            results.append(False)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"[1] 商工登記      {NG}  {msg}")
        # SSL 憑證問題在不同 Python 版本表現不同,直接給出可行的處理方向
        if "CERTIFICATE_VERIFY_FAILED" in msg or "SSL" in msg:
            import ssl as _ssl
            import sys as _sys
            print(f"        → Python {_sys.version.split()[0]} / {_ssl.OPENSSL_VERSION}")
            if "Subject Key Identifier" in msg:
                print("        → 成因:Python 3.13 起預設啟用 VERIFY_X509_STRICT,")
                print("               會拒絕缺少 Subject Key Identifier 的憑證鏈,")
                print("               而政府網站的憑證正好有此情形。")
                print("        → 本專案已於 httpx_ssl.py 關閉該項檢查;若仍失敗,")
                print("               請確認 opendata.py 是否為最新版(應 import httpx_ssl)。")
            else:
                print("        → macOS 若為官網安裝的 Python,請執行一次:")
                print("               /Applications/Python\\ 3.x/Install\\ Certificates.command")
                print("        → 或更新憑證套件:pip install --upgrade certifi")
        results.append(False)

    # 2 TWSE 營收
    try:
        rev = await opendata.fetch_twse_revenue(ban)
        if rev:
            print(f"[2] TWSE 月營收   {OK}  取得 {len(rev)} 個月,最新 {rev[-1]['m']} 約 {rev[-1]['val']} 億")
            results.append(True)
        else:
            print(f"[2] TWSE 月營收   {SKIP} 非上市公司或查無營收(屬正常情形)")
            results.append(True)
    except Exception as e:
        print(f"[2] TWSE 月營收   {NG}  {type(e).__name__}: {e}")
        results.append(False)

    # 3 食藥署許可證
    import tfda
    try:
        if not tfda.CACHE.exists():
            print(f"[3] 藥品許可證    {SKIP} 尚未建立快取,請先執行:python prefetch.py")
            results.append(True)
        else:
            lic = tfda.search_company(ban=ban)
            if lic["count"]:
                print(f"[3] 藥品許可證    {OK}  查得 {lic['count']} 張(其中新藥/新成分 {lic['new_drug']} 張)")
            else:
                print(f"[3] 藥品許可證    {SKIP} 查得 0 張。本資料集為「西藥」許可證,")
                print(f"                       醫療器材／化粧品／保健食品廠商查無屬正常(例:科妍為玻尿酸醫材廠)。")
            results.append(True)
    except Exception as e:
        print(f"[3] 藥品許可證    {NG}  {type(e).__name__}: {e}")
        results.append(False)

    # 4 GDELT 新聞
    try:
        name = sys.argv[2] if len(sys.argv) > 2 else "台積電"
        news = await opendata.fetch_news(name, limit=3)
        if news:
            print(f"[4] 新聞來源      {OK}  以「{name}」測試,取得 {len(news)} 則")
            results.append(True)
        else:
            print(f"[4] 新聞來源      {NG}  {opendata.LAST_ERROR.get('news', '無回傳結果')}")
            results.append(False)
    except Exception as e:
        print(f"[4] 新聞來源      {NG}  {type(e).__name__}: {e}")
        results.append(False)

    # 5 EAP
    import eap
    if not os.getenv("EAP_TOKEN"):
        print(f"[5] 精誠 EAP      {SKIP} .env 未設定 EAP_TOKEN")
    else:
        # 5a 連線本身:自由問答通道,不要求模型回 JSON
        try:
            r = await eap.chat_raw("請用一句話說明這個知識庫包含哪些資料", session_name="連線測試")
            reply = (r.get("reply") or "").replace("\n", " ")
            print(f"[5] 精誠 EAP 連線  {OK}  平台回覆:{reply[:60]}…")
            results.append(True)

            # 5b JSON 遵循度:各 Agent 端點要求模型嚴格回 JSON,這裡先量測
            try:
                await eap.call_chat('請只回傳這段 JSON,不要有其他文字:{"ok":true}', "格式測試")
                print(f"     └ JSON 遵循  {OK}  模型可依指示輸出純 JSON")
            except Exception as e2:
                msg = getattr(e2, "message", str(e2))
                print(f"     └ JSON 遵循  {WARN} 模型未依指示輸出 JSON(審查/評分功能可能偶發失敗後降級)")
                print(f"        {msg[:110]}")
                print(f"        → 屬模型行為而非連線問題;正式功能的提示詞更完整,通常可正常解析。")
                print(f"        → 若審查功能頻繁失敗,請至 EAP 平台 Robot Setting 補強「只輸出 JSON」指示。")
        except Exception as e:
            code = getattr(e, "code", type(e).__name__)
            msg = getattr(e, "message", str(e))
            print(f"[5] 精誠 EAP 連線  {NG}  {code}: {msg}")
            print(f"      (詳細診斷請執行 python test_eap.py)")
            results.append(False)

    print(f"\n=== 結果:{sum(results)}/{len(results)} 項通過 ===")
    print("提示:任一項失敗只影響該區塊,情資查詢的其他區塊仍會正常顯示。\n")


asyncio.run(main())