<script setup>
// 頁面 5:市場訊號(生技製藥 36 家同業排行)
// 資料來源 = 股價市場訊號模組 §6.3 POST /api/market/universe
import { ref, computed, onMounted } from "vue";
import { focusRing, num } from "../constants.js";
import { reviewApi } from "../api.js";

const emit = defineEmits(["open-case"]);

const data = ref(null);
const loading = ref(true);
const filter = ref("全部");
const FILTERS = ["全部", "低風險", "中等", "偏高風險", "資料不足"];

onMounted(async () => {
  try {
    data.value = await reviewApi("/api/market/universe", {}, null, 300);
  } catch (e) { data.value = null; }
  loading.value = false;
});

const LEVEL = {
  "低風險":   { text: "text-emerald-700", bar: "bg-emerald-600", chip: "bg-emerald-50 text-emerald-800 border-emerald-400" },
  "中等":     { text: "text-amber-700",   bar: "bg-amber-500",   chip: "bg-amber-50 text-amber-800 border-amber-400" },
  "偏高風險": { text: "text-rose-700",    bar: "bg-rose-600",    chip: "bg-rose-50 text-rose-800 border-rose-400" },
  "資料不足": { text: "text-slate-400",   bar: "bg-slate-300",   chip: "bg-slate-100 text-slate-500 border-slate-300" },
};

const rows = computed(() => {
  const all = data.value?.companies || [];
  return filter.value === "全部" ? all : all.filter((c) => c.level === filter.value);
});

const stats = computed(() => {
  const all = data.value?.companies || [];
  const cnt = (lv) => all.filter((c) => c.level === lv).length;
  const scored = all.filter((c) => c.market_score !== null);
  return [
    ["母體家數", `${data.value?.universe ?? "—"} 家`],
    ["低風險", `${cnt("低風險")} 家`],
    ["偏高風險", `${cnt("偏高風險")} 家`],
    ["平均分數", scored.length ? `${Math.round(scored.reduce((a, c) => a + c.market_score, 0) / scored.length)} 分` : "—"],
  ];
});

function openCase(c) {
  emit("open-case", {
    id: c.ban || `code:${c.company_id}`, code: c.company_id, ban: c.ban || null,
    name: c.company_name, industry: data.value?.industry || "生技製藥",
    stage: "pre", score: c.market_score, updated: "—", level: c.level, tier: c.tier,
  });
}
const fmt = (v, unit = "") => v == null ? "—" : `${v}${unit}`;
</script>

