<script setup>
// 頁籤 1:AI 審查會議(phase 狀態機 7.1:idle/finance/tech/judge/done)
import { ref, reactive, computed, nextTick, onMounted, watch, onUnmounted } from "vue";
import { AGENT, SEVERITY, focusRing, num } from "../constants.js";
import { reviewApi } from "../api.js";
import { MOCK } from "../mock.js";
import { store, setJudge } from "../store.js";
import WaterfallChart from "./WaterfallChart.vue";
import RecordBar from "./RecordBar.vue";
import LoadingCard from "./LoadingCard.vue";

const props = defineProps({ c: { type: Object, required: true } });

const phase = ref("idle");

// 分析階段輪播文字:讓等待期間看得出系統正在做什麼
const FINANCE_STEPS = ["讀取財報欄位", "計算償債能力指標", "評估營運現金流", "整理關鍵發現"];
const TECH_STEPS = ["盤點產品線與藥證", "抓取近期新聞", "評估技術門檻", "整理關鍵發現"];
const JUDGE_STEPS = ["比對兩份結論", "尋找矛盾點", "計算評分瀑布", "撰寫裁決"];
const stepIdx = ref(0);
let stepTimer = null;
watch(() => phase.value, (v) => {
  clearInterval(stepTimer);
  stepIdx.value = 0;
  if (v !== "idle" && v !== "done") stepTimer = setInterval(() => (stepIdx.value += 1), 1700);
});
onUnmounted(() => clearInterval(stepTimer));
const r = reactive({ finance: null, tech: null, judge: null });
const err = ref(null);
const committeeEnd = ref(null);
const busy = computed(() => phase.value !== "idle" && phase.value !== "done");

function scrollToEnd() { nextTick(() => committeeEnd.value?.scrollIntoView({ behavior: "smooth", block: "nearest" })); }

const cid = computed(() => props.c.code || props.c.id);
const judgeMeta = computed(() => r.judge?._rec_id
  ? { recId: r.judge._rec_id, cachedAt: r.judge._cached_at, fromCache: !!r.judge._from_cache, pinned: !!r.judge._pinned }
  : null);

// 裁決結果一律反映畫面上當下的財務／技術結果,故不提供歷次紀錄挑選。
// 上游兩位 Agent 有任何變動時,由 refreshJudge() 自動重跑並同步 store。

// v1.3 進頁自動載入:後端快取優先,有既有結果會秒回且不打 EAP;完全沒有紀錄時維持待命
onMounted(() => { if (!r.judge) run(false, false); });

// v1.6 各 Agent 可單獨重跑:整場會議要跑三次 EAP 呼叫,只想重跑其中一位時不必全部重來
const soloBusy = ref("");           // "finance" | "tech" | "judge" | ""
const metaOf = (x) => (x?._rec_id
  ? { recId: x._rec_id, cachedAt: x._cached_at, fromCache: !!x._from_cache, pinned: !!x._pinned }
  : null);
const financeMeta = computed(() => metaOf(r.finance));
const techMeta = computed(() => metaOf(r.tech));

async function runOne(which, force = true) {
  if (soloBusy.value || busy.value) return;
  soloBusy.value = which;
  err.value = null;
  try {
    const req = { company_id: props.c.id, company_name: props.c.name, company_code: props.c.code || "", force };
    if (which === "finance") {
      r.finance = await reviewApi("/api/review/finance", req, MOCK.finance);
      await refreshJudge();                       // 上游變動 → 裁決與基準分同步重算
    } else if (which === "tech") {
      r.tech = await reviewApi("/api/review/tech", req, MOCK.tech);
      await refreshJudge();
    } else {
      if (!r.finance || !r.tech) { alert("請先完成財務與技術分析,審查官才能交叉質詢。"); soloBusy.value = ""; return; }
      await refreshJudge();
    }
  } catch (e) { err.value = { ...e, stage: which }; }
  soloBusy.value = "";
}

// 重跑審查官:一律以畫面上當下的財務／技術結果為輸入,force 確保不吃舊快取。
// 這是「衍生結果不得與素材脫節」的關鍵:上游一變,裁決與拜訪後基準分立刻跟著更新。
const judgeStale = ref(false);
async function refreshJudge() {
  if (!r.finance || !r.tech) return;
  judgeStale.value = true;
  soloBusy.value = "judge";
  try {
    r.judge = await reviewApi("/api/review/judge",
      { company_id: props.c.id, company_code: props.c.code || "", finance_result: r.finance, tech_result: r.tech, force: true },
      MOCK.judge, 2000);
    setJudge(props.c.id, r.judge);
    phase.value = "done";
    judgeStale.value = false;
  } catch (e) {
    err.value = { ...e, stage: "judge" };
  }
  soloBusy.value = "";
}

