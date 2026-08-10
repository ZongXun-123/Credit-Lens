"""test_eap.py — 依官方規格測試 EAP 連線(Gemini Enterprise API v1)
用法:python test_eap.py

流程(來自官方 OpenAPI 規格):
  1. POST {BASE}/chat/create          body {"title": ...}                → chat_id
  2. POST {BASE}/chat/{chat_id}       body {"q": ..., "streaming": false} → response
  3. GET  {BASE}/chat/{chat_id}/messages                                  → 歷史訊息
"""
import asyncio
import base64
import json
import time

import httpx
from dotenv import load_dotenv

import eap
from envtools import env, env_ascii

load_dotenv()

OK, NG, INFO = "\033[92m✓\033[0m", "\033[91m✗\033[0m", "\033[93m→\033[0m"


async def main():
    base = (env("EAP_API_BASE") or "https://cloud.geminidata.com/api/v1").rstrip("/")
    token = env("EAP_TOKEN")
    project = env("EAP_PROJECT_ID")
    tenant = env_ascii("EAP_TENANT") or eap.tenant_from_token(token)

    print("\n=== EAP 連線測試(官方規格流程)===\n")
    print(f"Base      :{base}")
    print(f"Token     :{'已設定(長度 ' + str(len(token)) + ')' if token else '未設定'}")
    print(f"ProjectID :{project or '(未設定)'}")
    print(f"Tenant    :{tenant or '(未解析)'}")

    if not token:
        print(f"\n{NG} 請先於 .env 設定 EAP_TOKEN\n")
        return

    try:
        p = token.split(".")[1]; p += "=" * (-len(p) % 4)
        exp = json.loads(base64.urlsafe_b64decode(p)).get("exp", 0)
        left = exp - int(time.time())
        if left <= 0:
            print(f"\n{NG} Token 已過期({time.strftime('%m-%d %H:%M', time.localtime(exp))}),請重新取得\n")
            return
        print(f"Token 到期:{time.strftime('%m-%d %H:%M', time.localtime(exp))}(剩 {left//3600} 小時 {left%3600//60} 分)")
    except Exception:
        pass

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if tenant:
        headers["x-application-tenant"] = tenant

    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0), follow_redirects=True) as c:
        # 步驟 1
        print(f"\n{INFO} 步驟 1:POST {base}/chat/create")
        body = {"title": "Credit-Lens 連線測試"}
        if project:
            body.update({"projectId": project, "project_id": project})
        r1 = await c.post(f"{base}/chat/create", json=body, headers=headers)
        print(f"    HTTP {r1.status_code}  {r1.text[:220]}")
        if r1.status_code != 200:
            print(f"\n{NG} 建立聊天室失敗。若為 400/403,多半是缺少或錯誤的 Project ID。\n")
            return
        chat_id = await eap._extract_chat_id(r1.json())
        if not chat_id:
            print(f"\n{NG} 回應中找不到 chat_id。完整回應如下,請貼給我以便補上欄位對應:")
            print(json.dumps(r1.json(), ensure_ascii=False, indent=2)[:600])
            return
        print(f"{OK}   chat_id = {chat_id}")

        # 步驟 2
        print(f"\n{INFO} 步驟 2:POST {base}/chat/{chat_id}")
        q = "請用一句話說明這個知識庫包含哪些企業財務資料"
        r2 = await c.post(f"{base}/chat/{chat_id}", json={"q": q, "streaming": False}, headers=headers)
        print(f"    HTTP {r2.status_code}  Content-Type: {r2.headers.get('content-type', '')}")
        if r2.status_code != 200:
            print(f"    {r2.text[:300]}")
            print(f"\n{NG} 送出問題失敗\n")
            return
        ctype = r2.headers.get("content-type", "")
        answer = eap._parse_sse(r2.text) if "event-stream" in ctype else eap._extract_answer(r2.json(), r2.text)
        print(f"\n{OK} 平台回覆:\n{'-' * 70}\n{answer[:900]}\n{'-' * 70}")

        # 步驟 3
        print(f"\n{INFO} 步驟 3:GET {base}/chat/{chat_id}/messages")
        r3 = await c.get(f"{base}/chat/{chat_id}/messages", headers=headers)
        print(f"    HTTP {r3.status_code}  {r3.text[:200]}")

    print(f"\n{OK} 連線成功!後端已可使用真實 EAP。重啟 uvicorn 即生效。\n")


if __name__ == "__main__":
    asyncio.run(main())
