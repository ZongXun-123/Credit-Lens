// ============================================================
// [API] 呼叫層(規格書 5.1 / 5.2 / 7.3)
// USE_MOCK=true:開發與 Demo 保險絲,回傳內建範例 JSON
// 整合日:改為 false,並以環境變數 VITE_API_BASE 指向後端
// ============================================================
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export const USE_MOCK = false;   // 預設 false:直接呼叫後端 API(改 true 可脫離後端獨立展示)

export const API_BASE =
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_BASE) || "http://localhost:8000";

export async function callApi(path, body) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 90_000); // 前端逾時 90 秒(5.1)
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      // 統一錯誤格式(5.2):非 200 一律解析 error.code / error.message
      throw {
        code: data?.error?.code || "INTERNAL_ERROR",
        message: data?.error?.message || "系統發生未預期錯誤,請重試。",
      };
    }
    return data;
  } catch (e) {
    if (e?.name === "AbortError") throw { code: "EAP_TIMEOUT", message: "系統回應逾時,請重試。" };
    if (e?.code) throw e;
    throw { code: "INTERNAL_ERROR", message: "無法連線至後端服務,請確認網路後重試。" };
  } finally {
    clearTimeout(timer);
  }
}

// Mock 模式與真實 API 的統一入口:整合日不需改動各元件
export async function reviewApi(path, body, mock, mockDelay = 1800) {
  if (USE_MOCK) { await sleep(mockDelay); return mock; }
  return callApi(path, body);
}
