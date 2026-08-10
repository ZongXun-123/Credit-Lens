<script setup>
// 頁面 6:網站導覽
// 以「AO 的一天」工作流為主軸,把五個頁面與四個案件頁籤畫成一張可互動的流程地圖。
// 節點可點擊直達,滑鼠移入時對應路徑高亮,右側同步顯示該節點的說明與資料來源。
import { ref, onMounted } from "vue";
import { focusRing } from "../constants.js";

const emit = defineEmits(["go", "open-intel"]);

const active = ref("dashboard");
const mounted = ref(false);
onMounted(() => requestAnimationFrame(() => (mounted.value = true)));

// 地圖節點:x/y 為 SVG 座標(viewBox 0 0 720 360)
const NODES = [
  { key: "dashboard", nav: "案件總覽", x: 92, y: 74, w: 128, stage: "起點",
    title: "案件總覽", desc: "列出 EAP 知識庫中的全部企業,可搜尋與排序,點選任一家即進入案件頁。",
    src: ["EAP 知識庫公司清單", "股價市場訊號(評分)"], color: "slate" },
  { key: "intel", nav: "情資查詢", x: 92, y: 178, w: 128, stage: "背景調查",
    title: "情資查詢", desc: "以統一編號或公司名稱查詢公開情資:商工登記、月營收、藥品許可證、專利、新聞。",
    src: ["經濟部商工登記", "TWSE 月營收", "食藥署許可證", "TIPO / Google Patents", "GDELT 新聞"], color: "slate" },
  { key: "ask", nav: "知識問答", x: 92, y: 282, w: 128, stage: "隨時查證",
    title: "知識問答", desc: "直接與 EAP 平台模型自由對話,不套評分格式,供臨時查證使用。",
    src: ["EAP chat API"], color: "slate" },

  { key: "committee", nav: "案件總覽", x: 300, y: 60, w: 150, stage: "拜訪前", tab: "AI 審查會議",
    title: "AI 審查會議", desc: "財務 Agent 與技術 Agent 並行分析,風險審查官交叉質詢並給出裁決分與評分瀑布。",
    src: ["EAP 知識圖譜財報", "TIPO 專利", "新聞情緒"], color: "teal" },
  { key: "pre", nav: "案件總覽", x: 300, y: 148, w: 150, stage: "拜訪前", tab: "拜訪前情資",
    title: "五維雷達與提問單", desc: "技術、市場、財務、訴訟、外部環境五維評分,並針對最弱兩維產出防禦提問單。",
    src: ["EAP 知識圖譜", "產業通識"], color: "teal" },
  { key: "market", nav: "市場訊號", x: 300, y: 236, w: 150, stage: "拜訪前", tab: "市場訊號",
    title: "市場訊號", desc: "波動度、最大回撤、市值等量化指標離線計算,再由 EAP 與財報交叉解讀。",
    src: ["TEJ 股價(離線計算)", "EAP 財報交叉解讀"], color: "teal" },

  { key: "mid", nav: "案件總覽", x: 500, y: 148, w: 132, stage: "拜訪中", tab: "拜訪中與後",
    title: "即時提詞卡", desc: "面談現場輸入客戶回答,系統即時判定風險是否化解,並建議下一句追問方向。",
    src: ["EAP 判定模型"], color: "amber" },

  { key: "post", nav: "案件總覽", x: 500, y: 250, w: 132, stage: "拜訪後", tab: "拜訪中與後",
    title: "紀錄萃取與評分", desc: "貼上或上傳會議紀錄,萃取承諾事項與風險回應,以裁決分為基準產出覆評瀑布。",
    src: ["EAP 萃取模型", "拜訪前裁決分"], color: "purple" },
  { key: "reports", nav: "報告中心", x: 500, y: 60, w: 132, stage: "歸檔",
    title: "報告中心", desc: "彙整已產出的授信審查報告,可加星標記、下載 PDF、刪除,點公司名可回到案件頁。",
    src: ["reports 目錄", "快取資料庫分數"], color: "purple" },
];

// 連線:from → to
const EDGES = [
  ["dashboard", "committee"], ["dashboard", "pre"], ["dashboard", "market"],
  ["intel", "pre"], ["committee", "pre"], ["pre", "mid"], ["mid", "post"],
  ["post", "reports"], ["committee", "reports"],
];

const byKey = Object.fromEntries(NODES.map((n) => [n.key, n]));
const cur = () => byKey[active.value] || NODES[0];

