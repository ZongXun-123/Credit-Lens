<script setup>
// 頁籤 5:市場訊號(股價市場訊號模組 產品說明書 v1.0 §8)
// 資料來源 = 6.2 POST /api/market/signal;沿用 v1.1 §7.2 色票與 §9.4 瀑布圖規則
import { ref, computed, onMounted, watch } from "vue";
import { focusRing, num } from "../constants.js";
import { reviewApi } from "../api.js";
import WaterfallChart from "./WaterfallChart.vue";
import RecordBar from "./RecordBar.vue";
import LoadingCard from "./LoadingCard.vue";

const props = defineProps({ c: { type: Object, required: true } });

const data = ref(null);
const loadErr = ref(null);
const loading = ref(false);

// EAP 財報交叉解讀(選用):量化分數不變,只把文字解讀換成 EAP 依知識庫財報產生的版本
const eapRead = ref(null);
const eapReadErr = ref(null);
const eapBusy = ref(false);
const eapMeta = computed(() => eapRead.value?._rec_id
  ? { recId: eapRead.value._rec_id, cachedAt: eapRead.value._cached_at, fromCache: !!eapRead.value._from_cache, pinned: !!eapRead.value._pinned }
  : null);

async function loadEapRead(force = false) {
  eapBusy.value = true; eapReadErr.value = null;
  try {
    const out = await reviewApi("/api/market/eap_read",
      { company_id: props.c.code || props.c.id, company_name: props.c.name, force },
      { summary: ["【示範資料】離線展示模式,非 EAP 實際交叉解讀。"], recommendation: "【示範資料】", cites: [], _degraded: true },
      1500);
    eapRead.value = out;
  } catch (e) { eapReadErr.value = e; }
  eapBusy.value = false;
}

// 進頁時查一下有沒有既有的交叉解讀紀錄:有就自動載入(快取優先,秒回不打 EAP)
async function autoLoadEapRead() {
  try {
    const r = await reviewApi("/api/cache/list",
      { kind: "market_read", company_id: props.c.code || props.c.id, limit: 1 }, { items: [] }, 100);
    if (r.items?.length) await loadEapRead(false);
  } catch (e) { /* 無紀錄或後端未起,維持按鈕手動觸發 */ }
}

// §9.2 色彩規範:低風險=emerald / 中等=amber / 偏高風險=rose / 資料不足=slate
const LEVEL = {
  "低風險":   { box: "border-emerald-600 bg-emerald-50", text: "text-emerald-700", bar: "bg-emerald-600" },
  "中等":     { box: "border-amber-600 bg-amber-50",     text: "text-amber-700",   bar: "bg-amber-600" },
  "偏高風險": { box: "border-rose-600 bg-rose-50",       text: "text-rose-700",    bar: "bg-rose-600" },
  "資料不足": { box: "border-slate-400 bg-slate-50",     text: "text-slate-500",   bar: "bg-slate-400" },
};
const lv = computed(() => LEVEL[data.value?.level] || LEVEL["資料不足"]);

async function load() {
  const code = props.c.code || props.c.id;
  loadErr.value = null; loading.value = true; data.value = null;
  eapRead.value = null; eapReadErr.value = null;   // 換公司時重置交叉解讀
  try {
    data.value = await reviewApi("/api/market/signal",
      { company_id: code, company_name: props.c.name }, null, 600);
  } catch (e) {
    loadErr.value = e;
  }
  loading.value = false;
}
onMounted(() => { load(); autoLoadEapRead(); });
watch(() => props.c.code, load);

// Sparkline:月收盤價折線 + 面積(§8.5)
const W = 640, H = 140, PAD = 6;
const spark = computed(() => {
  const p = data.value?.prices_monthly || [];
  if (p.length < 2) return null;
  const min = Math.min(...p), max = Math.max(...p), span = max - min || 1;
  const pts = p.map((v, i) => [
    PAD + (i / (p.length - 1)) * (W - PAD * 2),
    H - PAD - ((v - min) / span) * (H - PAD * 2),
  ]);
  return {
    line: pts.map((q) => q.join(",")).join(" "),
    area: `${PAD},${H - PAD} ` + pts.map((q) => q.join(",")).join(" ") + ` ${W - PAD},${H - PAD}`,
    up: p[p.length - 1] >= p[0], min, max, first: p[0], last: p[p.length - 1],
  };
});