<template>
  <main id="main" class="max-w-5xl mx-auto px-4 py-6 w-full">
    <nav aria-label="麵包屑" class="text-sm text-slate-500">
      <ol class="flex items-center gap-1 flex-wrap">
        <li>首頁</li>
        <li class="flex items-center gap-1"><span aria-hidden="true" class="text-slate-400 px-0.5">/</span><span aria-current="page" class="text-slate-700">市場訊號</span></li>
      </ol>
    </nav>

    <div class="mt-4 mb-3">
      <h2 class="border-l-4 border-sky-800 pl-3 text-lg font-bold text-slate-900 mb-1">股價市場訊號 · 同業排行</h2>
      <p class="text-sm text-slate-600">
        以整體資本市場對企業的評價作為授信補強訊號。分數越高代表市場風險評價越低(同業相對)。
        <span v-if="data" :class="`${num} text-slate-500`">{{ data.industry }} · {{ data.period }}</span>
      </p>
    </div>

    <div v-if="loading" class="bg-white border border-slate-300 p-10 text-center text-sm text-slate-500" aria-live="polite">
      <span class="inline-block w-2 h-2 rounded-full bg-sky-700 motion-safe:animate-ping mr-2" aria-hidden="true" />載入市場訊號中…
    </div>

    <div v-else-if="!data" class="border border-rose-300 border-l-4 border-l-rose-600 bg-rose-50 p-4 text-sm text-slate-800">
      無法載入市場訊號資料。請確認後端 <span class="font-mono">backend/data/market_signal.json</span> 是否存在。
    </div>

    <template v-else>
      <div class="grid sm:grid-cols-4 gap-3">
        <div v-for="([k, v], i) in stats" :key="k"
          class="bg-white border border-slate-300 border-t-4 border-t-sky-900 px-4 py-3 motion-safe:animate-[fadeUp_.4s_ease-out]"
          :style="{ animationDelay: `${i * 60}ms` }">
          <div class="text-xs text-slate-500">{{ k }}</div>
          <div :class="`${num} font-bold text-2xl text-sky-900 mt-0.5`">{{ v }}</div>
        </div>
      </div>

      <div class="flex items-center justify-between gap-4 mt-6 mb-3 flex-wrap">
        <h3 class="border-l-4 border-sky-800 pl-3 text-base font-bold text-slate-900">排行(共 {{ rows.length }} 家)</h3>
        <div class="flex gap-1 flex-wrap">
          <button v-for="f in FILTERS" :key="f" @click="filter = f"
            :class="['px-3 h-8 text-xs rounded-sm border motion-safe:transition-colors', focusRing,
              filter === f ? 'bg-sky-900 border-sky-900 text-white font-bold' : 'bg-white border-slate-300 text-slate-600 hover:bg-sky-50']">
            {{ f }}
          </button>
        </div>
      </div>

      <ul class="border-t-2 border-sky-900">
        <li v-for="(c, i) in rows" :key="c.company_id" class="border-b border-slate-300">
          <button @click="openCase(c)"
            :class="`w-full text-left bg-white hover:bg-sky-50 px-4 py-3 flex items-center gap-4 flex-wrap motion-safe:transition-colors group motion-safe:animate-[fadeUp_.35s_ease-out] ${focusRing}`"
            :style="{ animationDelay: `${Math.min(i, 12) * 25}ms` }">
            <span :class="`${num} text-sm text-slate-400 w-7 shrink-0`">{{ i + 1 }}</span>
            <span :class="`${num} text-xs text-slate-500 w-12 shrink-0`">{{ c.company_id }}</span>
            <span class="min-w-28 flex-1">
              <span class="text-slate-900 font-medium group-hover:text-sky-900 group-hover:underline underline-offset-2">{{ c.company_name }}</span>
              <span :class="`block text-xs text-slate-400 mt-0.5 ${num}`">
                <template v-if="c.ban">統編 {{ c.ban }}</template>
                <template v-else>統編未對照</template>
              </span>
            </span>

            <span class="hidden md:flex items-center gap-4 text-xs text-slate-500 w-64 shrink-0">
              <span :class="num">波動 {{ fmt(c.summary.vol_full_pct, "%") }}</span>
              <span :class="num">回撤 {{ fmt(c.summary.mdd_pct, "%") }}</span>
              <span :class="`${num} ${(c.summary.mom_1y_pct || 0) >= 0 ? 'text-emerald-700' : 'text-rose-700'}`">
                年報酬 {{ fmt(c.summary.mom_1y_pct, "%") }}
              </span>
            </span>

            <span class="w-28 shrink-0 hidden sm:block">
              <span class="block h-2 bg-slate-100 border border-slate-200 overflow-hidden rounded-sm">
                <span :class="['block h-full motion-safe:transition-[width] motion-safe:duration-700', LEVEL[c.level].bar]"
                  :style="{ width: `${c.market_score || 0}%` }" />
              </span>
            </span>
            <span class="w-14 text-right shrink-0">
              <span :class="`${num} font-bold text-lg ${LEVEL[c.level].text}`">{{ c.market_score === null ? "—" : c.market_score }}</span>
            </span>
            <span :class="['text-xs px-1.5 py-0.5 border rounded-sm shrink-0 w-20 text-center', LEVEL[c.level].chip]">{{ c.level }}</span>
          </button>
        </li>
      </ul>

      <p class="text-xs text-slate-500 mt-3 leading-relaxed">
        註:本模組為同業相對風險評分,並非違約機率預測,須與內部財務／負債資料合併判讀。
        歷史交易日不足 60 日者不予評分。點擊任一列可開啟該企業的授信案件。
      </p>
    </template>
  </main>
</template>