const COLOR = {
  slate: { box: "fill-white stroke-slate-400", text: "fill-slate-800", chip: "bg-slate-100 text-slate-700 border-slate-300", bar: "bg-slate-500" },
  teal: { box: "fill-white stroke-teal-600", text: "fill-teal-900", chip: "bg-teal-50 text-teal-800 border-teal-300", bar: "bg-teal-600" },
  amber: { box: "fill-white stroke-amber-600", text: "fill-amber-900", chip: "bg-amber-50 text-amber-800 border-amber-300", bar: "bg-amber-600" },
  purple: { box: "fill-white stroke-violet-600", text: "fill-violet-900", chip: "bg-violet-50 text-violet-800 border-violet-300", bar: "bg-violet-600" },
};

const H = 42;
function path(a, b) {
  const A = byKey[a], B = byKey[b];
  const x1 = A.x + A.w / 2, y1 = A.y + H / 2;
  const x2 = B.x - B.w / 2, y2 = B.y + H / 2;
  const mx = (x1 + x2) / 2;
  return `M${x1} ${y1} C${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
}
const related = (k) => EDGES.filter((e) => e.includes(active.value)).some((e) => e.includes(k));

function goNode(n) {
  active.value = n.key;
  if (n.key === "intel") emit("open-intel", "");
  else emit("go", n.nav);
}
</script>

<template>
  <main id="main" class="max-w-5xl mx-auto px-4 py-6 w-full">
    <nav aria-label="麵包屑" class="text-sm text-slate-500">
      <ol class="flex items-center gap-1 flex-wrap">
        <li>首頁</li>
        <li class="flex items-center gap-1">
          <span aria-hidden="true" class="text-slate-400 px-0.5">/</span>
          <span aria-current="page" class="text-slate-700">網站導覽</span>
        </li>
      </ol>
    </nav>

    <header class="mt-4">
      <h2 class="border-l-4 border-sky-800 pl-3 text-lg font-bold text-slate-900">網站導覽</h2>
      <p class="mt-1.5 pl-3 text-sm text-slate-600 leading-relaxed">
        本平臺依授信人員（AO）「拜訪前、拜訪中、拜訪後」的工作流設計。
        點選地圖上的任一節點即可直達該功能，或將滑鼠移入以檢視說明與資料來源。
      </p>
    </header>

    <!-- 階段圖例 -->
    <div class="mt-4 flex items-center gap-4 flex-wrap text-xs">
      <span v-for="(g, i) in [['起點與工具', 'bg-slate-500'], ['拜訪前', 'bg-teal-600'], ['拜訪中', 'bg-amber-600'], ['拜訪後與歸檔', 'bg-violet-600']]"
        :key="g[0]" class="flex items-center gap-1.5 motion-safe:animate-[fadeUp_.4s_ease-out]"
        :style="{ animationDelay: `${i * 70}ms` }">
        <span aria-hidden="true" :class="['w-3 h-3 rounded-sm', g[1]]" />
        <span class="text-slate-700">{{ g[0] }}</span>
      </span>
    </div>

    <div class="mt-4 grid lg:grid-cols-3 gap-4 items-start">
      <!-- 流程地圖 -->
      <section class="lg:col-span-2 bg-white border border-slate-300 p-2 overflow-x-auto" aria-label="功能流程地圖">
        <svg viewBox="0 0 720 360" class="w-full min-w-[620px]" role="img"
          aria-label="智貸先鋒功能流程地圖,共九個功能節點">
          <defs>
            <marker id="am" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M1 1L9 5L1 9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            </marker>
          </defs>

          <!-- 階段背景帶 -->
          <g opacity="0.5">
            <rect x="18" y="26" width="148" height="316" rx="10" class="fill-slate-50 stroke-slate-200" />
            <rect x="216" y="26" width="176" height="260" rx="10" class="fill-teal-50/60 stroke-teal-200" />
            <rect x="424" y="112" width="152" height="174" rx="10" class="fill-amber-50/60 stroke-amber-200" />
            <rect x="424" y="26" width="152" height="76" rx="10" class="fill-violet-50/60 stroke-violet-200" />
          </g>
          <g class="text-[11px]" fill="currentColor">
            <text x="92" y="18" text-anchor="middle" class="fill-slate-500">進入點</text>
            <text x="304" y="18" text-anchor="middle" class="fill-teal-700">拜訪前</text>
            <text x="500" y="18" text-anchor="middle" class="fill-violet-700">歸檔</text>
          </g>

          <!-- 連線:與作用中節點相關者高亮並流動 -->
          <g fill="none" stroke-width="1.8">
            <path v-for="(e, i) in EDGES" :key="i" :d="path(e[0], e[1])" marker-end="url(#am)"
              :class="[e.includes(active) ? 'text-sky-700' : 'text-slate-300',
                       'motion-safe:transition-colors duration-300']"
              stroke="currentColor"
              :stroke-dasharray="e.includes(active) ? '6 5' : '0'"
              :style="e.includes(active) ? 'animation: dashMove 1.1s linear infinite' : ''" />
          </g>

          <!-- 節點 -->
          <g v-for="(n, i) in NODES" :key="n.key">
            <g class="cursor-pointer motion-safe:transition-opacity duration-300"
              :opacity="mounted ? (related(n.key) || n.key === active ? 1 : 0.55) : 0"
              :style="{ transition: `opacity .4s ease ${i * 55}ms` }"
              @mouseenter="active = n.key" @focus="active = n.key" @click="goNode(n)"
              tabindex="0" role="button" :aria-label="`前往${n.title}`"
              @keydown.enter.prevent="goNode(n)" @keydown.space.prevent="goNode(n)">
              <rect :x="n.x - n.w / 2" :y="n.y" :width="n.w" :height="H" rx="6"
                :class="[COLOR[n.color].box, 'motion-safe:transition-all duration-200']"
                :stroke-width="n.key === active ? 2.6 : 1.4" />
              <rect v-if="n.key === active" :x="n.x - n.w / 2" :y="n.y" width="4" :height="H" rx="2"
                :class="COLOR[n.color].box.replace('fill-white', 'fill-current')" />
              <text :x="n.x" :y="n.y + 18" text-anchor="middle" class="text-[12.5px] font-bold"
                :class="COLOR[n.color].text">{{ n.title }}</text>
              <text :x="n.x" :y="n.y + 32" text-anchor="middle" class="text-[10px] fill-slate-500">
                {{ n.tab ? `案件頁 · ${n.tab}` : n.nav }}
              </text>
            </g>
          </g>
        </svg>
      </section>

      <!-- 節點說明 -->
      <aside class="space-y-3">
        <div :key="active" class="bg-white border border-slate-300 motion-safe:animate-[popIn_.28s_ease-out]">
          <div :class="['h-1.5', COLOR[cur().color].bar]" />
          <div class="p-4">
            <span :class="['inline-block text-xs px-2 py-0.5 border rounded-sm mb-2', COLOR[cur().color].chip]">
              {{ cur().stage }}
            </span>
            <h3 class="text-base font-bold text-slate-900">{{ cur().title }}</h3>
            <p class="mt-1.5 text-sm text-slate-700 leading-relaxed">{{ cur().desc }}</p>

            <h4 class="mt-3 text-xs font-bold text-slate-500">資料來源</h4>
            <ul class="mt-1 space-y-1">
              <li v-for="(s, i) in cur().src" :key="s"
                class="text-xs text-slate-700 flex items-start gap-1.5 motion-safe:animate-[slideIn_.3s_ease-out]"
                :style="{ animationDelay: `${i * 55}ms` }">
                <span aria-hidden="true" class="text-slate-400 mt-0.5">▸</span>{{ s }}
              </li>
            </ul>

            <button @click="goNode(cur())"
              :class="`mt-4 w-full px-3 h-10 text-sm font-bold text-white bg-sky-900 hover:bg-sky-800 rounded-sm motion-safe:transition-colors ${focusRing}`">
              前往{{ cur().title }} →
            </button>
          </div>
        </div>

        <div class="bg-white border border-slate-300 border-l-4 border-l-slate-400 p-3">
          <h4 class="text-xs font-bold text-slate-900 mb-1.5">技術架構</h4>
          <ul class="text-xs text-slate-700 leading-relaxed space-y-1 list-disc list-inside">
            <li>多代理協作（Multi-Agent）：財務、技術、審查官三個角色分工</li>
            <li>LLM-as-a-Judge：審查官僅能引用前兩者發現，不得產生新事實</li>
            <li>多源情資融合：EAP 知識圖譜 × 六項公開資料源</li>
            <li>防幻覺：每筆發現附引用來源，無來源者自動剔除</li>
          </ul>
        </div>
      </aside>
    </div>

    <!-- 全站頁面清單(可及性與 SEO 用) -->
    <section class="mt-6">
      <h3 class="border-l-4 border-slate-400 pl-3 text-base font-bold text-slate-900 mb-3">全站頁面</h3>
      <ul class="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
        <li v-for="(t, i) in ['案件總覽', '情資查詢', '市場訊號', '知識問答', '報告中心']" :key="t"
          class="motion-safe:animate-[fadeUp_.4s_ease-out]" :style="{ animationDelay: `${i * 60}ms` }">
          <button @click="emit('go', t)"
            :class="`w-full text-left px-3 py-2.5 bg-white border border-slate-300 hover:border-sky-500 hover:bg-sky-50
                     text-sm text-slate-800 rounded-sm hover-lift ${focusRing}`">
            <span class="font-medium">{{ t }}</span>
            <span aria-hidden="true" class="float-right text-slate-400">→</span>
          </button>
        </li>
      </ul>
    </section>
  </main>
</template>
