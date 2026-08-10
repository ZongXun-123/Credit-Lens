<script setup>
// 頁面 2:案件詳情(四個工作流頁籤容器)
import { ref } from "vue";
import { TABS, focusRing, num } from "../constants.js";
import { reviewApi, API_BASE } from "../api.js";
import { store } from "../store.js";
import CommitteeTab from "../components/CommitteeTab.vue";
import PreVisitTab from "../components/PreVisitTab.vue";
import PostVisitTab from "../components/PostVisitTab.vue";
import MarketSignalTab from "../components/MarketSignalTab.vue";

const TAB_COMP = { committee: CommitteeTab, pre: PreVisitTab, post: PostVisitTab, market: MarketSignalTab };

// v1.4:於案件頁任何位置皆可產出報告。不需先開審查會議、也不需會議紀錄——
// 後端會自快取資料庫彙整該公司目前已有的分析結果(有幾段印幾段)。
const reporting = ref(false);
async function makeReport() {
  reporting.value = true;
  try {
    const body = { company_id: props.c.id, company_name: props.c.name || "", company_code: props.c.code || "" };
    const judge = store.judgeByCompany[props.c.id];
    if (judge) body.judge_result = judge;      // 本次剛跑過的裁決優先帶入
    const r = await reviewApi("/api/report", body, { report_url: "" }, 800);
    if (r.report_url) window.open(new URL(r.report_url, API_BASE).href, "_blank");
    else alert("離線展示模式:整合後將開啟實際 PDF。");
  } catch (e) {
    alert(e.code === "NO_MATERIAL"
      ? "此公司尚無任何分析結果,無法產出報告。請先執行「AI 審查會議」或「拜訪前情資」。"
      : `產出報告失敗:${e.message}`);
  }
  reporting.value = false;
}

const props = defineProps({ c: { type: Object, required: true } });
const emit = defineEmits(["go-home", "open-intel"]);

const tab = ref("committee");
</script>

<template>
  <main id="main" class="max-w-5xl mx-auto px-4 py-5 w-full">
    <nav aria-label="麵包屑" class="text-sm text-slate-500">
      <ol class="flex items-center gap-1 flex-wrap">
        <li><button @click="emit('go-home')" :class="`text-sky-800 hover:underline underline-offset-2 rounded-sm px-0.5 ${focusRing}`">首頁</button></li>
        <li class="flex items-center gap-1"><span aria-hidden="true" class="text-slate-400 px-0.5">/</span>
          <button @click="emit('go-home')" :class="`text-sky-800 hover:underline underline-offset-2 rounded-sm px-0.5 ${focusRing}`">案件總覽</button></li>
        <li class="flex items-center gap-1"><span aria-hidden="true" class="text-slate-400 px-0.5">/</span><span aria-current="page" class="text-slate-700">{{ c.name }}</span></li>
      </ol>
    </nav>

    <div class="mt-4 mb-4 pb-3 border-b border-slate-300 flex items-end justify-between gap-4 flex-wrap">
      <div>
        <h1 class="text-2xl font-bold text-slate-900">{{ c.name }}</h1>
        <p :class="`text-sm text-slate-500 mt-1 ${num}`">
          <template v-if="c.code">證券代號 {{ c.code }}</template>
          <template v-if="c.ban"><template v-if="c.code"> · </template>統一編號 {{ c.ban }}</template>
          <template v-else-if="c.code"> · <span class="text-amber-700">統編未對照</span></template>
          <template v-else>統一編號 {{ c.id }}</template>
          · {{ c.industry }} · 最近更新 {{ c.updated }}
        </p>
        <button v-if="c.ban || c.name" @click="emit('open-intel', c.ban || c.name)"
          :class="`mt-2 px-3 py-1.5 text-xs font-bold border border-sky-800 text-sky-900 hover:bg-sky-50 rounded-sm motion-safe:transition-colors ${focusRing}`">
          {{ c.ban ? "查詢公開情資(商工登記／藥品許可證／新聞)→" : "以公司名稱查統一編號 →" }}
        </button>
      </div>
      <div class="text-right flex items-end gap-4">
        <div v-if="c.score !== null">
          <div class="text-xs text-slate-500">目前綜合評分</div>
          <span :class="`${num} font-bold text-3xl text-sky-900`">{{ c.score }}<span class="text-xs text-slate-500 font-normal"> 分</span></span>
        </div>
        <div>
          <button @click="makeReport" :disabled="reporting"
            :class="`px-4 h-10 text-sm font-bold text-white bg-sky-900 hover:bg-sky-800 disabled:bg-slate-300 disabled:text-slate-500 rounded-sm motion-safe:transition-colors ${focusRing}`">
            {{ reporting ? "產製中…" : "產出授信報告" }}
          </button>
          <p class="text-xs text-slate-500 mt-1">彙整目前已有的分析結果</p>
        </div>
      </div>
    </div>

    <!-- 頁籤:政府網站常見的方塊型頁籤(作用中=深藍底白字) -->
    <div role="tablist" aria-label="工作流階段" class="flex flex-wrap gap-1 border-b-2 border-sky-900">
      <button v-for="(t, i) in TABS" :key="t.key" role="tab" :aria-selected="tab === t.key" :id="`tab-${t.key}`" :aria-controls="`panel-${t.key}`"
        @click="tab = t.key"
        :class="[`px-4 py-2.5 text-sm rounded-t-sm border border-b-0 motion-safe:transition-colors ${focusRing}`,
          tab === t.key ? 'bg-sky-900 border-sky-900 text-white font-bold' : 'bg-slate-100 border-slate-300 text-slate-700 hover:bg-sky-50 hover:text-sky-900']">
        <span :class="[`${num} mr-1.5`, tab === t.key ? 'text-sky-300' : 'text-slate-400']">{{ i + 1 }}.</span>
        {{ t.label }}
      </button>
    </div>

    <!-- v1.3:KeepAlive 保活 — 切換頁籤時元件狀態保留,回來不會重跑 -->
    <div :key="tab" class="pt-4 pb-2 motion-safe:animate-[fadeUp_.3s_ease-out]" role="tabpanel" :id="`panel-${tab}`" :aria-labelledby="`tab-${tab}`">
      <KeepAlive>
        <component :is="TAB_COMP[tab]" :c="c" :key="`${tab}-${c.id}`" />
      </KeepAlive>
    </div>
  </main>
</template>
