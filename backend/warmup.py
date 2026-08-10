"""warmup.py — Demo 前批次預熱:把成功的結果存進快取

用法:
  python warmup.py                     只補「還沒有完整資料」的公司(預設,推薦)
  python warmup.py --all               所有公司都跑,但已有紀錄的項目仍會略過
  python warmup.py --force             連已有紀錄的項目也重跑(重新產生全部素材)
  python warmup.py 4105 1786           指定公司(仍只補該公司缺的項目)
  python warmup.py 4105 --force        指定公司,全部項目重跑
  python warmup.py 4105 --repeat 3     同一家重跑 3 次(挑最好的那次釘選)
  python warmup.py --list              只列出目前缺口,不執行

原理:EAP 不穩,但「跑十次總有幾次會成功」。本腳本反覆嘗試並把每次成功的結果
      存入 data/credit_lens.db;Demo 當天把 .env 設 CACHE_MODE=replay,
      系統就直接讀這些存好的結果——秒回、必成功、內容與實測完全一致。

預設行為(v1.6):逐「公司 × 項目」檢查快取,已經有紀錄的項目直接略過,
      只補真正缺的部分。中斷後再執行會接續未完成處,不會浪費時間重跑。

一致性規則(與系統畫面相同):
      財務分析與技術情報是「素材」,可保存多個版本、可挑選;
      風險審查則是兩者的「衍生結果」,只要財務或技術重跑,風險審查一律連帶重跑,
      確保資料庫中不會出現「裁決依據的是舊素材」的錯配組合。

注意:需先啟動後端(uvicorn main:app --port 8000),本腳本透過 HTTP 呼叫自己的 API,
      確保走的是與前端完全相同的路徑。
"""
import asyncio
import sys

import httpx

BASE = "http://127.0.0.1:8000"
OK, NG, SKIP, HAVE = "\033[92m成功\033[0m", "\033[91m失敗\033[0m", "\033[93m略過\033[0m", "\033[96m已有\033[0m"

# 一家公司的完整素材:五個項目
KINDS = ["finance", "tech", "judge", "pre_brief", "market_read"]
KIND_LABEL = {"finance": "財務分析", "tech": "技術情報", "judge": "風險審查",
              "pre_brief": "拜訪前情資", "market_read": "市場交叉解讀"}


async def post(client, path, body):
    try:
        r = await client.post(f"{BASE}{path}", json=body)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code} {r.text[:80]}"
        return r.json(), ""
    except httpx.HTTPError as e:
        return None, f"{type(e).__name__}: {e}"


def is_demo(obj, *paths) -> bool:
    """判斷回傳是否為降級的示範資料(內容以【示範開頭)。"""
    for p in paths:
        cur = obj
        for k in p:
            if isinstance(cur, list):
                cur = cur[k] if len(cur) > k else None
            elif isinstance(cur, dict):
                cur = cur.get(k)
            else:
                cur = None
            if cur is None:
                break
        if isinstance(cur, str) and cur.startswith("【示範"):
            return True
    return False


