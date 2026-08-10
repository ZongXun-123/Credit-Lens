"""check_patents.py — 檢查兩個專利資料源是否接得上
用法:python check_patents.py [公司名稱]     例:python check_patents.py 科妍生物科技

檢查項目:
  1. Google Patents 查詢端點(免金鑰;官方網頁自用端點,非公開 API)
  2. TIPO GPSS API(需 .env 設定 TIPO_API_KEY;未設定則略過)
  3. 深層連結產生(永遠可用,失敗代表程式本身有問題)

任一即時來源失敗只影響該欄,情資查詢頁會自動退回一鍵檢索連結。
若 TIPO 回傳「結構無法解析」,請把印出的原始回應貼給開發者,以便對齊欄位名稱。
"""
import asyncio
import json
import sys

from dotenv import load_dotenv

load_dotenv()

import patents  # noqa: E402(需先 load_dotenv)

OK = "\033[92m通過\033[0m"
NG = "\033[91m失敗\033[0m"
SKIP = "\033[93m略過\033[0m"


async def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "科妍生物科技股份有限公司"
    print(f"\n=== Credit-Lens 專利資料源檢查(公司:{name})===\n")

    # 3 深層連結(先測,失敗代表程式問題而非網路問題)
    links = patents.build_links(name)
    if links:
        print(f"[0] 深層連結      {OK}  簡稱「{links['company_short']}」/ 檢索式 {links['tipo_expr']}")
    else:
        print(f"[0] 深層連結      {NG}  無法由公司名稱產生檢索式")
        return

    # 1 Google Patents
    if not patents.google_live_enabled():
        print(f"[1] Google Patents {SKIP} .env 已設 GOOGLE_PATENTS_LIVE=false")
    else:
        g = await patents.fetch_google(name)
        if g:
            print(f"[1] Google Patents {OK}  共 {g['count']} 件,取得 {len(g['recent'])} 筆清單")
            for p in g["recent"][:3]:
                print(f"      · {p['date']:>10}  {p['no']:<16} {p['title'][:36]}")
        else:
            print(f"[1] Google Patents {NG}  {patents.LAST_ERROR.get('google', '無回傳')}")
            print("      → 此端點為 Google 網頁自用、非公開 API,格式變動屬正常;")
            print("        失敗時前端會自動退回一鍵檢索連結,不影響 Demo。")

    # 2 TIPO GPSS
    if not patents.api_enabled():
        print(f"[2] TIPO GPSS API {SKIP} .env 未設定 TIPO_API_KEY(僅提供檢索連結)")
        print("      申請:https://tiponet.tipo.gov.tw/gpss1/ → 使用說明 → API 驗證碼線上申請(免費)")
    else:
        t = await patents.fetch_tipo(name)
        if t:
            print(f"[2] TIPO GPSS API {OK}  共 {t['count']} 件,取得 {len(t['recent'])} 筆清單")
            for p in t["recent"][:3]:
                print(f"      · {p['date']:>10}  {p['no']:<16} {p['title'][:36]}")
        else:
            print(f"[2] TIPO GPSS API {NG}  {patents.LAST_ERROR.get('tipo', '無回傳')}")
            print("      → 若為「結構無法解析」,請執行下行指令並把輸出貼給開發者對齊欄位:")
            print(f'        python -c "import asyncio,httpx;print(asyncio.run(httpx.AsyncClient().get(')
            print(f"        '{patents.TIPO_API_URL}', params={{'userCode':'<你的驗證碼>','expFmt':'json',")
            print(f"        'expQty':3,'PA':'{links['company_short']}'}})).text[:800])\"")

    print("\n=== 完成 ===\n")


if __name__ == "__main__":
    asyncio.run(main())
