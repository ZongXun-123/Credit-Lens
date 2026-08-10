<script setup>
// 頁籤 3:拜訪中提詞
// 提問單來源 = 5.7 /api/pre/brief;判定來源 = 5.8 /api/interview/assess
import { ref, computed, onMounted, onUnmounted } from "vue";
import { VERDICT, focusRing, num } from "../constants.js";
import { reviewApi } from "../api.js";
import { MOCK } from "../mock.js";

const props = defineProps({ c: { type: Object, required: true } });

const qs = ref([]);
onMounted(async () => {
  try {
    const brief = await reviewApi("/api/pre/brief",
      { company_id: props.c.id, company_code: props.c.code || "", company_name: props.c.name },
      { radar: MOCK.radar, questions: MOCK.questions }, 600);
    qs.value = brief.questions.map((q) => ({ ...q, status: q.id === 1 ? "active" : "pending" }));
  } catch (e) { qs.value = []; }
});
const activeId = ref(1);
const answerInput = ref("");
const busy = ref(false);
const res = ref(null);
const rec = ref(false);
let recTimer = null;

const activeQ = computed(() => qs.value.find((q) => q.id === activeId.value));
const doneCount = computed(() => qs.value.filter((q) => q.status === "resolved").length);

function pickQ(id) { activeId.value = id; answerInput.value = ""; res.value = null; }

function assess(answer) {
  if (/(已簽|簽約|核貸|承諾函|保證)/.test(answer))
    return { verdict: "resolved", reason: "客戶提出具法律效力之資金承諾,量級相符,風險點視為化解。", follow: "建議索取文件副本附入審查報告。" };
  if (/(意向|洽談|規劃|預計|評估|募資|B輪|b輪)/.test(answer))
    return { verdict: "partial", reason: "提出資金方向但屬意向性質、未具約束力,時程未完全對上。", follow: "追問:意向書是否具法律約束力?交割時點?募資延遲的備援方案?" };
  return { verdict: "unresolved", reason: "回答未提出具體來源或時程,風險點未化解。", follow: "追問:請以數字說明缺口金額、資金來源、到位時間三項。" };
}

function toggleRec() {
  if (rec.value) { clearInterval(recTimer); rec.value = false; return; }
  const demo = "我們已取得兩家創投的B輪投資意向書,預計第四季完成募資,金額約八億。";
  let i = 0; answerInput.value = ""; rec.value = true;
  recTimer = setInterval(() => {
    i += 3; answerInput.value = demo.slice(0, i);
    if (i >= demo.length) { clearInterval(recTimer); rec.value = false; }
  }, 80);
}
onUnmounted(() => clearInterval(recTimer));

async function submitAnswer() {
  if (!answerInput.value.trim() || busy.value) return;
  busy.value = true; res.value = null;
  try {
    // 5.8 Request:company_id + question_id + question + answer
    const out = await reviewApi("/api/interview/assess",
      { company_id: props.c.id, question_id: activeId.value, question: activeQ.value.q, answer: answerInput.value },
      assess(answerInput.value), 1400); // USE_MOCK 時以本地規則模擬判定
    res.value = out;
    qs.value = qs.value.map((q) => (q.id === activeId.value ? { ...q, status: out.verdict } : q));
  } catch (e) {
    res.value = { verdict: "unresolved", reason: `判定失敗(${e.code}):${e.message}`, follow: "請重試。" };
  }
  busy.value = false;
}
</script>