// 由歷次紀錄面板載入單一 Agent 結果 → 裁決同步重算
async function loadAgent(which, payload) {
  r[which] = payload;
  await refreshJudge();
}

// 覆蓋度標示:coverage="none" 代表知識庫查無,分數不具評價意義
const COVERAGE = {
  none: { label: "資料不足", cls: "bg-slate-100 text-slate-600 border-slate-300" },
  partial: { label: "部分資料", cls: "bg-amber-50 text-amber-800 border-amber-300" },
};
const SENTI = {
  positive: { mark: "＋", cls: "bg-emerald-50 text-emerald-800 border-emerald-300", label: "有利" },
  negative: { mark: "－", cls: "bg-rose-50 text-rose-800 border-rose-300", label: "風險" },
  neutral: { mark: "・", cls: "bg-slate-100 text-slate-600 border-slate-300", label: "中性" },
};

// resume:7.3 已渲染卡片保留,重試從失敗的那一段開始;force:忽略既有紀錄強制重新產製
async function run(resume = false, force = false) {
  err.value = null;
  const req = { company_id: props.c.id, company_name: props.c.name, company_code: props.c.code || "", force }; // 5.3 Request
  if (!resume) { r.finance = null; r.tech = null; r.judge = null; }
  try {
    if (!r.finance) {
      phase.value = "finance"; scrollToEnd();
      r.finance = await reviewApi("/api/review/finance", req, MOCK.finance);   // 5.3
    }
    if (!r.tech) {
      phase.value = "tech"; scrollToEnd();
      r.tech = await reviewApi("/api/review/tech", req, MOCK.tech);            // 5.4
    }
    phase.value = "judge"; scrollToEnd();
    r.judge = await reviewApi("/api/review/judge",
      { company_id: props.c.id, company_code: props.c.code || "", finance_result: r.finance, tech_result: r.tech, force }, // 5.5:前兩支回應原封不動帶入
      MOCK.judge, 2000);
    setJudge(props.c.id, r.judge); // 供拜訪後評分(base_score)與報告(5.6)使用
    phase.value = "done"; scrollToEnd();
  } catch (e) {
    err.value = e;        // 顯示 error.message + 重試按鈕(7.3)
    phase.value = "idle"; // phase 回到 idle(7.3)
    scrollToEnd();
  }
}
</script>

