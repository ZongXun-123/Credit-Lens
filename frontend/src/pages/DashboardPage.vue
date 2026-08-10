<script setup>
// 頁面 1:案件總覽(Hero 搜尋 + 進行中案件列表 + 最新公告)
import { ref, computed, onMounted } from "vue";
import { STAGE_LABEL, focusRing, num } from "../constants.js";
import { reviewApi } from "../api.js";
import LoadingCard from "../components/LoadingCard.vue";
import { CASES, ANNOUNCEMENTS} from "../mock.js";

// 案件來源:優先 = EAP 知識庫公司清單(/api/eap/universe,與平台實際資料一致);
// 市場評分以證券代號 join 進來(股價市場訊號模組離線計算,非 EAP 產生)。
// EAP 清單取不到時,退回市場檔 36 家(原行為)。
const universe = ref(null);
const cases = ref(CASES);
const loading = ref(true);
const graphCodes = ref(new Set());   // 有 EAP 知識圖譜財務資料的公司
const caseSource = ref("");          // "eap" | "market" | "mock"
onMounted(async () => {
  loading.value = true;
  // 知識圖譜覆蓋範圍(失敗不影響列表)
  try {
    const cov = await reviewApi("/api/eap/coverage", {}, null, 200);
    graphCodes.value = new Set((cov?.companies || []).map((c) => c.code));
  } catch (e) { /* 忽略 */ }

  let mkt = null;
  try {
    mkt = await reviewApi("/api/market/universe", {}, null, 300);
    universe.value = mkt;
  } catch (e) { /* 市場檔缺失時仍可只列 EAP 清單 */ }
  const byCode = new Map((mkt?.companies || []).map((c) => [c.company_id, c]));

  try {
    const u = await reviewApi("/api/eap/universe", {}, null, 300);
    if (u?.companies?.length) {
      cases.value = u.companies.map((c) => {
        const m = c.code ? byCode.get(c.code) : null;   // 市場分數以代號 join
        return {
          id: c.ban || (c.code ? `code:${c.code}` : c.name), code: c.code, ban: c.ban || null,
          name: c.name, industry: mkt?.industry || "生技製藥", stage: "pre",
          score: m?.market_score ?? null,
          updated: u.fetched_at || "—",
          level: m?.level || "資料不足", tier: m?.tier || "insufficient",
          readiness: c.readiness ?? 0, financeState: c.finance_state || "", techState: c.tech_state || "",
        };
      }).concat(CASES);
      caseSource.value = "eap";
      loading.value = false;
      return;
    }
  } catch (e) { /* EAP 清單失敗 → 走下方市場檔備援 */ }

  if (mkt) {
    cases.value = mkt.companies.map((c) => ({
      // id 僅作為列表鍵值;統編一律放 ban(沒有就是 null,不可用證券代號頂替)
      id: c.ban || `code:${c.company_id}`, code: c.company_id, ban: c.ban || null, name: c.company_name,
      industry: mkt.industry, stage: "pre", score: c.market_score,
      updated: mkt.period?.split("~").pop()?.trim() || "—",
      level: c.level, tier: c.tier,
    })).concat(CASES);
    caseSource.value = "market";
    loading.value = false;
  } else {
    cases.value = CASES;
    caseSource.value = "mock";
  }
  loading.value = false;
});

const LEVEL_CLS = {
  "低風險": "text-emerald-700", "中等": "text-amber-700",
  "偏高風險": "text-rose-700", "資料不足": "text-slate-400",
};

const emit = defineEmits(["open-case"]);

