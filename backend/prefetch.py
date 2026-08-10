"""prefetch.py — Demo 前預先下載兩份本地快取(只需執行一次)
  1. 食藥署藥品許可證資料集(較大)
  2. 證券代號↔統一編號對照表(TWSE 上市 + TPEx 上櫃)
用法:python prefetch.py [--force]
"""
import asyncio
import sys

import opendata
import tfda


async def main():
    force = "--force" in sys.argv

    print("[1/2] 下載食藥署藥品許可證資料集中(檔案較大,請稍候)…")
    try:
        n = await tfda.download(force=force)
        print(f"      完成,共 {n:,} 筆許可證 → {tfda.CACHE.name}")
    except Exception as e:
        print(f"      下載失敗:{type(e).__name__} {e}")
        print("      未建立時,情資查詢的「藥品許可證」區塊會自動隱藏,其餘功能不受影響。")

    print("[2/2] 建立證券代號↔統一編號對照表(TWSE 上市 + TPEx 上櫃)…")
    try:
        m = await opendata.build_code_ban_map(force=force)
        if m:
            listed = sum(1 for v in m.values() if v.get("market") == "上市")
            otc = sum(1 for v in m.values() if v.get("market") == "上櫃")
            print(f"      完成,共 {len(m):,} 家(上市 {listed} / 上櫃 {otc})→ {opendata.CODE_BAN_CACHE.name}")
        else:
            print(f"      未取得資料:{opendata.LAST_ERROR}")
            print("      未建立時,案件仍可用證券代號運作,僅無法自動帶出統編。")
    except Exception as e:
        print(f"      建立失敗:{type(e).__name__} {e}")


if __name__ == "__main__":
    asyncio.run(main())