<template>
  <div class="grid lg:grid-cols-5 gap-4">
    <!-- 左:風險點清單(政府列表風) -->
    <div class="lg:col-span-2">
      <h3 class="text-sm font-bold text-slate-900 border-l-4 border-sky-800 pl-2 mb-2">
        風險點清單(已化解 <span :class="num">{{ doneCount }}/{{ qs.length }}</span>)
      </h3>
      <div v-if="qs.length === 0" class="border border-slate-300 bg-white p-6 text-sm text-slate-500">載入提問單中<span class="animate-pulse" aria-hidden="true"> …</span></div>
      <ul v-else class="border-t-2 border-sky-900">
        <li v-for="q in qs" :key="q.id" class="border-b border-slate-300">
          <button @click="pickQ(q.id)" :aria-current="q.id === activeId ? 'true' : undefined"
            :class="[`w-full text-left px-3 py-2.5 text-sm flex items-center gap-2 motion-safe:transition-colors ${focusRing}`,
              q.id === activeId ? 'bg-sky-900 text-white' : 'bg-white hover:bg-sky-50 text-slate-800']">
            <span :class="`${num} font-bold shrink-0`">Q{{ q.id }}</span>
            <span class="flex-1 min-w-0 truncate">{{ q.dim }}</span>
            <span v-if="VERDICT[q.status]"
              :class="['text-xs px-1.5 py-0.5 border rounded-sm shrink-0', q.id === activeId ? 'bg-white' : '', VERDICT[q.status].cls]">
              {{ VERDICT[q.status].label }}
            </span>
            <span v-else :class="['text-xs shrink-0', q.id === activeId ? 'text-sky-200' : 'text-slate-400']">
              {{ q.id === activeId ? "進行中" : "待提問" }}
            </span>
          </button>
        </li>
      </ul>
      <p class="text-xs text-slate-500 mt-2 leading-relaxed">
        行動版介面同步提供;面談時輸入客戶回答,AI 即時判定風險是否化解。
      </p>
    </div>

    <!-- 右:提問與判定 -->
    <div class="lg:col-span-3 space-y-3" v-if="activeQ">
      <div class="bg-white border border-slate-300 border-l-4 border-l-sky-600 p-4">
        <div :class="`text-xs text-sky-900 font-bold mb-1 ${num}`">問題 {{ activeQ.id }}/{{ qs.length }} · {{ activeQ.dim }}</div>
        <p class="text-sm text-slate-900 leading-relaxed font-medium">{{ activeQ.q }}</p>
        <p class="mt-1.5 text-xs text-slate-500 leading-relaxed">AI 出題依據:{{ activeQ.why }}</p>
      </div>

      <div class="bg-white border border-slate-300 p-4">
        <div class="text-xs text-slate-600 mb-1.5 flex items-center justify-between">
          <label for="ans" class="font-bold">客戶回答(輸入或口述)</label>
          <span v-if="rec" class="text-rose-700 motion-safe:animate-pulse">● 語音轉文字中…</span>
        </div>
        <textarea id="ans" v-model="answerInput" rows="3"
          placeholder="請輸入客戶的回答,或按「語音輸入」口述…" spellcheck="false"
          :class="`w-full border border-slate-300 p-2.5 text-sm text-slate-800 resize-none placeholder-slate-400 rounded-sm focus:border-sky-700 ${focusRing}`" />
        <div class="flex gap-2 mt-2">
          <button @click="toggleRec"
            :class="[`px-4 h-10 text-sm font-bold rounded-sm border motion-safe:transition-colors ${focusRing}`,
              rec ? 'bg-rose-700 border-rose-700 text-white' : 'bg-white border-slate-400 text-slate-700 hover:bg-slate-100']">
            {{ rec ? "停止" : "語音輸入" }}
          </button>
          <button @click="submitAnswer" :disabled="busy || !answerInput.trim()"
            :class="`flex-1 h-10 text-sm font-bold text-white bg-sky-900 hover:bg-sky-800 disabled:bg-slate-300 disabled:text-slate-500 rounded-sm motion-safe:transition-colors ${focusRing}`">
            {{ busy ? "AI 判定中…" : "送出判定" }}
          </button>
        </div>
      </div>

      <div v-if="busy" class="bg-white border border-slate-300 p-3.5 text-sm text-slate-500" aria-live="polite">
        風險審查官比對回答與風險點中<span class="animate-pulse" aria-hidden="true"> …</span>
      </div>
      <div v-if="res" aria-live="polite"
        :class="['border border-l-4 p-4 motion-safe:animate-[fadeUp_.35s_ease-out]', VERDICT[res.verdict].cls,
          res.verdict === 'resolved' ? 'border-l-emerald-600' : res.verdict === 'partial' ? 'border-l-amber-500' : 'border-l-rose-600']">
        <div class="font-bold text-sm mb-1.5">判定結果:{{ VERDICT[res.verdict].label }}</div>
        <p class="text-sm text-slate-800 leading-relaxed mb-2">{{ res.reason }}</p>
        <div class="bg-white border border-slate-300 p-2.5 text-sm leading-relaxed">
          <span class="font-bold text-sky-900">建議追問:</span>
          <span class="text-slate-800"> {{ res.follow }}</span>
        </div>
      </div>
    </div>
  </div>
</template>