const query = ref("");
// 排序:評分(空值沉底)、名稱(繁中筆畫以 localeCompare 處理)、代號、風險等級
const sortKey = ref("ready");
const sortAsc = ref(false);   // 預設遞減:素材最齊全者在最前
const LEVEL_ORDER = { "低風險": 3, "中等": 2, "偏高風險": 1, "資料不足": 0 };
function cmp(a, b) {
  const k = sortKey.value;
  if (k === "ready") {
    const d = (a.readiness ?? 0) - (b.readiness ?? 0);
    return d !== 0 ? d : (a.score ?? -1) - (b.score ?? -1);   // 同級再依評分
  }
  if (k === "name") return String(a.name || "").localeCompare(String(b.name || ""), "zh-Hant");
  if (k === "code") return String(a.code || "").localeCompare(String(b.code || ""), undefined, { numeric: true });
  if (k === "level") return (LEVEL_ORDER[a.level] ?? -1) - (LEVEL_ORDER[b.level] ?? -1);
  const av = a.score ?? -1, bv = b.score ?? -1;      // 未評分一律沉底
  return av - bv;
}

const caseListRaw = computed(() => {
  const q = query.value.trim();
  return cases.value.filter((c) => !q || c.name.includes(q) || c.id.includes(q));
});
const caseList = computed(() => {
  const arr = [...caseListRaw.value].sort(cmp);
  return sortAsc.value ? arr : arr.reverse();
});
</script>

