# mcp_client.py — MCP(Model Context Protocol)Streamable HTTP 客戶端
#
# 為何走這條:精誠 EAP 控制台顯示「MCP 已啟用」,且 /mcp 端點會回標準 JSON-RPC 錯誤
#   · 只帶 Accept: application/json → 406「必須同時接受 application/json 與 text/event-stream」
#   · 補上 Accept 後            → 400「Missing session ID」
# 兩則都是 MCP 規範的正確回應,代表伺服器就在那裡,只是需要照協定握手。
#
# 協定流程:
#   1. POST initialize          → 回應標頭帶 Mcp-Session-Id
#   2. POST notifications/initialized(通知,無回應內容)
#   3. POST tools/list          → 取得可用工具清單
#   4. POST tools/call          → 實際呼叫工具
import json
from typing import Optional

import httpx

PROTOCOL_VERSION = "2024-11-05"
ACCEPT = "application/json, text/event-stream"


class McpError(Exception):
    def __init__(self, message: str, detail: str = ""):
        self.message, self.detail = message, detail
        super().__init__(message)


def parse_response(r: httpx.Response) -> dict:
    """MCP 回應可能是純 JSON,也可能是 SSE(text/event-stream),兩種都要能解。"""
    ctype = r.headers.get("content-type", "")
    text = r.text.strip()
    if "text/event-stream" in ctype or text.startswith("event:") or text.startswith("data:"):
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload and payload != "[DONE]":
                    try:
                        return json.loads(payload)
                    except json.JSONDecodeError:
                        continue
        raise McpError("SSE 回應中找不到有效的 data 區段", text[:200])
    try:
        return json.loads(text) if text else {}
    except json.JSONDecodeError:
        raise McpError("回應非 JSON", text[:200])


class McpSession:
    """一次連線的 MCP 會談。用法:async with McpSession(url, token) as s: ..."""

    def __init__(self, url: str, token: str = "", tenant: str = "", timeout: float = 90.0):
        self.url, self.token, self.tenant = url, token, tenant
        self.session_id: Optional[str] = None
        self.server_info: dict = {}
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=15.0), follow_redirects=True)
        self._rpc_id = 0

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", "Accept": ACCEPT}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.tenant:
            h["x-application-tenant"] = self.tenant
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    async def _rpc(self, method: str, params: Optional[dict] = None, notify: bool = False) -> dict:
        self._rpc_id += 1
        body = {"jsonrpc": "2.0", "method": method}
        if not notify:
            body["id"] = self._rpc_id
        if params is not None:
            body["params"] = params

        r = await self._client.post(self.url, json=body, headers=self._headers())

        # initialize 的回應標頭會帶 session id,之後每次都要附上
        sid = r.headers.get("mcp-session-id") or r.headers.get("Mcp-Session-Id")
        if sid:
            self.session_id = sid

        if notify and r.status_code in (200, 202, 204):
            return {}
        if r.status_code >= 400:
            raise McpError(f"{method} 失敗 HTTP {r.status_code}", r.text[:250])

        data = parse_response(r)
        if "error" in data:
            e = data["error"]
            raise McpError(f"{method} 回傳錯誤 {e.get('code')}", str(e.get("message", ""))[:250])
        return data.get("result", {})

    async def __aenter__(self):
        result = await self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"roots": {"listChanged": False}, "sampling": {}},
            "clientInfo": {"name": "credit-lens", "version": "1.0"},
        })
        self.server_info = result.get("serverInfo", {})
        try:
            await self._rpc("notifications/initialized", notify=True)
        except McpError:
            pass  # 部分實作不要求此通知
        return self

    async def __aexit__(self, *exc):
        await self._client.aclose()

    async def list_tools(self) -> list:
        return (await self._rpc("tools/list", {})).get("tools", [])

    async def call_tool(self, name: str, arguments: dict) -> str:
        """呼叫工具並把回傳內容組成純文字。"""
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        parts = []
        for item in result.get("content", []):
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif "text" in item:
                    parts.append(str(item["text"]))
        if not parts and result:
            parts.append(json.dumps(result, ensure_ascii=False))
        return "\n".join(p for p in parts if p)


# 工具名稱關鍵字(依可能性排序),用於自動挑選「問答/檢索」類工具
TOOL_HINTS = ["chat", "ask", "query", "question", "search", "rag", "retriev", "knowledge", "assistant", "answer"]


def pick_tool(tools: list) -> Optional[dict]:
    """從工具清單挑出最像『問答』的一個。"""
    if not tools:
        return None
    for hint in TOOL_HINTS:
        for t in tools:
            if hint in str(t.get("name", "")).lower():
                return t
        for t in tools:
            if hint in str(t.get("description", "")).lower():
                return t
    return tools[0]


def build_arguments(tool: dict, message: str) -> dict:
    """依工具的 inputSchema 決定要把提問塞進哪個參數。"""
    schema = tool.get("inputSchema") or {}
    props = schema.get("properties") or {}
    required = schema.get("required") or []

    for key in ["query", "question", "message", "text", "input", "prompt", "q", "keyword"]:
        if key in props:
            return {key: message}
    if required:
        return {required[0]: message}
    if props:
        return {next(iter(props)): message}
    return {"query": message}
