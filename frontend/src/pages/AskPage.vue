<script setup>
// 頁面 5:知識問答(自由對話)
// 直接串 EAP 平台 /chat API 與本專案模型對話,不套 Agent 契約、不強制 JSON。
// 後端端點:/api/eap/chat(送問題)、/api/eap/status(連線狀態)
// chat_id 由本頁保管並隨每次提問回送,平台端才會保留同一串對話的上下文。
import { ref, computed, nextTick, onMounted } from "vue";
import { focusRing, num } from "../constants.js";
import { reviewApi } from "../api.js";

const messages = ref([]);      // { role: 'user'|'ai'|'error', text, ms?, at }
const input = ref("");
const busy = ref(false);
const chatId = ref("");
const status = ref(null);
const thread = ref(null);

const canSend = computed(() => input.value.trim().length > 0 && !busy.value);
const askedCount = computed(() => messages.value.filter((m) => m.role === "user").length);

// 建議提問:對應 EAP 知識圖譜實際具備的欄位(償債能力/獲利能力/成長率指標)
const PRESETS = [
  "這個知識庫涵蓋哪些企業與財務欄位?",
  "列出借款依存度高於 30% 的製藥業者,並附上數值。",
  "營運現金流量為負、且稅後淨利成長率衰退的生技公司有哪些?",
  "以授信角度說明「流動比率」與「速動比率」差距過大代表什麼。",
];

function clock() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

async function scrollDown() {
  await nextTick();
  if (thread.value) thread.value.scrollTop = thread.value.scrollHeight;
}

onMounted(async () => {
  try {
    status.value = await reviewApi("/api/eap/status", {},
      { configured: false, base: "(離線展示)", mock_mode: true }, 200);
  } catch (e) {
    status.value = { configured: false, error: e.message };
  }
});

async function send(text) {
  const q = (text ?? input.value).trim();
  if (!q || busy.value) return;
  input.value = "";
  messages.value.push({ role: "user", text: q, at: clock() });
  busy.value = true;
  await scrollDown();

  const t0 = performance.now();
  try {
    const out = await reviewApi("/api/eap/chat",
      { message: q, chat_id: chatId.value, session_name: "知識問答" },
      { chat_id: "demo-session", new_session: !chatId.value,
        reply: "【示範資料】目前為離線展示模式,本回覆非 EAP 平台實際輸出。" },
      1200);
    chatId.value = out.chat_id || chatId.value;
    messages.value.push({
      role: "ai", text: out.reply, at: clock(),
      ms: Math.round(performance.now() - t0),
    });
  } catch (e) {
    messages.value.push({
      role: "error", at: clock(),
      code: e.code || "INTERNAL_ERROR",
      text: e.message || "呼叫失敗,請重試。",
    });
  }
  busy.value = false;
  await scrollDown();
}

function onKey(e) {
  // Enter 送出、Shift+Enter 換行;輸入法組字中(isComposing)不攔截
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    send();
  }
}

function reset() {
  messages.value = [];
  chatId.value = "";   // 清空後下次提問會在平台端開新的聊天室
  input.value = "";
}
</script>

