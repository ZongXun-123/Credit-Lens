"""find_test_cases.py — 從本地食藥署快取中,列出「保證查得到資料」的測試統編
用法:python find_test_cases.py [顯示筆數]     例:python find_test_cases.py 15

這些統編直接取自食藥署官方資料,因此「藥品許可證」區塊必定有結果,
可直接貼到情資查詢頁測試。(需先執行過 python prefetch.py)
"""
import json
import sys
from collections import defaultdict

import tfda

if not tfda.CACHE.exists():
    print("尚未建立快取,請先執行:python prefetch.py")
    raise SystemExit(1)

top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
data = json.loads(tfda.CACHE.read_text(encoding="utf-8"))
rows = data.get("rows", [])

agg = defaultdict(lambda: {"name": "", "count": 0})
for r in rows:
    ban = r.get("ban", "")
    if ban and ban.isdigit() and len(ban) == 8:
        agg[ban]["count"] += 1
        if not agg[ban]["name"]:
            agg[ban]["name"] = r.get("company", "")

if not agg:
    print(f"快取有 {len(rows):,} 筆,但沒有解析到統一編號欄位。")
    print("請把下面這筆原始資料貼出來,以便確認欄位名稱:")
    print(json.dumps(rows[0] if rows else {}, ensure_ascii=False, indent=2))
    raise SystemExit(1)

ranked = sorted(agg.items(), key=lambda kv: kv[1]["count"], reverse=True)[:top_n]

print(f"\n=== 可直接使用的測試統編(取自 {len(rows):,} 筆許可證)===\n")
print(f"{'統一編號':<12}{'許可證數':>8}  公司名稱")
print("-" * 64)
for ban, info in ranked:
    print(f"{ban:<12}{info['count']:>8}  {info['name']}")
print("\n用法:把統編貼到網頁「情資查詢」的搜尋框即可。")
print("提示:上市藥廠(如生達 71122503)還會多帶出 TWSE 月營收。\n")
