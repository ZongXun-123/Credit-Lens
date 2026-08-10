"""check_token.py — 檢查 .env 裡的 EAP_TOKEN 是否完整、有效
用法:python check_token.py

背景:平台回 403 {"message":"invalid signature"} 代表 JWT 簽章驗證失敗。
      最常見原因是複製 Token 時被截斷、混入換行或引號,而不是權限問題。
      本腳本只在本機解析,不會把 Token 送到任何地方。
"""
import base64
import json
import os
import time

from dotenv import load_dotenv

from envtools import env

load_dotenv()

OK, NG, WARN = "\033[92m✓\033[0m", "\033[91m✗\033[0m", "\033[93m!\033[0m"


def b64url(part: str) -> dict:
    part += "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part))


def main():
    raw = os.getenv("EAP_TOKEN", "") or ""
    token = env("EAP_TOKEN")

    print("\n=== EAP Token 診斷 ===\n")

    if not token:
        print(f"{NG} .env 未設定 EAP_TOKEN")
        return

    # --- 原始字串健檢 ---
    print(f"{OK} 長度:{len(token)} 字元")
    if raw != raw.strip():
        print(f"{WARN} 原始值前後有空白(已自動清除)")
    for bad, name in [("\n", "換行"), ("\r", "歸位字元"), (" ", "空格"), ('"', "雙引號"), ("'", "單引號")]:
        if bad in token:
            print(f"{NG} Token 內含{name} → 複製時被截斷或混入雜訊,請重新複製")
    if not token.isascii():
        print(f"{NG} 含非 ASCII 字元(可能複製到說明文字)")

    parts = token.split(".")
    if len(parts) != 3:
        print(f"{NG} JWT 應由 3 段以「.」分隔,實際為 {len(parts)} 段 → Token 不完整")
        return
    print(f"{OK} 結構正確:3 段(header.payload.signature)")
    print(f"    各段長度:{len(parts[0])} / {len(parts[1])} / {len(parts[2])}")
    if len(parts[2]) < 20:
        print(f"{NG} 簽章段過短({len(parts[2])} 字元)→ Token 尾端被截斷,這正是 invalid signature 的典型原因")

    # --- 內容解析 ---
    try:
        head = b64url(parts[0])
        body = b64url(parts[1])
    except (ValueError, json.JSONDecodeError) as e:
        print(f"{NG} 無法解碼:{e} → Token 內容毀損")
        return

    print(f"\n--- Header ---\n    alg={head.get('alg')}  typ={head.get('typ')}")

    print("\n--- Payload(重要欄位)---")
    for k in ["iss", "aud", "sub", "g_tid", "g_uid", "isAPI", "nickname", "email"]:
        if k in body:
            print(f"    {k:10} = {body[k]}")

    now = int(time.time())
    exp, iat = body.get("exp"), body.get("iat")
    if iat:
        print(f"    {'iat':10} = {iat}  ({time.strftime('%Y-%m-%d', time.localtime(iat))} 簽發)")
    if exp:
        left = exp - now
        state = f"{OK} 未過期" if left > 0 else f"{NG} 已過期"
        print(f"    {'exp':10} = {exp}  ({time.strftime('%Y-%m-%d', time.localtime(exp))}) {state}")

    tenant = str(body.get("g_tid", "")).split(":")[0]
    print(f"\n{OK} 將送出的 x-application-tenant = {tenant or '(無法解析)'}")

    print("\n--- 判讀 ---")
    print("  Token 結構完整但伺服器仍回 invalid signature,可能原因:")
    print("   1. Token 已被重新產生 → 舊的失效,請至大會控制台取最新的")
    print("   2. 複製時漏字(尤其最後幾碼)→ 重新複製整串,確認頭尾都沒漏")
    print("   3. 該 Token 屬於不同環境/專案 → 向 EAP 平台組確認是否為本專案的 API Token")
    print("   4. 認證方式非 Bearer → 執行 python probe_eap.py 會自動測試其他認證寫法\n")


if __name__ == "__main__":
    main()