<template>
  <main id="main" class="max-w-5xl mx-auto px-4 py-6 w-full">
    <nav aria-label="麵包屑" class="text-sm text-slate-500">
      <ol class="flex items-center gap-1 flex-wrap">
        <li>首頁</li>
        <li class="flex items-center gap-1">
          <span aria-hidden="true" class="text-slate-400 px-0.5">/</span>
          <span aria-current="page" class="text-slate-700">知識問答</span>
        </li>
      </ol>
    </nav>

    <div class="mt-4 flex items-end justify-between gap-4 flex-wrap">
      <div>
        <h2 class="border-l-4 border-sky-800 pl-3 text-lg font-bold text-slate-900 flex items-center gap-2">
          知識問答
          <span aria-hidden="true" class="inline-flex items-center gap-1 text-xs font-normal text-sky-800 bg-sky-50 border border-sky-200 rounded-sm px-1.5 py-0.5">
            <span class="w-1.5 h-1.5 rounded-full bg-sky-600 motion-safe:animate-pulse" />即時
          </span>
        </h2>
        <p class="mt-1.5 pl-3 text-sm text-slate-600 leading-relaxed">
          直接向本平台的知識庫模型提問。本頁不套用評分格式,回覆為模型原始輸出,
          供 AO 於審查前後臨時查證使用。
        </p>
      </div>
      <button v-if="messages.length" @click="reset"
        :class="`px-3 h-9 text-sm border border-slate-400 bg-white text-slate-700 hover:bg-slate-100 rounded-sm shrink-0 motion-safe:transition-colors ${focusRing}`">
        清除對話
      </button>
    </div>

    <!-- 連線狀態列 -->
    <div v-if="status" class="mt-4 bg-white border border-slate-300 border-t-4 border-t-sky-900 px-4 py-2.5
                              flex items-center gap-x-5 gap-y-1.5 flex-wrap text-xs">
      <span class="flex items-center gap-1.5 font-bold">
        <span aria-hidden="true"
          :class="['w-2 h-2 rounded-full shrink-0', status.mock_mode ? 'bg-amber-500' : status.configured ? 'bg-emerald-600' : 'bg-rose-600']" />
        <span :class="status.mock_mode ? 'text-amber-800' : status.configured ? 'text-emerald-800' : 'text-rose-800'">
          {{ status.mock_mode ? "離線展示模式" : status.configured ? "已連線 EAP 平台" : "未設定 EAP Token" }}
        </span>
      </span>
      <span class="text-slate-500">端點 <span :class="`${num} text-slate-700`">{{ status.base }}</span></span>
      <span v-if="status.tenant" class="text-slate-500">租戶 <span :class="`${num} text-slate-700`">{{ status.tenant }}</span></span>
      <span v-if="status.expires_at" class="text-slate-500">
        Token 到期
        <span :class="`${num} ${status.expired ? 'text-rose-700 font-bold' : 'text-slate-700'}`">
          {{ status.expires_at }}<template v-if="!status.expired && status.hours_left !== null">(剩 {{ status.hours_left }} 小時)</template>
        </span>
      </span>
      <span v-if="chatId" class="text-slate-500">對話編號 <span :class="`${num} text-slate-700`">{{ chatId.slice(0, 12) }}</span></span>
    </div>

    <div class="mt-4 grid lg:grid-cols-4 gap-4 items-start">
      <!-- 對話區 -->
      <section class="lg:col-span-3 bg-white border border-slate-300" aria-label="對話內容">
        <div ref="thread" class="px-4 py-4 space-y-3 min-h-80 max-h-[28rem] overflow-y-auto" aria-live="polite">
          <!-- 空狀態:引導插畫 -->
          <div v-if="messages.length === 0" class="py-8 text-center motion-safe:animate-[fadeUp_.5s_ease-out]">
            <div aria-hidden="true" class="mx-auto w-20 h-20 mb-3 relative motion-safe:animate-[floaty_3.4s_ease-in-out_infinite]">
              <svg viewBox="0 0 80 80" class="w-20 h-20">
                <circle cx="40" cy="40" r="30" class="fill-sky-50 stroke-sky-200" stroke-width="1.5" />
                <g class="stroke-sky-800" stroke-width="2.4" fill="none" stroke-linecap="round">
                  <circle cx="36" cy="36" r="13" />
                  <path d="m47 47 9 9" />
                  <path d="M31 36h10M36 31v10" />
                </g>
                <circle v-for="(d, i) in [[16,20],[64,26],[20,60],[62,58]]" :key="i"
                  :cx="d[0]" :cy="d[1]" r="2.5" class="fill-sky-300"
                  :style="`animation: dotBounce 2s ease-in-out ${i * 0.25}s infinite`" />
              </svg>
            </div>
            <p class="text-sm font-medium text-slate-700">向知識庫提問</p>
            <p class="mt-1 text-xs text-slate-500 leading-relaxed max-w-sm mx-auto">
              可查詢企業財務指標、比較同業表現,或請模型說明某項指標的授信意涵。
              直接輸入問題,或點選右側的建議提問開始。
            </p>
          </div>

          <div v-for="(m, i) in messages" :key="i" class="motion-safe:animate-[fadeUp_.3s_ease-out]">
            <!-- 使用者 -->
            <div v-if="m.role === 'user'" class="flex justify-end items-start gap-2">
              <div class="max-w-[85%] bg-slate-100 border border-slate-300 rounded-sm px-3 py-2 hover-lift">
                <div :class="`text-xs text-slate-500 mb-0.5 ${num}`">授信人員 · {{ m.at }}</div>
                <p class="text-sm text-slate-900 leading-relaxed whitespace-pre-wrap">{{ m.text }}</p>
              </div>
              <span aria-hidden="true" class="shrink-0 w-7 h-7 grid place-items-center rounded-sm bg-slate-600 text-white text-xs font-bold mt-0.5">AO</span>
            </div>

            <!-- 模型回覆 -->
            <div v-else-if="m.role === 'ai'" class="bg-white border border-slate-300 border-l-4 border-l-sky-700 px-3.5 py-2.5 hover-lift">
              <div class="flex items-center justify-between gap-3 mb-1 flex-wrap">
                <span class="text-xs font-bold text-sky-900 flex items-center gap-1.5">
                  <span aria-hidden="true" class="w-5 h-5 grid place-items-center rounded-sm bg-sky-900 text-white text-[9px]">AI</span>
                  智貸先鋒 · EAP 知識庫
                </span>
                <span :class="`text-xs text-slate-400 ${num}`">
                  {{ m.at }}<template v-if="m.ms"> · 回應 {{ (m.ms / 1000).toFixed(1) }} 秒</template>
                </span>
              </div>
              <p class="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">{{ m.text }}</p>
            </div>

            <!-- 錯誤 -->
            <div v-else class="border border-l-4 border-rose-400 border-l-rose-600 bg-rose-50 px-3.5 py-2.5">
              <div class="text-xs font-bold text-rose-800 mb-0.5">呼叫失敗 · {{ m.code }}</div>
              <p class="text-sm text-rose-900 leading-relaxed">{{ m.text }}</p>
            </div>
          </div>

          <div v-if="busy" class="bg-white border border-slate-300 border-l-4 border-l-sky-700 px-3.5 py-3 motion-safe:animate-[fadeUp_.3s_ease-out]">
            <div class="flex items-center gap-2.5">
              <span aria-hidden="true" class="flex items-end gap-1 h-4">
                <span v-for="n in 3" :key="n" class="w-1.5 h-full bg-sky-700 rounded-full"
                  :style="`animation: bar 1s ease-in-out ${(n - 1) * 0.15}s infinite`" />
              </span>
              <span class="text-sm text-slate-600">正在檢索知識庫並整理回覆…</span>
            </div>
            <div class="mt-2.5 space-y-1.5" aria-hidden="true">
              <div class="shimmer-bar h-2.5 rounded-sm" style="width: 72%" />
              <div class="shimmer-bar h-2.5 rounded-sm" style="width: 88%" />
              <div class="shimmer-bar h-2.5 rounded-sm" style="width: 54%" />
            </div>
          </div>
        </div>

        <!-- 輸入區 -->
        <div class="border-t border-slate-300 p-3 bg-slate-50">
          <label for="ask-input" class="sr-only">提問內容</label>
          <textarea id="ask-input" v-model="input" @keydown="onKey" rows="3" spellcheck="false"
            placeholder="請輸入問題,例如:借款依存度最高的前五家製藥業者是哪幾家?"
            :class="`w-full border border-slate-300 bg-white p-2.5 text-sm text-slate-800 resize-none placeholder-slate-400 rounded-sm focus:border-sky-700 ${focusRing}`" />
          <div class="flex items-center justify-between gap-3 mt-2 flex-wrap">
            <span class="text-xs text-slate-500">
              Enter 送出、Shift + Enter 換行<template v-if="askedCount"> · 本次已提問 <span :class="num">{{ askedCount }}</span> 則</template>
            </span>
            <button @click="send()" :disabled="!canSend"
              :class="`px-6 h-10 text-sm font-bold text-white bg-sky-900 hover:bg-sky-800 disabled:bg-slate-300 disabled:text-slate-500 rounded-sm motion-safe:transition-colors ${focusRing}`">
              {{ busy ? "查詢中…" : "送出提問" }}
            </button>
          </div>
        </div>
      </section>

      <!-- 側欄:建議提問與說明 -->
      <aside class="space-y-4">
        <div class="bg-white border border-slate-300">
          <h3 class="text-sm font-bold text-slate-900 border-b border-slate-300 bg-slate-100 px-3 py-2">建議提問</h3>
          <ul class="p-2 space-y-1.5">
            <li v-for="(p, i) in PRESETS" :key="i">
              <button @click="send(p)" :disabled="busy"
                :style="{ animationDelay: `${i * 70}ms` }"
                :class="`w-full text-left text-xs leading-relaxed text-slate-700 border border-slate-300 rounded-sm px-2.5 py-2
                         hover:bg-sky-50 hover:border-sky-400 hover:text-sky-900 disabled:opacity-50 disabled:hover:bg-white
                         motion-safe:transition-all hover:translate-x-0.5 motion-safe:animate-[fadeUp_.4s_ease-out] group ${focusRing}`">
                <span aria-hidden="true" class="inline-block w-4 text-slate-400 group-hover:text-sky-600 font-bold">{{ i + 1 }}</span>
                {{ p }}
              </button>
            </li>
          </ul>
        </div>

        <div class="bg-white border border-slate-300 border-l-4 border-l-slate-400 px-3 py-2.5">
          <h3 class="text-xs font-bold text-slate-900 mb-1.5">使用說明</h3>
          <ul class="text-xs text-slate-600 leading-relaxed space-y-1 list-disc list-inside">
            <li>同一頁內連續提問會沿用同一組對話編號,模型可延續前文。</li>
            <li>按「清除對話」會另開新的對話,前文不再納入。</li>
            <li>本頁回覆未經風險審查官交叉驗證,不得單獨作為授信依據。</li>
          </ul>
        </div>
      </aside>
    </div>
  </main>
</template>