async def warm_company(client, code, name, missing, force) -> dict:
    """跑一家公司;missing 為本次需要補的項目集合。force=True 時忽略 missing 全部重跑。"""
    todo = set(KINDS) if force else set(missing)
    if not todo:
        return {}
    cascade = "judge" in todo and ("finance" in todo or "tech" in todo)
    tail = "(風險審查因上游更新而連帶重跑)" if cascade else ""
    print(f"\n── {name or ''}(code:{code})  待補 {len(todo)} 項:"
          f"{'、'.join(KIND_LABEL[k] for k in KINDS if k in todo)} {tail}")
    req = {"company_id": code, "company_name": name, "company_code": code, "force": True}
    done, fin, tech = {}, None, None

    # 財務(judge 需要,故 judge 待補時也要先取得)
    if "finance" in todo or "judge" in todo:
        fin, e = await post(client, "/api/review/finance", req if "finance" in todo else {**req, "force": False})
        ok = bool(fin and not is_demo(fin, ["findings", 0, "text"]))
        if "finance" in todo:
            done["finance"] = ok
            extra = f"score {fin.get('score')}" + (f" · {fin.get('coverage')}" if fin and fin.get("coverage") != "full" else "") if fin else e
            print(f"   財務分析      {OK if ok else NG}  {extra}")

    if "tech" in todo or "judge" in todo:
        tech, e = await post(client, "/api/review/tech", req if "tech" in todo else {**req, "force": False})
        ok = bool(tech and not is_demo(tech, ["findings", 0, "text"]))
        if "tech" in todo:
            done["tech"] = ok
            extra = f"score {tech.get('score')}" + (f" · {tech.get('coverage')}" if tech and tech.get("coverage") != "full" else "") if tech else e
            print(f"   技術情報      {OK if ok else NG}  {extra}")

    if "judge" in todo:
        if fin and tech:
            j, e = await post(client, "/api/review/judge",
                              {"company_id": code, "finance_result": fin, "tech_result": tech, "force": True})
            ok = bool(j and not is_demo(j, ["verdict"]))
            done["judge"] = ok
            print(f"   風險審查      {OK if ok else NG}  {('final ' + str(j.get('final_score'))) if j else e}")
        else:
            done["judge"] = False
            print(f"   風險審查      {SKIP} 前置結果缺失")

    if "pre_brief" in todo:
        b, e = await post(client, "/api/pre/brief", req)
        ok = bool(b and b.get("radar") and not is_demo(b, ["radar", 0, "reason"]))
        done["pre_brief"] = ok
        print(f"   拜訪前情資    {OK if ok else NG}  {('雷達 ' + str(len(b.get('radar', []))) + ' 維') if b else e}")

    if "market_read" in todo:
        mr, e = await post(client, "/api/market/eap_read", {"company_id": code, "company_name": name, "force": True})
        if mr and not mr.get("_degraded"):
            done["market_read"] = True
            print(f"   市場交叉解讀  {OK}  {len(mr.get('summary', []))} 條")
        else:
            done["market_read"] = False
            print(f"   市場交叉解讀  {SKIP} {e or '無股價資料或已降級'}")

    n = sum(done.values())
    print(f"   → 本輪補齊 {n}/{len(done)} 項")
    return done


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    repeat, force = 1, "--force" in sys.argv
    run_all, list_only = "--all" in sys.argv, "--list" in sys.argv
    if "--repeat" in sys.argv:
        i = sys.argv.index("--repeat")
        if i + 1 < len(sys.argv):
            repeat = int(sys.argv[i + 1])
            args = [a for a in args if a != sys.argv[i + 1]]

    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
        st, e = await post(client, "/api/cache/stats", {})
        if st is None:
            print(f"\n{NG} 連不上後端 {BASE}:{e}")
            print("請先在另一個視窗啟動:python -m uvicorn main:app --port 8000\n")
            return
        print(f"\n=== Demo 預熱(快取模式 {st['mode']},已存 {st['total']} 筆)===")
        if st["mode"] == "replay":
            print(f"{SKIP} 目前為 replay 模式,已有快取的項目不會真打 EAP。")
            print("      要累積新素材請把 .env 的 CACHE_MODE 改回 record 並重啟後端。")

        # 取得公司清單與現有覆蓋度
        uni, _ = await post(client, "/api/eap/universe", {})
        rows = [c for c in (uni or {}).get("companies", []) if c.get("code")]
        name_by_code = {c["code"]: c["name"] for c in rows}
        cov, _ = await post(client, "/api/cache/coverage", {})
        have_map = {c["company_id"]: set(c["kinds"]) for c in (cov or {}).get("companies", [])}

        # 偵測「已存在但過期」的裁決:資料庫中的 judge 若比 finance/tech 舊,
        # 代表它是依更早的素材算出來的(例如上一版 warmup 或手動重跑造成),
        # 這種錯配不會被「缺項」偵測到,必須另外抓出來重跑。
        async def stale_judge(code) -> bool:
            latest = {}
            for k in ("finance", "tech", "judge"):
                items, _ = await post(client, "/api/cache/list", {"kind": k, "company_id": code, "limit": 1})
                rows = (items or {}).get("items") or []
                if rows:
                    latest[k] = rows[0]["created_at"]
            if "judge" not in latest:
                return False
            upstream = [latest[k] for k in ("finance", "tech") if k in latest]
            return bool(upstream) and latest["judge"] < max(upstream)

        if args:
            targets = [(c, name_by_code.get(c, "")) for c in args]
        elif rows:
            targets = [(c["code"], c["name"]) for c in rows]
        else:
            print(f"\n{NG} 取不到 EAP 公司清單;請改為指定代號:python warmup.py 4105 1786\n")
            return

        # 逐公司算出缺口
        # 一致性規則:風險審查是財務與技術的衍生結果,上游一旦重跑,
        # 既有的裁決就是依舊素材算出的,必須連帶重跑,否則資料庫會留下對不上的組合。
        plan, stale_list = [], []
        for code, name in targets:
            missing = [k for k in KINDS if k not in have_map.get(code, set())]
            if force:
                missing = list(KINDS)
            elif ("finance" in missing or "tech" in missing) and "judge" not in missing:
                missing.append("judge")          # 本次要重跑上游 → 裁決強制跟著更新
            elif "judge" not in missing and await stale_judge(code):
                missing.append("judge")          # 既有裁決比素材舊 → 屬錯配,一併更新
                stale_list.append(code)
            if missing:
                plan.append((code, name, [k for k in KINDS if k in missing]))

        complete = len(targets) - len(plan)
        print(f"\n目標 {len(targets)} 家:已完整 {complete} 家,待補 {len(plan)} 家")
        if stale_list:
            print(f"{SKIP} 其中 {len(stale_list)} 家的裁決比素材舊(錯配),已排入重跑:"
                  f"{'、'.join(stale_list[:10])}")
        if plan:
            print("\n--- 缺口明細(前 15 家)---")
            for code, name, miss in plan[:15]:
                cas = "judge" in miss and ("finance" in miss or "tech" in miss)
                print(f"  {code:>6} {(name or '')[:10]:<12} 補 {len(miss)} 項:"
                      f"{'、'.join(KIND_LABEL[k] for k in miss)}{' ←含連帶重跑' if cas else ''}")
            if len(plan) > 15:
                print(f"  …另有 {len(plan) - 15} 家")

        if list_only:
            print("\n【僅列出缺口,未執行】拿掉 --list 即開始補齊。\n")
            return
        if not plan:
            print("\n所有目標公司的素材都已齊備,無須執行。")
            print("若要重新產生素材,請加 --force。\n")
            return
        if not run_all and not args and len(plan) > 8:
            plan = plan[:8]
            print(f"\n{SKIP} 預設一次只補 8 家(避免單次執行過久),要全部補齊請加 --all")

        print(f"\n開始補齊 {len(plan)} 家 × {repeat} 輪")
        for r in range(repeat):
            if repeat > 1:
                print(f"\n===== 第 {r + 1}/{repeat} 輪 =====")
            for code, name, miss in plan:
                await warm_company(client, code, name, miss, force)

        cov2, _ = await post(client, "/api/cache/coverage", {})
        ready = [c for c in (cov2 or {}).get("companies", []) if c["ready"]]
        st2, _ = await post(client, "/api/cache/stats", {})
        print(f"\n=== 完成:快取共 {st2['total']} 筆,可完整 Demo 的公司 {len(ready)} 家 ===")
        for c in ready[:10]:
            print(f"  · {c['company_name'] or c['company_id']}(code:{c['company_id']}) "
                  f"{c['have']}/{c['need']} 項")
        still = [c for c in (cov2 or {}).get("companies", []) if not c["ready"]]
        if still:
            print(f"\n仍不完整 {len(still)} 家,可再執行一次 python warmup.py 接續補齊。")
        print("\nDemo 當天:把 backend/.env 設 CACHE_MODE=replay 並重啟後端即可全程重播。\n")


if __name__ == "__main__":
    asyncio.run(main())