<template>
  <div class="space-y-3">
    <div class="bg-sky-50 border border-sky-200 px-4 py-3 flex items-center justify-between gap-4 flex-wrap">
      <p class="text-sm text-slate-700">由財務、技術兩位分析 Agent 發言,風險審查官交叉質詢後裁決基準分。</p>
      <button @click="run(false, true)" :disabled="busy"
        :class="`px-4 py-2 text-sm font-bold text-white bg-sky-900 hover:bg-sky-800 disabled:bg-slate-300 disabled:text-slate-500 rounded-sm motion-safe:transition-colors ${focusRing}`">
        {{ busy ? "審查進行中…" : phase === "done" ? "重新召開會議" : "召開審查會議" }}
      </button>
    </div>

    <LoadingCard v-if="phase === 'idle' && !r.finance && !err"
      title="正在確認既往審查紀錄"
      :steps="['查詢本機紀錄', '確認知識庫連線', '準備審查委員會']" />

    <div v-if="err" role="alert" class="border border-rose-300 border-l-4 border-l-rose-600 bg-rose-50 p-4 flex items-center justify-between gap-4 flex-wrap">
      <div>
        <div class="font-bold text-rose-800 text-sm mb-0.5">審查中斷({{ err.code }})</div>
        <p class="text-sm text-slate-800 leading-relaxed">{{ err.message }}</p>
      </div>
      <button @click="run(true)"
        :class="`px-5 h-10 text-sm font-bold text-white bg-rose-700 hover:bg-rose-600 rounded-sm motion-safe:transition-colors ${focusRing}`">
        重試
      </button>
    </div>

    <!-- 財務分析 Agent -->
    <div v-if="phase === 'finance' || r.finance"
      :class="`bg-white border border-slate-300 border-l-4 ${AGENT.finance.edge} p-4 motion-safe:animate-[fadeUp_.4s_ease-out]`">
      <div class="flex items-center justify-between gap-x-3 gap-y-1.5 mb-2.5 flex-wrap">
        <span class="flex items-center gap-2 flex-wrap min-w-0">
          <span :class="`font-bold text-sm ${AGENT.finance.text}`">{{ AGENT.finance.name }} Agent</span>
          <span v-if="r.finance && COVERAGE[r.finance.coverage]"
            :class="['text-xs px-1.5 py-0.5 border rounded-sm', COVERAGE[r.finance.coverage].cls]">
            {{ COVERAGE[r.finance.coverage].label }}
          </span>
        </span>
        <span class="flex items-center gap-3 shrink-0">
          <template v-if="r.finance">
            <span v-if="r.finance.coverage === 'none'" class="text-xs text-slate-500">資料不足,未評分</span>
            <span v-else :class="`${num} font-bold text-xl text-amber-800 leading-none`">{{ r.finance.score }}<span class="text-xs text-slate-500 font-normal"> 分</span></span>
            <button @click="runOne('finance')" :disabled="!!soloBusy || busy"
              :class="`px-2.5 h-7 text-xs font-bold text-amber-800 bg-white border border-amber-300 hover:bg-amber-50 disabled:opacity-40 rounded-sm motion-safe:transition-colors ${focusRing}`">
              {{ soloBusy === 'finance' ? "詢問中…" : "再問一次" }}
            </button>
          </template>
        </span>
      </div>
      <div v-if="!r.finance || soloBusy === 'finance'" class="py-1">
        <div class="flex items-center gap-2.5 mb-2.5">
          <span aria-hidden="true" class="flex items-end gap-1 h-4">
            <span v-for="n in 3" :key="n" class="w-1.5 h-full rounded-full bg-amber-600"
              :style="`animation: bar 1s ease-in-out ${(n - 1) * 0.15}s infinite`" />
          </span>
          <span :key="stepIdx" class="text-sm text-slate-600 motion-safe:animate-[fadeUp_.35s_ease-out]">
            {{ FINANCE_STEPS[stepIdx % FINANCE_STEPS.length] }}…
          </span>
        </div>
        <div class="space-y-1.5" aria-hidden="true">
          <div class="shimmer-bar h-2.5 rounded-sm" style="width: 78%" />
          <div class="shimmer-bar h-2.5 rounded-sm" style="width: 92%" />
          <div class="shimmer-bar h-2.5 rounded-sm" style="width: 61%" />
        </div>
      </div>
      <template v-else>

        <div v-for="(f, i) in r.finance.findings" :key="i"
          :class="['mb-2.5 pl-2.5 border-l-2 text-sm leading-relaxed text-slate-800 motion-safe:animate-[slideIn_.35s_ease-out]',
            f.sentiment === 'positive' ? 'border-l-emerald-500' : f.sentiment === 'negative' ? 'border-l-rose-500' : 'border-l-slate-300']"
          :style="{ animationDelay: `${i * 70}ms` }">
          <span :class="['inline-flex items-center gap-0.5 mr-1.5 px-1.5 py-0.5 rounded-sm text-xs border font-bold align-middle',
            SENTI[f.sentiment || 'neutral'].cls]">
            <span aria-hidden="true">{{ SENTI[f.sentiment || 'neutral'].mark }}</span>{{ SENTI[f.sentiment || 'neutral'].label }}
          </span>{{ f.text }}<br />
          <span class="inline-block mt-1 mr-1 px-1.5 py-0.5 rounded-sm text-xs bg-slate-100 text-slate-600 border border-slate-300">資料來源:{{ f.cite }}</span>
          <span v-if="f.confidence != null" :class="`inline-block mt-1 mr-1 px-1.5 py-0.5 rounded-sm text-xs bg-white text-slate-500 border border-slate-300 ${num}`">信心 {{ Math.round(f.confidence * 100) }}%</span>
        </div>
        <RecordBar v-if="r.finance" kind="finance" :cid="cid" :current="financeMeta" :busy="soloBusy === 'finance'"
          hide-refresh class="mt-3" @load="(p) => loadAgent('finance', p)" />
      </template>
    </div>

    <!-- 技術情報 Agent -->
    <div v-if="phase === 'tech' || r.tech"
      :class="`bg-white border border-slate-300 border-l-4 ${AGENT.tech.edge} p-4 motion-safe:animate-[fadeUp_.4s_ease-out]`">
      <div class="flex items-center justify-between gap-x-3 gap-y-1.5 mb-2.5 flex-wrap">
        <span class="flex items-center gap-2 flex-wrap min-w-0">
          <span :class="`font-bold text-sm ${AGENT.tech.text}`">{{ AGENT.tech.name }} Agent</span>
          <span v-if="r.tech && COVERAGE[r.tech.coverage]"
            :class="['text-xs px-1.5 py-0.5 border rounded-sm', COVERAGE[r.tech.coverage].cls]">
            {{ COVERAGE[r.tech.coverage].label }}
          </span>
        </span>
        <span class="flex items-center gap-3 shrink-0">
          <template v-if="r.tech">
            <span v-if="r.tech.coverage === 'none'" class="text-xs text-slate-500">資料不足,未評分</span>
            <span v-else :class="`${num} font-bold text-xl text-cyan-800 leading-none`">{{ r.tech.score }}<span class="text-xs text-slate-500 font-normal"> 分</span></span>
            <button @click="runOne('tech')" :disabled="!!soloBusy || busy"
              :class="`px-2.5 h-7 text-xs font-bold text-cyan-800 bg-white border border-cyan-300 hover:bg-cyan-50 disabled:opacity-40 rounded-sm motion-safe:transition-colors ${focusRing}`">
              {{ soloBusy === 'tech' ? "詢問中…" : "再問一次" }}
            </button>
          </template>
        </span>
      </div>
      <div v-if="!r.tech || soloBusy === 'tech'" class="py-1">
        <div class="flex items-center gap-2.5 mb-2.5">
          <span aria-hidden="true" class="flex items-end gap-1 h-4">
            <span v-for="n in 3" :key="n" class="w-1.5 h-full rounded-full bg-cyan-600"
              :style="`animation: bar 1s ease-in-out ${(n - 1) * 0.15}s infinite`" />
          </span>
          <span :key="stepIdx" class="text-sm text-slate-600 motion-safe:animate-[fadeUp_.35s_ease-out]">
            {{ TECH_STEPS[stepIdx % TECH_STEPS.length] }}…
          </span>
        </div>
        <div class="space-y-1.5" aria-hidden="true">
          <div class="shimmer-bar h-2.5 rounded-sm" style="width: 78%" />
          <div class="shimmer-bar h-2.5 rounded-sm" style="width: 92%" />
          <div class="shimmer-bar h-2.5 rounded-sm" style="width: 61%" />
        </div>
      </div>
      <template v-else>

        <div v-for="(f, i) in r.tech.findings" :key="i"
          :class="['mb-2.5 pl-2.5 border-l-2 text-sm leading-relaxed text-slate-800 motion-safe:animate-[slideIn_.35s_ease-out]',
            f.sentiment === 'positive' ? 'border-l-emerald-500' : f.sentiment === 'negative' ? 'border-l-rose-500' : 'border-l-slate-300']"
          :style="{ animationDelay: `${i * 70}ms` }">
          <span :class="['inline-flex items-center gap-0.5 mr-1.5 px-1.5 py-0.5 rounded-sm text-xs border font-bold align-middle',
            SENTI[f.sentiment || 'neutral'].cls]">
            <span aria-hidden="true">{{ SENTI[f.sentiment || 'neutral'].mark }}</span>{{ SENTI[f.sentiment || 'neutral'].label }}
          </span>{{ f.text }}<br />
          <span class="inline-block mt-1 mr-1 px-1.5 py-0.5 rounded-sm text-xs bg-slate-100 text-slate-600 border border-slate-300">資料來源:{{ f.cite }}</span>
          <span v-if="f.confidence != null" :class="`inline-block mt-1 mr-1 px-1.5 py-0.5 rounded-sm text-xs bg-white text-slate-500 border border-slate-300 ${num}`">信心 {{ Math.round(f.confidence * 100) }}%</span>
        </div>
        <RecordBar v-if="r.tech" kind="tech" :cid="cid" :current="techMeta" :busy="soloBusy === 'tech'"
          hide-refresh class="mt-3" @load="(p) => loadAgent('tech', p)" />
      </template>
    </div>

    <!-- 風險審查官 Agent -->
    <div v-if="phase === 'judge' || r.judge"
      :class="`bg-white border border-slate-300 border-l-4 ${AGENT.judge.edge} p-4 motion-safe:animate-[fadeUp_.4s_ease-out]`">
      <div class="flex items-center justify-between gap-x-3 gap-y-1.5 mb-2.5 flex-wrap">
        <span class="flex items-center gap-2 flex-wrap min-w-0">
          <span :class="`font-bold text-sm ${AGENT.judge.text}`">{{ AGENT.judge.name }} Agent</span>
          <span class="text-xs px-1.5 py-0.5 border border-slate-300 bg-slate-100 text-slate-600 rounded-sm">
            依上方兩位 Agent 即時推導
          </span>
        </span>
        <span class="flex items-center gap-3 shrink-0">
          <span v-if="r.judge" :class="`${num} font-bold text-xl text-rose-800 leading-none`">{{ r.judge.final_score }}<span class="text-xs text-slate-500 font-normal"> 分</span></span>
          <button v-if="r.judge" @click="runOne('judge')" :disabled="!!soloBusy || busy"
            :class="`px-2.5 h-7 text-xs font-bold text-rose-800 bg-white border border-rose-300 hover:bg-rose-50 disabled:opacity-40 rounded-sm motion-safe:transition-colors ${focusRing}`">
            {{ soloBusy === 'judge' ? "詢問中…" : "再問一次" }}
          </button>
        </span>
      </div>
      <p v-if="r.judge && r.judge.base_note" class="text-xs text-slate-500 mb-2">
        基礎分 {{ r.judge.waterfall?.[0]?.value }} 分({{ r.judge.base_note }}),由系統計算後帶入,故同一組素材每次結果一致。
      </p>
      <div v-if="!r.judge || soloBusy === 'judge'" class="py-1">
        <div class="flex items-center gap-2.5 mb-2.5">
          <span aria-hidden="true" class="flex items-end gap-1 h-4">
            <span v-for="n in 3" :key="n" class="w-1.5 h-full rounded-full bg-rose-600"
              :style="`animation: bar 1s ease-in-out ${(n - 1) * 0.15}s infinite`" />
          </span>
          <span :key="stepIdx" class="text-sm text-slate-600 motion-safe:animate-[fadeUp_.35s_ease-out]">
            {{ JUDGE_STEPS[stepIdx % JUDGE_STEPS.length] }}…
          </span>
        </div>
        <div class="space-y-1.5" aria-hidden="true">
          <div class="shimmer-bar h-2.5 rounded-sm" style="width: 85%" />
          <div class="shimmer-bar h-2.5 rounded-sm" style="width: 70%" />
        </div>
      </div>
      <template v-else>
        <!-- 6.3:contradictions 可為空陣列,顯示「無重大矛盾」 -->
        <div v-if="r.judge.contradictions.length === 0" class="text-sm text-slate-700 mb-2.5 border border-emerald-300 bg-emerald-50 p-3">
          交叉質詢完成,無重大矛盾。
        </div>
        <div v-else class="text-sm text-slate-600 mb-2.5">交叉質詢完成,發現 {{ r.judge.contradictions.length }} 項矛盾:</div>
        <div v-for="(x, i) in r.judge.contradictions" :key="i"
          :class="['mb-2 border p-3', (SEVERITY[x.severity] || SEVERITY.medium).box]">
          <div class="text-rose-800 font-bold text-sm mb-1 flex items-center gap-2">
            <span>【矛盾 {{ i + 1 }}】{{ x.title }}</span>
            <span :class="['text-xs font-normal px-1.5 py-0.5 border rounded-sm', (SEVERITY[x.severity] || SEVERITY.medium).chip]">
              嚴重度:{{ (SEVERITY[x.severity] || SEVERITY.medium).label }}
            </span>
          </div>
          <div class="text-sm text-slate-800 leading-relaxed">{{ x.detail }}</div>
        </div>
        <div class="mt-3 text-sm leading-relaxed text-slate-900 bg-slate-50 border border-slate-200 p-3">
          <span class="font-bold text-rose-800">裁決:</span>{{ r.judge.verdict }}
        </div>
      </template>
    </div>

    <!-- 拜訪前基準評分(瀑布圖) -->
    <div v-if="phase === 'done' && r.judge" class="bg-white border border-slate-300 border-t-4 border-t-sky-900 p-4 motion-safe:animate-[fadeUp_.4s_ease-out]">
      <h3 class="font-bold text-slate-900 mb-3">拜訪前基準評分</h3>
      <WaterfallChart :items="r.judge.waterfall" :final-score="r.judge.final_score" />
    </div>
    <div ref="committeeEnd" />
  </div>
</template>