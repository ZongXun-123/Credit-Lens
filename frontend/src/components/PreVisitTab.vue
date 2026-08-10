<script setup>
// 頁籤 2:拜訪前情資(手刻 SVG 雷達圖 + 防禦提問單)
// 資料來源 = 規格書 5.7 /api/pre/brief(USE_MOCK=true 時回退第 5 章範例 JSON)
import { ref, computed, onMounted, watch } from "vue";
import { AGENT, num } from "../constants.js";
import { reviewApi } from "../api.js";
import LoadingCard from "./LoadingCard.vue";
import RecordBar from "./RecordBar.vue";
import { MOCK } from "../mock.js";

const props = defineProps({ c: { type: Object, required: true } });

const brief = ref(null); // BriefResult:{ radar, questions }
const loadErr = ref(null);
const sel = ref("finance");

const briefBusy = ref(false);
const cid = computed(() => props.c.code || props.c.id);
const briefMeta = computed(() => brief.value?._rec_id
  ? { recId: brief.value._rec_id, cachedAt: brief.value._cached_at, fromCache: !!brief.value._from_cache, pinned: !!brief.value._pinned }
  : null);

async function load(force = false) {
  loadErr.value = null; briefBusy.value = true;
  try {
    brief.value = await reviewApi(
      "/api/pre/brief",
      { company_id: props.c.id, company_name: props.c.name, company_code: props.c.code || "", force }, // 5.7 Request
      { radar: MOCK.radar, questions: MOCK.questions },
      900
    );
  } catch (e) {
    loadErr.value = e; // 5.2 錯誤格式,依 7.3 顯示訊息 + 重試
  }
  briefBusy.value = false;
}
onMounted(() => load(false));   // 快取優先:有既有紀錄秒回

const radar = computed(() => brief.value?.radar || []);
// 互動狀態:hover 為滑鼠當下停留的維度;drawn 控制入場動畫(由中心展開)
const hover = ref("");
const drawn = ref(false);
watch(brief, (v) => {
  drawn.value = false;
  if (v) requestAnimationFrame(() => requestAnimationFrame(() => (drawn.value = true)));
}, { immediate: true });
const questions = computed(() => brief.value?.questions || []);
const selDim = computed(() => radar.value.find((x) => x.key === sel.value) || radar.value[0]);
const weakest = computed(() => [...radar.value].sort((a, b) => a.score - b.score)[0]);

const R_CX = 160, R_CY = 140, R_R = 96;
function radarPt(i, val, r = R_R) {
  const n = radar.value.length || 6;
  const a = (Math.PI * 2 * i) / n - Math.PI / 2;
  return [R_CX + Math.cos(a) * (val / 100) * r, R_CY + Math.sin(a) * (val / 100) * r];
}
const radarPoly = (field) => radar.value.map((d, i) => radarPt(i, d[field]).join(",")).join(" ");
const radarGrid = computed(() => [25, 50, 75, 100].map((lv) => radar.value.map((_, i) => radarPt(i, lv).join(",")).join(" ")));
const radarAxes = computed(() => radar.value.map((_, i) => radarPt(i, 100)));
const radarLabels = computed(() => radar.value.map((d, i) => {
  const [x, y] = radarPt(i, 122);
  const a = (Math.PI * 2 * i) / radar.value.length - Math.PI / 2;
  const cos = Math.cos(a);
  const anchor = Math.abs(cos) < 0.3 ? "middle" : cos > 0 ? "start" : "end";
  return { ...d, x, y: y + 4, anchor };
}));
</script>

