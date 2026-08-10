# eap.py — 精誠 EAP 封裝(規格書 3.2 / 7.3)
# 真實流程(由組員實測破解,GeminiData 平台 v1 路由):
#   階段 1:POST {EAP_API_URL}                body={"name": "..."}    → 取得聊天室 id
#   階段 2:POST {EAP_API_URL}/{id}/messages  body={"message": "..."} → 回應欄位 reply
# 本模組職責:兩階段呼叫、逾時、失敗重試 1 次、LLM 回傳非法 JSON 時修復
import os
import json
import re
from pathlib import Path

import httpx

import httpx_ssl

from envtools import env, env_ascii
import mcp_client as _mcp

PROMPT_DIR = Path(__file__).parent / "prompts"


class EapError(Exception):
    def __init__(self, code: str, status: int, message: str):
        self.code, self.status, self.message = code, status, message


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8")


def repair_json(text: str) -> dict:
    """LLM 回傳非法 JSON 時的修復(7.3):去除 markdown 圍欄、擷取最外層大括號。"""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(t[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise EapError("LLM_FORMAT_ERROR", 502,
                   f"LLM 回傳格式無法修復,請重試。模型實際回覆(前 150 字):{t[:150]}")


def tenant_from_token(token: str) -> str:
    """從 JWT payload 取出租戶識別(g_tid,格式 <tenant>:<role>)。"""
    try:
        import base64
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return str(data.get("g_tid", "")).split(":")[0] or str(data.get("g_uid", ""))
    except (IndexError, ValueError, TypeError):
        return ""


# 契約欄位:出現任一個就代表已經拆到真正的內容,不再往下拆
_CONTRACT_KEYS = ("companies", "summary", "agent", "score", "findings", "radar", "questions", "verdict",
                  "final_score", "waterfall", "commitments", "responses", "new_risks",
                  "reason", "follow", "error", "recommendation")
# 信封欄位:平台把答案包在這些鍵裡(實測為 result)
_ENVELOPE_KEYS = ("result", "response", "reply", "answer", "content", "message", "text", "data")


def unwrap(obj, depth: int = 0):
    """把 {"result": "<JSON 字串>", "tokensIn": 0, ...} 這類外層信封遞迴拆到真正的內容。
    平台不同版本、串流與非串流的包裝層數可能不同,一律用這支收斂。"""
    if depth > 4 or not isinstance(obj, dict):
        return obj
    if any(k in obj for k in _CONTRACT_KEYS):
        return obj
    for k in _ENVELOPE_KEYS:
        v = obj.get(k)
        if isinstance(v, dict):
            return unwrap(v, depth + 1)
        if isinstance(v, str) and v.strip():
            try:
                return unwrap(repair_json(v), depth + 1)
            except EapError:
                continue
    return obj


def _headers() -> dict:
    token = env("EAP_TOKEN")
    if not token:
        raise EapError("INTERNAL_ERROR", 500, "後端未設定 EAP_TOKEN,請於 backend/.env 填入大會提供的 Token")
    # HTTP 標頭只允許 ASCII;含中文代表 .env 仍是佔位說明文字未替換
    if not token.isascii():
        raise EapError("INTERNAL_ERROR", 500,
                       "EAP_TOKEN 含非 ASCII 字元(多半是 .env 仍保留「請貼上你們團隊的JWT_Token」佔位字串)。"
                       "請改成大會控制台取得的實際 Token,格式應為 eyJ 開頭的長字串。")
    if not token.startswith("ey"):
        raise EapError("INTERNAL_ERROR", 500,
                       f"EAP_TOKEN 格式可疑(開頭為「{token[:12]}…」)。JWT 應以 eyJ 開頭,請確認未複製到註解或多餘文字。")
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # 平台要求 x-application-tenant 標頭;未於 .env 指定時自 Token 的 g_tid 自動解析
    # env_ascii:含中文的設定值一律忽略(多半是 .env 註解誤植),改由 Token 解析
    tenant = env_ascii("EAP_TENANT") or tenant_from_token(token)
    if tenant and not tenant.isascii():
        tenant = ""
    if tenant:
        h["x-application-tenant"] = tenant
    return h


# 平台實測回應:{"acknowledged": true, "insertedId": "6a60..."}(MongoDB 風格)
_ID_KEYS = ("insertedId", "inserted_id", "chat_id", "chatId", "id", "_id")


async def _extract_chat_id(data) -> str:
    """建立聊天室的回應中取出 chat_id。"""
    if not isinstance(data, dict):
        return ""
    for k in _ID_KEYS:
        if data.get(k):
            return str(data[k])
    for nest in ("chat", "data", "result"):
        inner = data.get(nest)
        if isinstance(inner, dict):
            for k in _ID_KEYS:
                if inner.get(k):
                    return str(inner[k])
    # 最後手段:任何看起來像 id 的欄位(24 碼十六進位 = MongoDB ObjectId)
    for k, v in data.items():
        if isinstance(v, str) and re.fullmatch(r"[0-9a-f]{24}", v):
            return v
    return ""


# 平台實測回應:{"result": "<答案字串>", "tokensIn": 0, "tokensOut": 0}
_ANSWER_KEYS = ("result", "response", "reply", "answer", "content", "message", "text")


def _extract_answer(data, raw_text: str) -> str:
    """送出問題後取出回答文字。平台實際使用 result 欄位,其餘為相容性備援。"""
    if isinstance(data, dict):
        for k in _ANSWER_KEYS:
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                return v
        for nest in ("data", "result", "message"):
            inner = data.get(nest)
            if isinstance(inner, dict):
                for k in _ANSWER_KEYS:
                    if isinstance(inner.get(k), str) and inner[k].strip():
                        return inner[k]
    return raw_text


def _parse_sse(text: str) -> str:
    """streaming=true 時回傳 text/event-stream,把各 chunk 組回完整回答。"""
    parts = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
            if isinstance(obj, dict):
                for k in ("result", "response", "content", "text", "delta", "answer"):
                    v = obj.get(k)
                    if isinstance(v, str):
                        parts.append(v)
                        break
            elif isinstance(obj, str):
                parts.append(obj)
        except json.JSONDecodeError:
            parts.append(payload)   # 純文字 chunk
    return "".join(parts)


def api_base() -> str:
    return (env("EAP_API_BASE") or "https://cloud.geminidata.com/api/v1").rstrip("/")


async def _create_chat(client: httpx.AsyncClient, title: str) -> str:
    """步驟 1:POST {base}/chat/create body={"title": ...} → chat_id"""
    base = api_base()
    project_id = env("EAP_PROJECT_ID")
    create_body = {"title": title[:60]}
    if project_id:
        # 專案綁定:欄位名不確定,同時帶多種寫法(後端忽略未知欄位)
        create_body.update({"projectId": project_id, "project_id": project_id})
    r1 = await client.post(f"{base}/chat/create", json=create_body, headers=_headers())
    if r1.status_code == 401:
        raise EapError("INTERNAL_ERROR", 500, "EAP Token 無效或過期(HTTP 401),請更新 .env 之 EAP_TOKEN")
    if r1.status_code != 200:
        raise EapError("EAP_TIMEOUT", 504,
                       f"建立聊天室失敗 HTTP {r1.status_code}:{r1.text[:150]}"
                       f"(確認 EAP_API_BASE={base} 與 EAP_PROJECT_ID 是否正確)")
    try:
        chat_id = await _extract_chat_id(r1.json())
    except ValueError:
        raise EapError("LLM_FORMAT_ERROR", 502, f"建立聊天室回應非 JSON:{r1.text[:150]}")
    if not chat_id:
        raise EapError("LLM_FORMAT_ERROR", 502, f"建立聊天室回應中找不到 chat_id:{r1.text[:200]}")
    return chat_id


async def _send_message(client: httpx.AsyncClient, chat_id: str, question: str) -> str:
    """步驟 2:POST {base}/chat/{chat_id} body={"q": ..., "streaming": false} → 回答純文字"""
    base = api_base()
    r2 = await client.post(f"{base}/chat/{chat_id}",
                           json={"q": question, "streaming": False}, headers=_headers())
    if r2.status_code == 404:
        raise EapError("CHAT_NOT_FOUND", 404, "聊天室不存在或已逾期,請重新開始對話")
    if r2.status_code != 200:
        raise EapError("EAP_TIMEOUT", 504, f"送出問題失敗 HTTP {r2.status_code}:{r2.text[:150]}")

    ctype = r2.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        answer = _parse_sse(r2.text)
    else:
        try:
            answer = _extract_answer(r2.json(), r2.text)
        except ValueError:
            answer = _parse_sse(r2.text) or r2.text

    if env("EAP_DEBUG").lower() == "true":
        print(f"🔍 [EAP原始回應] Content-Type={ctype}")
        print(f"🔍 [EAP原始回應] {r2.text[:600]}")
        print(f"🔍 [取出的答案] {answer[:400]}")

    if not answer.strip():
        raise EapError("LLM_FORMAT_ERROR", 502, f"EAP 回覆為空。原始回應:{r2.text[:200]}")
    return answer


async def _chat_once(client: httpx.AsyncClient, system_prompt: str, user_message: str, session_name: str) -> str:
    """官方規格流程(Gemini Enterprise API v1):建立聊天室 → 送出問題。
       API Base URL 預設 https://cloud.geminidata.com/api/v1"""
    chat_id = await _create_chat(client, session_name)
    return await _send_message(client, chat_id, f"{system_prompt}\n\n---\n\n{user_message}")


async def _chat_mcp(system_prompt: str, user_message: str) -> str:
    """透過 MCP 協定呼叫平台端的問答工具並回傳文字回覆。
    會自動挑選最可能的問答型工具並把 system+user 合併為一個訊息參數傳送。
    """
    url = env("EAP_MCP_URL") or "https://cloud.geminidata.com/mcp"
    token = env("EAP_TOKEN")
    tenant = env_ascii("EAP_TENANT") or tenant_from_token(token)

    async with _mcp.McpSession(url, token, tenant or "") as s:
        tools = await s.list_tools()
        tool = _mcp.pick_tool(tools)
        if not tool:
            raise _mcp.McpError("找不到可用工具", "")
        message = f"{system_prompt}\n\n---\n\n{user_message}"
        args = _mcp.build_arguments(tool, message)
        return await s.call_tool(tool.get("name") or tool.get("id"), args)


async def call_chat(system_prompt: str, user_message: str, session_name: str = "Credit-Lens 審查") -> dict:
    """呼叫 EAP,回傳解析後的 JSON dict。逾時 60 秒、失敗自動重試 1 次(7.3)。"""
    transport = (env("EAP_TRANSPORT") or "auto").lower()
    last_err: EapError | None = None
    for _ in range(2):  # 首次 + 重試 1 次
        try:
            if transport == "mcp":
                try:
                    return unwrap(repair_json(await _chat_mcp(system_prompt, user_message)))
                except _mcp.McpError as e:
                    raise EapError("EAP_TIMEOUT", 504, f"MCP 呼叫失敗:{e.message} {e.detail[:120]}")
            async with httpx_ssl.client(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
                reply = await _chat_once(client, system_prompt, user_message, session_name)
                return unwrap(repair_json(reply))
        except httpx.TimeoutException:
            last_err = EapError("EAP_TIMEOUT", 504, "EAP 平台回應逾時,請重試")
        except httpx.HTTPError as e:
            last_err = EapError("EAP_TIMEOUT", 504, f"EAP 連線失敗({type(e).__name__}: {e})")
        except EapError as e:
            last_err = e
    raise last_err


async def ask_agent(agent: str, user_message: str, session_name: str = "Credit-Lens 審查") -> dict:
    """agent = prompts/ 下的檔名(finance/tech/judge/pre_brief/assess/extract/score)"""
    return await call_chat(load_prompt(agent), user_message, session_name)


# ============================================================
# 自由問答(知識問答頁使用)
# 與 call_chat 的差別:
#   · 不套 Agent 提示詞、不強制 JSON,回傳平台原始文字
#   · 保留 chat_id,同一串對話沿用同一個聊天室,平台端才有上下文
#   · 不自動重試(互動式操作由使用者自行決定是否重送)
# ============================================================
CONSULT_PROMPT = (
    "你是本知識庫的授信情資助理,服務對象為銀行授信人員(AO)。"
    "請依知識庫中查得的資料回答,並在敘述中標明資料來源或欄位名稱;"
    "知識庫查無相關資料時,直接說明查無,不要臆測或自行補充外部資訊。"
    "回答使用繁體中文,以條列或短段落呈現,避免冗長開場白。"
)


async def chat_raw(message: str, chat_id: str = "", session_name: str = "知識問答") -> dict:
    """自由問答。chat_id 為空時建立新聊天室,否則沿用既有對話。
    回傳 {"chat_id": ..., "reply": ..., "new_session": bool}"""
    if not message.strip():
        raise EapError("INVALID_REQUEST", 422, "提問內容不可為空")

    async with httpx_ssl.client(timeout=httpx.Timeout(75.0, connect=15.0)) as client:
        new_session = not chat_id
        try:
            try:
                if new_session:
                    # 首則訊息附上角色設定,後續同一聊天室沿用平台端上下文
                    chat_id = await _create_chat(client, session_name)
                    question = f"{CONSULT_PROMPT}\n\n---\n\n{message}"
                else:
                    question = message
                reply = await _send_message(client, chat_id, question)
            except EapError as e:
                # 舊聊天室失效:改開新的重送一次,避免使用者手動重整
                if e.code != "CHAT_NOT_FOUND" or new_session:
                    raise
                chat_id = await _create_chat(client, session_name)
                reply = await _send_message(client, chat_id, f"{CONSULT_PROMPT}\n\n---\n\n{message}")
                new_session = True
        except httpx.TimeoutException:
            raise EapError("EAP_TIMEOUT", 504, "EAP 平台回應逾時,請重試或縮短提問")
        except httpx.HTTPError as e:
            raise EapError("EAP_TIMEOUT", 504, f"EAP 連線失敗({type(e).__name__}: {e})")

    return {"chat_id": chat_id, "reply": reply.strip(), "new_session": new_session}


def status() -> dict:
    """連線狀態(供前端頁首顯示)。只回傳可公開的中繼資訊,不外洩 Token。"""
    import base64
    import time

    token = env("EAP_TOKEN")
    out = {
        "configured": bool(token),
        "base": api_base(),
        "tenant": env_ascii("EAP_TENANT") or (tenant_from_token(token) if token else ""),
        "project_id_set": bool(env("EAP_PROJECT_ID")),
        "expires_at": "",
        "expired": None,
        "hours_left": None,
    }
    if not token:
        return out
    try:
        p = token.split(".")[1]
        p += "=" * (-len(p) % 4)
        exp = json.loads(base64.urlsafe_b64decode(p)).get("exp")
        if exp:
            left = int(exp) - int(time.time())
            out["expires_at"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(exp)))
            out["expired"] = left <= 0
            out["hours_left"] = max(0, left // 3600)
    except (IndexError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return out