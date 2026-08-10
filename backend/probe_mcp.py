"""probe_mcp.py — 以 MCP 協定連線精誠 EAP,列出可用工具
用法:python probe_mcp.py

這支腳本會完成 MCP 握手(initialize → session id → tools/list),
把平台提供的工具名稱、說明與參數印出來。
拿到工具清單後,即可確定 Agent 該呼叫哪一支、參數怎麼帶。
"""
import asyncio
import json

from dotenv import load_dotenv

import eap
import mcp_client as mcp
from envtools import env, env_ascii

load_dotenv()

OK, NG = "\033[92m✓\033[0m", "\033[91m✗\033[0m"


async def main():
    url = env("EAP_MCP_URL") or "https://cloud.geminidata.com/mcp"
    token = env("EAP_TOKEN")
    tenant = env_ascii("EAP_TENANT") or eap.tenant_from_token(token)

    print(f"\n=== MCP 連線探測 ===\n")
    print(f"端點  :{url}")
    print(f"Token :{'已設定(長度 ' + str(len(token)) + ')' if token else '未設定'}")
    print(f"Tenant:{tenant or '未解析'}\n")

    # 兩種認證組合都試:帶 tenant / 不帶 tenant
    for label, use_tenant in [("帶 tenant 標頭", True), ("不帶 tenant 標頭", False)]:
        print(f"--- 嘗試:{label} ---")
        try:
            async with mcp.McpSession(url, token, tenant if use_tenant else "") as s:
                print(f"{OK} 握手成功")
                print(f"    伺服器:{json.dumps(s.server_info, ensure_ascii=False)}")
                print(f"    Session ID:{s.session_id}")

                tools = await s.list_tools()
                print(f"{OK} 取得 {len(tools)} 個工具\n")
                for i, t in enumerate(tools, 1):
                    print(f"  [{i}] {t.get('name')}")
                    desc = (t.get("description") or "").strip().replace("\n", " ")
                    if desc:
                        print(f"      說明:{desc[:140]}")
                    props = (t.get("inputSchema") or {}).get("properties") or {}
                    if props:
                        print(f"      參數:{', '.join(props.keys())}")
                        req = (t.get("inputSchema") or {}).get("required") or []
                        if req:
                            print(f"      必填:{', '.join(req)}")
                    print()

                chosen = mcp.pick_tool(tools)
                if chosen:
                    args = mcp.build_arguments(chosen, "請用一句話說明你能提供什麼資料")
                    print(f"--- 試呼叫「{chosen.get('name')}」,參數 {json.dumps(args, ensure_ascii=False)} ---")
                    try:
                        reply = await s.call_tool(chosen["name"], args)
                        print(f"{OK} 回應:\n{reply[:800]}\n")
                        print("請把上面的工具清單與回應貼出來,即可完成 Agent 串接。\n")
                    except mcp.McpError as e:
                        print(f"{NG} 呼叫失敗:{e.message}\n    {e.detail}\n")
                return
        except mcp.McpError as e:
            print(f"{NG} {e.message}")
            if e.detail:
                print(f"    {e.detail}")
            print()
        except Exception as e:
            print(f"{NG} {type(e).__name__}: {e}\n")

    print("兩種組合皆失敗。請把上面的錯誤訊息貼出來。\n")


if __name__ == "__main__":
    asyncio.run(main())