<template>
  <div v-if="loadErr" role="alert" class="border border-rose-300 border-l-4 border-l-rose-600 bg-rose-50 p-4 flex items-center justify-between gap-4 flex-wrap">
    <div>
      <div class="font-bold text-rose-800 text-sm mb-0.5">情資載入失敗({{ loadErr.code }})</div>
      <p class="text-sm text-slate-800 leading-relaxed">{{ loadErr.message }}</p>
    </div>
    <button @click="load(false)" class="px-5 h-10 text-sm font-bold text-white bg-rose-700 hover:bg-rose-600 rounded-sm motion-safe:transition-colors">重試</button>
  </div>
  <LoadingCard v-else-if="!brief" title="正在產出拜訪前情資"
    :steps="['檢索企業財報', '計算五維評分', '比對同業基準', '研擬防禦提問']" />
  <div v-else-if="false" class="bg-white border border-slate-300 p-4 text-sm text-slate-500" aria-live="polite">
    載入拜訪前情資中<span class="animate-pulse" aria-hidden="true"> …</span>
  </div>
  <div v-else class="space-y-5">
    <RecordBar kind="pre_brief" :cid="cid" :current="briefMeta" :busy="briefBusy"
      @refresh="load(true)" @load="(p) => (brief = p)" />
    <div class="grid lg:grid-cols-2 gap-4">
      <div class="bg-white border border-slate-300 p-3">
        <h3 class="text-sm font-bold text-slate-900 border-l-4 border-sky-800 pl-2 mb-1">護城河雷達圖</h3>
        <svg viewBox="0 0 320 290" class="w-full select-none" style="max-height: 290px" role="img"
          aria-label="五維護城河雷達圖,可點選各維度查看評分理由">
          <!-- 網格與軸線:滑入時對應軸線加亮 -->
          <polygon v-for="(pts, i) in radarGrid" :key="'g' + i" :points="pts" fill="none" stroke="#cbd5e1" stroke-width="1"
            :opacity="drawn ? 1 : 0" :style="`transition: opacity .5s ease ${i * 70}ms`" />
          <line v-for="([ax, ay], i) in radarAxes" :key="'a' + i" :x1="R_CX" :y1="R_CY" :x2="ax" :y2="ay"
            :stroke="radar[i] && (radar[i].key === sel || radar[i].key === hover) ? '#0284c7' : '#cbd5e1'"
            :stroke-width="radar[i] && (radar[i].key === sel || radar[i].key === hover) ? 1.8 : 1"
            style="transition: stroke .2s ease, stroke-width .2s ease" />

          <!-- 產業基準(虛線) -->
          <polygon :points="radarPoly('benchmark')" fill="#94a3b8" fill-opacity="0.12" stroke="#94a3b8"
            stroke-width="1.5" stroke-dasharray="4 4"
            :style="`transform-origin:${R_CX}px ${R_CY}px; transform:scale(${drawn ? 1 : 0}); transition: transform .7s cubic-bezier(.34,1.3,.5,1) .15s`" />

          <!-- 本公司分數:入場時由中心展開 -->
          <polygon :points="radarPoly('score')" fill="#0369a1" fill-opacity="0.22" stroke="#0c4a6e" stroke-width="2"
            :style="`transform-origin:${R_CX}px ${R_CY}px; transform:scale(${drawn ? 1 : 0}); transition: transform .8s cubic-bezier(.34,1.35,.5,1) .3s`" />

          <!-- 頂點圓點:可點選,選中時放大並帶脈動光暈 -->
          <g v-for="(d, i) in radar" :key="'p' + d.key">
            <circle v-if="d.key === sel || d.key === hover" :cx="radarPt(i, d.score)[0]" :cy="radarPt(i, d.score)[1]"
              r="11" fill="#0284c7" fill-opacity="0.18" class="motion-safe:animate-[pulseDot_1.6s_ease-out_infinite]" />
            <circle :cx="radarPt(i, d.score)[0]" :cy="radarPt(i, d.score)[1]"
              :r="d.key === sel ? 6 : d.key === hover ? 5.5 : 4"
              :fill="d.key === sel ? '#0c4a6e' : '#0369a1'" stroke="#fff" stroke-width="2"
              style="cursor: pointer; transition: r .18s ease, fill .18s ease"
              :opacity="drawn ? 1 : 0"
              @click="sel = d.key" @mouseenter="hover = d.key" @mouseleave="hover = ''" />
          </g>

          <!-- 維度標籤:整塊可點,含分數與高於/低於基準的箭頭 -->
          <g v-for="(lb, i) in radarLabels" :key="lb.key" style="cursor: pointer"
            @click="sel = lb.key" @mouseenter="hover = lb.key" @mouseleave="hover = ''"
            :opacity="drawn ? 1 : 0" :style="`transition: opacity .4s ease ${400 + i * 60}ms`">
            <text :x="lb.x" :y="lb.y" :text-anchor="lb.anchor"
              :fill="lb.key === sel ? '#0c4a6e' : lb.key === hover ? '#0284c7' : '#475569'"
              :font-size="12" :font-weight="lb.key === sel || lb.key === hover ? 700 : 400"
              style="transition: fill .18s ease">
              {{ lb.label }} {{ lb.score }}
              <tspan :fill="radar[i] && radar[i].score >= radar[i].benchmark ? '#059669' : '#e11d48'" font-size="10">
                {{ radar[i] && radar[i].score >= radar[i].benchmark ? "▲" : "▼" }}
              </tspan>
            </text>
          </g>
        </svg>
        <div class="flex justify-center gap-5 text-xs text-slate-600 mt-1">
          <span class="flex items-center gap-1.5"><span class="inline-block w-4 h-0.5 bg-sky-900" />該企業</span>
          <span class="flex items-center gap-1.5"><span class="inline-block w-4 border-t-2 border-dashed border-slate-400" />產業基準</span>
        </div>
        <p class="text-xs text-slate-500 text-center mt-1">點選維度名稱或頂點圓點,可查看該維評分理由與資料來源;▲▼ 表示相對產業基準</p>
      </div>

      <div class="space-y-3">
        <div :key="selDim.key" class="bg-white border border-slate-300 border-t-4 border-t-sky-900 p-4 motion-safe:animate-[fadeUp_.35s_ease-out]">
          <div class="flex items-baseline justify-between mb-1.5 gap-2">
            <h3 class="font-bold text-slate-900">{{ selDim.label }}</h3>
            <span :class="`${num} font-bold text-xl text-sky-900`">{{ selDim.score }}<span class="text-xs text-slate-500 font-normal"> 分</span></span>
          </div>
          <div class="flex items-center gap-2 text-xs mb-2.5 flex-wrap">
            <span :class="['px-1.5 py-0.5 border rounded-sm', AGENT[selDim.agent].chip]">評分:{{ AGENT[selDim.agent].name }} Agent</span>
            <span :class="`text-slate-500 ${num}`">產業基準 {{ selDim.benchmark }} 分({{ selDim.score >= selDim.benchmark ? "高於" : "低於" }}基準 {{ Math.abs(selDim.score - selDim.benchmark) }} 分)</span>
          </div>
          <p class="text-sm leading-relaxed text-slate-800 mb-1.5">{{ selDim.reason }}</p>
          <span v-for="(ct, i) in selDim.cites" :key="i" class="inline-block mt-1 mr-1 px-1.5 py-0.5 rounded-sm text-xs bg-slate-100 text-slate-600 border border-slate-300">資料來源:{{ ct }}</span>
        </div>
        <div class="bg-amber-50 border border-amber-300 border-l-4 border-l-amber-500 p-4 text-sm leading-relaxed">
          <div class="font-bold text-amber-900 mb-1">本次拜訪建議聚焦</div>
          <p class="text-slate-800">
            最弱維度為「{{ weakest.label }}」({{ weakest.score }} 分,低於產業基準 {{ weakest.benchmark - weakest.score }} 分),
            下方防禦提問單已優先針對此維度生成追問。
          </p>
        </div>
      </div>
    </div>

    <div>
      <div class="flex items-center justify-between gap-4 mb-3">
        <h2 class="border-l-4 border-sky-800 pl-3 text-lg font-bold text-slate-900">護城河防禦提問單</h2>
      </div>
      <ol class="border-t-2 border-sky-900">
        <li v-for="q in questions" :key="q.id" class="bg-white border-b border-slate-300 px-4 py-3 hover:bg-sky-50 motion-safe:transition-colors">
          <div class="flex gap-3">
            <span :class="`${num} text-sky-900 font-bold text-sm shrink-0 w-8`">Q{{ q.id }}.</span>
            <div class="min-w-0">
              <p class="text-sm text-slate-900 font-medium leading-relaxed">{{ q.q }}</p>
              <p class="text-xs text-slate-500 mt-1 leading-relaxed">
                <span class="px-1 py-0.5 bg-slate-100 border border-slate-300 rounded-sm mr-1">AI 出題依據</span>
                {{ q.why }}
              </p>
            </div>
          </div>
        </li>
      </ol>
    </div>
  </div>
</template>