<template>
  <div>
    <!-- Hero 色帶:標語 + 大搜尋框 + 統計數字(data.taipei 式) -->
    <div class="bg-sky-900 text-white">
      <div class="max-w-5xl mx-auto px-4 py-8">
        <h1 class="text-2xl font-bold mb-1">多源情資交叉驗證,開啟新興產業授信新視野</h1>
        <p class="text-sky-200 text-sm mb-5">整合知識圖譜財報、商工登記、月營收、藥品許可證、市場股價與新聞等多源資料,由 AI 審查委員會為每一件授信案把關。</p>
        <form role="search" @submit.prevent class="flex max-w-2xl">
          <label for="case-search" class="sr-only">搜尋案件</label>
          <input id="case-search" type="search" v-model="query"
            placeholder="請輸入公司名稱或統一編號…" autocomplete="off" spellcheck="false"
            :class="`flex-1 h-12 px-4 text-slate-900 bg-white rounded-l-sm placeholder-slate-400 ${focusRing}`" />
          <button type="submit" :class="`h-12 px-6 bg-amber-500 hover:bg-amber-400 text-sky-950 font-bold rounded-r-sm motion-safe:transition-colors ${focusRing}`">
            搜尋
          </button>
        </form>
        <dl class="flex gap-8 mt-6 text-sm flex-wrap">
          <div v-for="[k, v] in [['介接資料源', '4 項'], ['市場訊號母體', universe ? `${universe.universe} 家` : '—'], ['授信案件', `${cases.length} 件`]]" :key="k" class="flex items-baseline gap-2">
            <dt class="text-sky-300">{{ k }}</dt>
            <dd :class="`${num} text-xl font-bold`">{{ v }}</dd>
          </div>
        </dl>
      </div>
    </div>

    <main id="main" class="max-w-5xl mx-auto px-4 py-6 w-full">
      <nav aria-label="麵包屑" class="text-sm text-slate-500">
        <ol class="flex items-center gap-1 flex-wrap">
          <li>首頁</li>
          <li class="flex items-center gap-1"><span aria-hidden="true" class="text-slate-400 px-0.5">/</span><span aria-current="page" class="text-slate-700">案件總覽</span></li>
        </ol>
      </nav>

      <div class="mt-4">
        <div class="flex items-center justify-between gap-4 mb-3">
          <h2 class="border-l-4 border-sky-800 pl-3 text-lg font-bold text-slate-900">
            授信案件清單<span v-if="query.trim()" class="text-sm font-normal text-slate-500">(搜尋:「{{ query.trim() }}」,共 {{ caseList.length }} 件)</span>
          </h2>
          <!-- 排序:預設依評分高至低 -->
          <div class="flex items-center gap-1.5 flex-wrap">
            <label for="sortkey" class="text-xs text-slate-500">排序</label>
            <select id="sortkey" v-model="sortKey"
              :class="`text-xs h-8 px-2 border border-slate-400 bg-white rounded-sm text-slate-800 ${focusRing}`">
              <option value="ready">歷史資料</option>
              <option value="score">綜合評分</option>
              <option value="name">公司名稱</option>
              <option value="code">證券代號</option>
              <option value="level">風險等級</option>
            </select>
            <button @click="sortAsc = !sortAsc" :aria-label="sortAsc ? '改為遞減' : '改為遞增'"
              :class="`h-8 px-2 text-xs border border-slate-400 bg-white hover:bg-slate-100 rounded-sm text-slate-700 motion-safe:transition-colors ${focusRing}`">
              <span aria-hidden="true" class="inline-block motion-safe:transition-transform duration-200"
                :class="sortAsc ? 'rotate-180' : ''">▼</span>
              {{ sortAsc ? "遞增" : "遞減" }}
            </button>
          </div>
        </div>

        <LoadingCard v-if="loading"
          title="正在盤點知識庫企業"
          :steps="['連線 EAP 知識庫', '清點公司清單', '併入市場評分', '整理案件列表']" />

        <div v-else-if="caseList.length === 0" class="border border-slate-300 bg-white p-10 text-center text-sm text-slate-500">
          查無符合的案件,請調整搜尋條件。
        </div>
        <ul v-else class="border-t-2 border-sky-900">
          <li v-for="(c, i) in caseList" :key="c.id" class="border-b border-slate-300">
            <button @click="emit('open-case', c)"
              :style="{ animationDelay: `${Math.min(i, 12) * 25}ms` }"
              :class="`w-full text-left bg-white hover:bg-sky-50 hover:pl-5 px-4 py-3.5 flex items-center gap-4 flex-wrap motion-safe:transition-all group motion-safe:animate-[fadeUp_.35s_ease-out] ${focusRing}`">
              <span :class="`${num} text-xs text-slate-500 w-24 shrink-0`">{{ c.updated }}</span>
              <span class="flex-1 min-w-48">
                <span class="text-slate-900 font-medium group-hover:text-sky-900 group-hover:underline underline-offset-2">{{ c.name }}</span>
                <span :class="`block text-xs text-slate-500 mt-0.5 ${num}`">
                  <template v-if="c.code">證券代號 {{ c.code }}</template>
                  <template v-if="c.ban"> · 統編 {{ c.ban }}</template>
                  <template v-if="!c.code && !c.ban">統一編號 {{ c.id }}</template>
                </span>
              </span>
              <span class="text-xs text-slate-600 w-24">
                <template v-if="c.level">市場評級:<span :class="['font-medium', LEVEL_CLS[c.level]]">{{ c.level }}</span></template>
                <template v-else>目前階段:<span class="font-medium text-slate-800">{{ STAGE_LABEL[c.stage] }}</span></template>
              </span>
              <span class="w-16 text-right">
                <span v-if="c.score !== null && c.score !== undefined" :class="`${num} font-bold text-lg ${LEVEL_CLS[c.level] || 'text-sky-900'}`">{{ c.score }}<span class="text-xs text-slate-500 font-normal"> 分</span></span>
                <span v-else class="text-xs text-slate-400">{{ c.level || "評分中" }}</span>
              </span>
            </button>
          </li>
        </ul>
      </div>

      <div class="mt-8">
        <div class="flex items-center justify-between gap-4 mb-3">
          <h2 class="border-l-4 border-sky-800 pl-3 text-lg font-bold text-slate-900">最新公告</h2>
        </div>
        <ul class="border-t-2 border-sky-900">
          <li v-for="([d, tg, t], i) in ANNOUNCEMENTS" :key="i" class="border-b border-slate-300 bg-white px-4 py-3 flex items-center gap-3 text-sm flex-wrap">
            <span :class="`${num} text-xs text-slate-500 w-24 shrink-0`">{{ d }}</span>
            <span class="text-xs px-1.5 py-0.5 border border-amber-400 bg-amber-50 text-amber-800 rounded-sm shrink-0">{{ tg }}</span>
            <a href="#" @click.prevent :class="`text-slate-800 hover:text-sky-900 hover:underline underline-offset-2 rounded-sm ${focusRing}`">{{ t }}</a>
          </li>
        </ul>
      </div>
    </main>
  </div>
</template>