const METRICS = [
  ["vol_full_pct", "年化波動度", "%", "全期;越低越穩定"],
  ["mdd_pct", "最大回撤", "%", "期間最深跌幅"],
  ["mom_1y_pct", "近一年報酬", "%", "方向共識"],
  ["turnover_pct", "日均週轉率", "%", "流動性輔助"],
  ["amihud", "Amihud 非流動性", "", "越高越難變現"],
  ["mktcap", "市值", "百萬元", "規模韌性"],
];
const fmt = (k, v) => v == null ? "—" : (k === "mktcap" ? Math.round(v).toLocaleString() : v);
</script>

<template>
  <div class="space-y-4">
    <div class="bg-sky-50 border border-sky-200 px-4 py-3 flex items-center justify-between gap-4 flex-wrap">
      <p class="text-sm text-slate-700">
        以整體資本市場對本企業的評價作為授信補強訊號。分數越高＝市場風險評價越低(同業相對)。
      </p>
      <span v-if="data?.meta" :class="`text-xs text-slate-500 ${num}`">
        母體 {{ data.meta.universe }} 家 · {{ data.meta.industry }} · {{ data.meta.period }}
      </span>
    </div>

    <LoadingCard v-if="loading" title="正在計算市場訊號"
      :steps="['讀取歷史股價', '計算波動與最大回撤', '比對同業分位', '合成風險評分']" />

    <div v-else-if="loadErr" role="alert" class="border border-rose-300 border-l-4 border-l-rose-600 bg-rose-50 p-4 flex items-center justify-between gap-4 flex-wrap">
      <div>
        <div class="font-bold text-rose-800 text-sm mb-0.5">市場訊號載入失敗({{ loadErr.code }})</div>
        <p class="text-sm text-slate-800 leading-relaxed">{{ loadErr.message }}</p>
      </div>
      <button @click="load" :class="`px-5 h-10 text-sm font-bold text-white bg-rose-700 hover:bg-rose-600 rounded-sm ${focusRing}`">重試</button>
    </div>

    <template v-else-if="data">
      <!-- 分數方塊 + 走勢圖 -->
      <div class="grid lg:grid-cols-3 gap-4">
        <div :class="['border-2 p-4 flex flex-col justify-center items-center', lv.box]">
          <div class="text-xs text-slate-600 mb-1">市場訊號分數</div>
          <div :class="`${num} font-bold text-5xl ${lv.text}`">{{ data.market_score ?? "—" }}</div>
          <div :class="`mt-1 text-base font-bold ${lv.text}`">{{ data.level }}</div>
          <div :class="`mt-2 text-xs text-slate-500 ${num}`">納入 {{ data.n_days }} 個交易日</div>
          <span v-if="data.tier === 'partial'" class="mt-2 text-xs px-1.5 py-0.5 border border-amber-500 bg-white text-amber-800 rounded-sm">
            歷史 &lt; 1 年 · 僅供參考
          </span>
          <span v-else-if="data.tier === 'insufficient'" class="mt-2 text-xs px-1.5 py-0.5 border border-slate-400 bg-white text-slate-600 rounded-sm">
            交易日不足 60 日 · 不予評分
          </span>
        </div>

        <div class="lg:col-span-2 bg-white border border-slate-300 p-4">
          <div class="flex items-baseline justify-between flex-wrap gap-2 mb-1">
            <h3 class="text-sm font-bold text-slate-900 border-l-4 border-sky-800 pl-2">月收盤價走勢</h3>
            <span v-if="spark" :class="`text-xs text-slate-500 ${num}`">
              期間 {{ spark.first }} → {{ spark.last }} 元(高 {{ spark.max }} / 低 {{ spark.min }})
            </span>
          </div>
          <svg v-if="spark" :viewBox="`0 0 ${W} ${H}`" class="w-full" role="img" aria-label="月收盤價走勢">
            <polygon :points="spark.area" :fill="spark.up ? '#059669' : '#e11d48'" fill-opacity="0.10" />
            <polyline :points="spark.line" fill="none" :stroke="spark.up ? '#059669' : '#e11d48'" stroke-width="2" />
          </svg>
          <p v-else class="text-sm text-slate-500 py-8 text-center">無足夠價格資料繪製走勢。</p>
        </div>
      </div>

      <!-- 瀑布圖 -->
      <div v-if="data.waterfall.length" class="bg-white border border-slate-300 border-t-4 border-t-sky-900 p-4">
        <h3 class="font-bold text-slate-900 mb-1">市場訊號分數組成</h3>
        <p class="text-xs text-slate-500 mb-3">基準 50 分,依同業橫斷面百分位加權調整(波動度 30% / 回撤 25% / 規模 20% / 流動性 15% / 動能 10%)。</p>
        <WaterfallChart :items="data.waterfall" :final-score="data.market_score" />
      </div>

      <!-- 指標明細 -->
      <div class="bg-white border border-slate-300 p-4">
        <h3 class="text-sm font-bold text-slate-900 border-l-4 border-sky-800 pl-2 mb-3">指標明細</h3>
        <div class="grid sm:grid-cols-3 gap-3">
          <div v-for="[k, label, unit, note] in METRICS" :key="k" class="border border-slate-200 p-3">
            <div class="text-xs text-slate-500">{{ label }}</div>
            <div :class="`${num} font-bold text-lg text-slate-900`">
              {{ fmt(k, data.metrics[k]) }}<span class="text-xs text-slate-500 font-normal"> {{ unit }}</span>
            </div>
            <div class="text-xs text-slate-400 mt-0.5">{{ note }}</div>
          </div>
        </div>
      </div>

      <!-- 授信解讀 -->
      <div class="bg-white border border-slate-300 p-4">
        <div class="flex items-center justify-between gap-2 flex-wrap mb-2">
          <h3 class="text-sm font-bold text-slate-900 border-l-4 border-sky-800 pl-2">授信解讀
            <span v-if="eapRead && !eapRead._degraded" class="ml-1 text-xs font-normal text-sky-800 bg-sky-50 border border-sky-300 rounded-sm px-1.5 py-0.5">EAP 交叉解讀</span>
          </h3>
          <button v-if="!eapRead" @click="loadEapRead(true)" :disabled="eapBusy"
            :class="`px-3 h-8 text-xs font-bold text-sky-900 bg-white border border-slate-400 hover:bg-sky-50 disabled:opacity-50 rounded-sm motion-safe:transition-colors ${focusRing}`">
            {{ eapBusy ? "解讀中…" : "EAP 財報交叉解讀" }}
          </button>
        </div>
        <ul class="mb-3">
          <li v-for="(s, i) in (eapRead?.summary || data.reading.summary)" :key="i" class="text-sm text-slate-800 leading-relaxed py-0.5">· {{ s }}</li>
        </ul>
        <div class="border border-emerald-300 border-l-4 border-l-emerald-600 bg-emerald-50 p-3 text-sm leading-relaxed">
          <span class="font-bold text-emerald-800">建議方向:</span>
          <span class="text-slate-800"> {{ eapRead?.recommendation || data.reading.recommendation }}</span>
        </div>
        <p v-if="eapRead?.cites?.length" class="text-xs text-slate-500 mt-2">
          引用知識庫欄位:{{ eapRead.cites.join("、") }}
        </p>
        <div v-if="eapRead && !eapRead._degraded" class="mt-2">
          <RecordBar kind="market_read" :cid="props.c.code || props.c.id" :current="eapMeta" :busy="eapBusy"
            @refresh="loadEapRead(true)" @load="(p) => (eapRead = p)" />
        </div>
        <p v-if="eapReadErr" class="text-xs text-rose-700 mt-2">EAP 交叉解讀失敗({{ eapReadErr.code }}),目前顯示為系統規則解讀。</p>
        <p class="text-xs text-slate-500 mt-2 leading-relaxed">
          註:市場評分為離線量化計算(可重現),AI 僅負責與知識庫財報交叉判讀;本模組非違約機率預測,須與內部財務資料合併判讀。
        </p>
      </div>
    </template>
  </div>
</template>
