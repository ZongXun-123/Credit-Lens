<script setup>
// 頁面 3:情資查詢(僅接受 8 碼統一編號;不知道統編可用「查統編」模糊搜尋)
// 區塊:市場訊號 · 公司登記 · 月營收 · 藥品許可證 · 近期新聞
// 已移除:訴訟紀錄、裁罰紀錄(EAP 與公開資料源皆無此資料)、企業關係圖譜
import { ref, computed, onMounted } from "vue";
import { focusRing, num } from "../constants.js";
import LoadingCard from "../components/LoadingCard.vue";
import { reviewApi } from "../api.js";
import { INTEL, CASES} from "../mock.js";

const props = defineProps({ initialQuery: { type: String, default: "" } });
const emit = defineEmits(["open-case"]);

const query = ref("");
const searched = ref(false);
const searching = ref(false);
const hit = ref(null);
const signal = ref(null);
const inputError = ref("");

const isBan = (s) => /^\d{8}$/.test(String(s).trim());

async function doSearch(q = query.value) {
  query.value = q;
  const key = String(q).trim();
  inputError.value = "";
  hit.value = null;
  signal.value = null;

  if (!key) { searched.value = false; return; }
  if (!isBan(key)) {
    inputError.value = "請輸入 8 碼統一編號。不知道統編請點右側「查統編」。";
    searched.value = false;
    return;
  }

  searched.value = true;
  searching.value = true;
  try {
    hit.value = await reviewApi("/api/intel/lookup", { query: key }, INTEL[key] || null, 700);
  } catch (e) {
    hit.value = null;
  }
  // 市場訊號:以統編回查證券代號(母體為生技製藥 36 家)
  try {
    const uni = await reviewApi("/api/market/universe", {}, null, 200);
    const m = (uni?.companies || []).find((c) => c.ban === key);
    if (m) signal.value = await reviewApi("/api/market/signal", { company_id: m.company_id }, null, 200);
  } catch (e) { /* 非母體公司,略過 */ }
  searching.value = false;
}

onMounted(() => {
  const q = String(props.initialQuery || "").trim();
  if (!q) return;
  if (isBan(q)) {
    doSearch(q);
  } else {
    // 從案件帶入公司名稱時,直接開啟查統編面板並代為搜尋
    lookupOpen.value = true;
    lookupKw.value = q;
    runLookup();
  }
});

// ---- 統編模糊查詢 ----
const lookupOpen = ref(false);
const lookupKw = ref("");
const lookupBusy = ref(false);
const lookupRows = ref([]);
const lookupDone = ref(false);

async function runLookup() {
  if (!lookupKw.value.trim()) return;
  lookupBusy.value = true;
  lookupDone.value = false;
  try {
    const r = await reviewApi("/api/company/search", { query: lookupKw.value }, { companies: [] }, 300);
    lookupRows.value = r.companies || [];
  } catch (e) { lookupRows.value = []; }
  lookupBusy.value = false;
  lookupDone.value = true;
}
function pickCompany(c) {
  if (!c.ban) return;
  lookupOpen.value = false;
  doSearch(c.ban);
}

// 由情資查詢結果直接組出案件物件(含證券代號,審查會議才查得到知識圖譜)
function createCase() {
  const h = hit.value;
  if (!h) return;
  const known = CASES.find((x) => x.id === h.id);
  emit("open-case", known || {
    id: h.id,
    ban: h.id,
    code: signal.value?.company_id || "",
    name: h.name || h.id,
    industry: h.industry || (signal.value ? "生技製藥" : "—"),
    stage: "pre",
    score: signal.value?.market_score ?? null,
    level: signal.value?.level || null,
    updated: new Date().toISOString().slice(0, 10),
  });
}

const maxRev = computed(() => Math.max(...(hit.value?.revenue?.map((r) => r.val) || [1])));
// 新聞極性(關鍵字比對結果,非情感分析模型;hover 可看命中的關鍵字)
const SENTI = {
  pos: { label: "正面", cls: "bg-emerald-50 text-emerald-800 border-emerald-400" },
  neu: { label: "中性", cls: "bg-slate-100 text-slate-500 border-slate-300" },
  neg: { label: "負面", cls: "bg-rose-50 text-rose-800 border-rose-400" },
};

const LEVEL_CLS = {
  "低風險": "text-emerald-700", "中等": "text-amber-700",
  "偏高風險": "text-rose-700", "資料不足": "text-slate-400",
};
// 複製 TIPO 檢索式到剪貼簿

const srcTag = "inline-block px-1.5 py-0.5 rounded-sm text-xs bg-slate-100 text-slate-600 border border-slate-300";
const liveTag = "ml-1 text-xs font-normal px-1.5 py-0.5 border border-emerald-400 bg-emerald-50 text-emerald-800 rounded-sm";
</script>

<template>
  <main id="main" class="max-w-5xl mx-auto px-4 py-6 w-full">
    <nav aria-label="麵包屑" class="text-sm text-slate-500">
      <ol class="flex items-center gap-1 flex-wrap">
        <li>首頁</li>
        <li class="flex items-center gap-1"><span aria-hidden="true" class="text-slate-400 px-0.5">/</span><span aria-current="page" class="text-slate-700">情資查詢</span></li>
      </ol>
    </nav>

    <div class="mt-4">
      <h2 class="border-l-4 border-sky-800 pl-3 text-lg font-bold text-slate-900 mb-1">多源情資查詢</h2>
      <p class="text-sm text-slate-600 mb-3">以統一編號查詢商工登記、月營收、藥品許可證、近期新聞與股價市場訊號。</p>

      <form role="search" @submit.prevent="doSearch()" class="flex max-w-2xl">
        <label for="intel-search" class="sr-only">查詢統一編號</label>
        <input id="intel-search" type="search" v-model="query" inputmode="numeric" maxlength="8"
          placeholder="請輸入 8 碼統一編號…" autocomplete="off" spellcheck="false"
          :class="`flex-1 h-11 px-4 text-slate-900 bg-white border border-slate-400 border-r-0 rounded-l-sm placeholder-slate-400 ${num} ${focusRing}`" />
        <button type="submit" :class="`h-11 px-6 bg-sky-900 hover:bg-sky-800 text-white font-bold rounded-r-sm motion-safe:transition-colors ${focusRing}`">查詢</button>
        <button type="button" @click="lookupOpen = !lookupOpen" :aria-expanded="lookupOpen"
          :class="`ml-3 h-11 px-4 bg-white border border-slate-400 rounded-sm text-sky-900 font-bold text-sm hover:bg-sky-50 motion-safe:transition-colors ${focusRing}`">
          不知道統編?
        </button>
      </form>

      <p v-if="inputError" role="alert" class="text-xs text-rose-700 mt-2 motion-safe:animate-[shake_.35s_ease-out]">{{ inputError }}</p>
      <p v-else class="text-xs text-slate-500 mt-2">
        範例:
        <button @click="doSearch('15458455')" :class="`text-sky-800 hover:underline underline-offset-2 rounded-sm px-0.5 ${num} ${focusRing}`">15458455(臺灣永光化學工業)</button>
        <span class="mx-1 text-slate-300">|</span>
        <button @click="doSearch('22662545')" :class="`text-sky-800 hover:underline underline-offset-2 rounded-sm px-0.5 ${num} ${focusRing}`">22662545(旭富製藥科技)</button>
      </p>

      <!-- 統編模糊查詢 -->
      <div v-if="lookupOpen" class="mt-3 border border-sky-300 bg-sky-50 p-4 max-w-2xl motion-safe:animate-[fadeUp_.3s_ease-out]">
        <div class="text-sm font-bold text-sky-900 mb-2">以公司名稱查統一編號</div>
        <div class="flex gap-2">
          <input v-model="lookupKw" @keyup.enter="runLookup" placeholder="輸入公司名稱關鍵字,例如「生達」"
            :class="`flex-1 h-9 px-3 text-sm bg-white border border-slate-400 rounded-sm ${focusRing}`" />
          <button @click="runLookup" :disabled="lookupBusy"
            :class="`h-9 px-4 text-sm font-bold text-white bg-sky-900 hover:bg-sky-800 disabled:bg-slate-300 rounded-sm motion-safe:transition-colors ${focusRing}`">
            {{ lookupBusy ? "查詢中…" : "搜尋" }}
          </button>
        </div>
        <div v-if="lookupRows.length" class="mt-3 border-t border-sky-200 pt-2">
          <div v-for="(c, i) in lookupRows" :key="i"
            class="flex items-center gap-3 py-1.5 text-sm flex-wrap border-b border-sky-100 last:border-0 motion-safe:animate-[fadeUp_.3s_ease-out]"
            :style="{ animationDelay: `${i * 30}ms` }">
            <span :class="`${num} text-xs text-slate-500 w-12`" :title="c.code ? '證券代號' : ''">{{ c.code || "—" }}</span>
            <span class="flex-1 min-w-32 text-slate-900">{{ c.name }}</span>
            <span :class="`${num} text-xs ${c.ban ? 'text-slate-700' : 'text-slate-400'}`">{{ c.ban || "無統編對照" }}</span>
            <span class="text-xs px-1.5 py-0.5 border border-slate-300 bg-white text-slate-500 rounded-sm">{{ c.source }}</span>
            <span v-if="c.status" class="text-xs text-slate-400">{{ c.status }}</span>
            <button @click="pickCompany(c)" :disabled="!c.ban"
              :class="['px-2 h-7 text-xs font-bold rounded-sm motion-safe:transition-colors', focusRing,
                c.ban ? 'text-white bg-sky-800 hover:bg-sky-700' : 'text-slate-400 bg-slate-200 cursor-not-allowed']">
              帶入
            </button>
          </div>
        </div>
        <p v-else-if="lookupDone && !lookupBusy" class="mt-2 text-xs text-slate-500">查無符合的公司,請換個關鍵字。</p>
      </div>
    </div>

    <LoadingCard v-if="searching" class="mt-5" title="正在彙整多源情資"
      :steps="['查詢經濟部商工登記', '抓取月營收與藥品許可證', '蒐集近期新聞', '整理情資卡片']" />

    <div v-if="searched && !searching && !hit" class="mt-5 border border-slate-300 bg-white p-10 text-center text-sm text-slate-500">
      查無「{{ query }}」之情資,請確認統一編號是否正確。
    </div>

    <template v-if="hit && !searching">

      <div class="mt-5 pb-3 border-b border-slate-300 flex items-end justify-between gap-4 flex-wrap motion-safe:animate-[fadeUp_.35s_ease-out]">
        <div>
          <h3 class="text-xl font-bold text-slate-900">{{ hit.name || "(未取得公司名稱)" }}</h3>
          <p :class="`text-sm text-slate-500 mt-1 ${num}`">統一編號 {{ hit.id }} · {{ hit.industry || "—" }} · {{ hit.reg && hit.reg.status || "" }}</p>
        </div>
        <button @click="createCase"
          :class="`px-4 py-2 text-sm font-bold text-white bg-amber-600 hover:bg-amber-500 rounded-sm motion-safe:transition-transform hover:-translate-y-0.5 ${focusRing}`">
          以此公司開啟授信案件 →
        </button>
      </div>

      <!-- items-start:各卡片依自身內容決定高度,避免右欄內容多時左欄被拉高留下大片空白 -->
      <div class="mt-4 grid lg:grid-cols-2 gap-4 items-start">
        <!-- 股價市場訊號 -->
        <div v-if="signal" class="bg-white border border-slate-300 border-t-4 border-t-emerald-600 p-4 motion-safe:animate-[fadeUp_.4s_ease-out]">
          <div class="flex items-baseline justify-between flex-wrap gap-2 mb-2">
            <h3 class="text-sm font-bold text-slate-900 border-l-4 border-sky-800 pl-2">股價市場訊號</h3>
            <span :class="srcTag">資料來源:TEJ 未調整股價</span>
          </div>
          <div class="flex items-baseline gap-4 flex-wrap">
            <div>
              <div class="text-xs text-slate-500">訊號分數</div>
              <span :class="`${num} font-bold text-4xl ${LEVEL_CLS[signal.level]}`">{{ signal.market_score === null ? "—" : signal.market_score }}</span>
              <span :class="`ml-2 text-sm font-bold ${LEVEL_CLS[signal.level]}`">{{ signal.level }}</span>
            </div>
            <div class="text-xs text-slate-600 leading-relaxed">
              <div :class="num">證券代號 {{ signal.company_id }} · 同業母體 {{ signal.meta && signal.meta.universe }} 家</div>
              <div v-if="signal.metrics && signal.metrics.vol_full_pct !== null" :class="num">
                年化波動 {{ signal.metrics.vol_full_pct }}% · 最大回撤 {{ signal.metrics.mdd_pct }}%
              </div>
            </div>
          </div>
          <p class="mt-2 text-xs text-slate-600 leading-relaxed">{{ signal.reading && signal.reading.recommendation }}</p>
        </div>

        <!-- 公司登記 -->
        <div class="bg-white border border-slate-300 p-4 motion-safe:animate-[fadeUp_.45s_ease-out]">
          <div class="flex items-baseline justify-between flex-wrap gap-2 mb-2">
            <h3 class="text-sm font-bold text-slate-900 border-l-4 border-sky-800 pl-2">公司登記資料
              <span v-if="hit.reg && hit.reg._source === 'live'" :class="liveTag">即時查詢</span>
            </h3>
            <span :class="srcTag">資料來源:經濟部商工登記</span>
          </div>
          <dl class="text-sm space-y-1.5">
            <div class="flex gap-2"><dt class="w-20 shrink-0 text-slate-500">資本額</dt><dd :class="`text-slate-800 ${num}`">{{ hit.reg && hit.reg.capital || "—" }}</dd></div>
            <div class="flex gap-2"><dt class="w-20 shrink-0 text-slate-500">設立日期</dt><dd :class="`text-slate-800 ${num}`">{{ hit.reg && hit.reg.founded || "—" }}</dd></div>
            <div class="flex gap-2"><dt class="w-20 shrink-0 text-slate-500">代表人</dt><dd class="text-slate-800">{{ hit.reg && hit.reg.chairman || "—" }}</dd></div>
            <div class="flex gap-2"><dt class="w-20 shrink-0 text-slate-500">登記地址</dt><dd class="text-slate-800">{{ hit.reg && hit.reg.address || "—" }}</dd></div>
          </dl>
        </div>

        <!-- 月營收 -->
        <div class="bg-white border border-slate-300 p-4 motion-safe:animate-[fadeUp_.5s_ease-out]">
          <div class="flex items-baseline justify-between flex-wrap gap-2 mb-2">
            <h3 class="text-sm font-bold text-slate-900 border-l-4 border-sky-800 pl-2">月營收(億元)</h3>
            <span :class="srcTag">資料來源:TWSE OpenAPI</span>
          </div>
          <template v-if="hit.revenue && hit.revenue.length">
            <p v-if="hit.revenue.length === 1" class="text-xs text-slate-500 mb-2">
              TWSE 該資料集僅提供最新月份;歷史趨勢需逐月累積。
            </p>
            <!-- 單筆用固定寬度並排說明,多筆才畫長條圖 -->
            <div v-if="hit.revenue.length === 1" class="flex items-end gap-5 pt-1">
              <div class="text-center">
                <div :class="`${num} font-bold text-3xl text-sky-900`">{{ hit.revenue[0].val }}</div>
                <div class="text-xs text-slate-500 mt-0.5">億元</div>
              </div>
              <div class="pb-1">
                <div :class="`text-sm text-slate-700 ${num}`">{{ hit.revenue[0].m }} 月營收</div>
                <div :class="`text-sm font-bold ${num} ${hit.revenue[0].yoy >= 0 ? 'text-emerald-700' : 'text-rose-700'}`">
                  年增率 {{ hit.revenue[0].yoy >= 0 ? "+" : "" }}{{ hit.revenue[0].yoy }}%
                </div>
              </div>
            </div>
            <div v-else class="flex items-end gap-3 h-32 pt-2" role="img" aria-label="月營收長條圖">
              <div v-for="r in hit.revenue" :key="r.m" class="flex-1 flex flex-col items-center gap-1 min-w-0">
                <span :class="`text-xs font-bold text-slate-800 ${num}`">{{ r.val }}</span>
                <div class="w-full bg-sky-800 rounded-t-sm motion-safe:animate-[growUp_.6s_ease-out]"
                  :style="{ height: `${Math.max(10, (r.val / maxRev) * 76)}px` }" />
                <span :class="`text-xs text-slate-500 ${num}`">{{ r.m }}</span>
                <span :class="`text-xs ${num} ${r.yoy >= 0 ? 'text-emerald-700' : 'text-rose-700'}`">{{ r.yoy >= 0 ? "+" : "" }}{{ r.yoy }}%</span>
              </div>
            </div>
          </template>
          <p v-else class="text-sm text-slate-500">非上市公司或無 TWSE 營收資料。</p>
        </div>

        <!-- 藥品許可證 -->
        <div class="bg-white border border-slate-300 p-4 motion-safe:animate-[fadeUp_.55s_ease-out]">
          <div class="flex items-baseline justify-between flex-wrap gap-2 mb-2">
            <h3 class="text-sm font-bold text-slate-900 border-l-4 border-sky-800 pl-2">藥品許可證概況
              <span v-if="hit.licenses && hit.licenses._source === 'live'" :class="liveTag">即時查詢</span>
            </h3>
            <span :class="srcTag">資料來源:衛福部食藥署</span>
          </div>
          <template v-if="hit.licenses">
            <div class="flex gap-6 text-sm mb-3">
              <div><div class="text-xs text-slate-500">有效許可證</div><div :class="`${num} font-bold text-xl text-sky-900`">{{ hit.licenses.count }} 張</div></div>
              <div><div class="text-xs text-slate-500">新藥/新成分</div><div :class="`${num} font-bold text-xl text-sky-900`">{{ hit.licenses.new_drug }} 張</div></div>
            </div>
            <div v-if="hit.licenses.recent && hit.licenses.recent.length" class="text-xs text-slate-500 mb-1">近期取得</div>
            <ul>
              <li v-for="(l, i) in (hit.licenses.recent || [])" :key="i"
                class="border-b border-slate-200 last:border-0 py-1.5 flex items-center gap-3 text-sm flex-wrap">
                <span :class="`${num} text-xs text-slate-500 shrink-0`">{{ l.date }}</span>
                <span class="text-slate-800 flex-1 min-w-32">{{ l.name }}</span>
                <span :class="`${num} text-xs text-slate-500 shrink-0`">{{ l.no }}</span>
              </li>
            </ul>
          </template>
          <p v-else class="text-sm text-slate-500">查無西藥許可證(醫療器材、化粧品廠商屬正常)。</p>
        </div>

        <!-- 近期新聞 -->
        <div class="lg:col-span-2 bg-white border border-slate-300 p-4 motion-safe:animate-[fadeUp_.6s_ease-out]">
          <div class="flex items-baseline justify-between flex-wrap gap-2 mb-2">
            <h3 class="text-sm font-bold text-slate-900 border-l-4 border-sky-800 pl-2">近期新聞
              <span v-if="hit.news_source === 'live'" :class="liveTag">即時查詢</span>
            </h3>
            <span :class="srcTag">資料來源:Google News</span>
          </div>
          <ul v-if="hit.news && hit.news.length">
            <li v-for="(n, i) in hit.news" :key="i"
              class="border-b border-slate-200 last:border-0 py-2 flex items-center gap-3 text-sm flex-wrap hover:bg-sky-50 motion-safe:transition-colors">
              <span :class="`${num} text-xs text-slate-500 shrink-0 w-20`">{{ n.date }}</span>
              <a v-if="n.url" :href="n.url" target="_blank" rel="noopener"
                :class="`text-slate-800 flex-1 min-w-40 hover:text-sky-900 hover:underline underline-offset-2 rounded-sm ${focusRing}`">{{ n.title }}</a>
              <span v-else class="text-slate-800 flex-1 min-w-40">{{ n.title }}</span>
              <span v-if="n.senti && SENTI[n.senti]"
                :title="n.senti_hit ? `命中關鍵字:${n.senti_hit}` : '未命中任何關鍵字'"
                :class="['text-xs px-1.5 py-0.5 border rounded-sm shrink-0 cursor-help', SENTI[n.senti].cls]">
                {{ SENTI[n.senti].label }}
              </span>
            </li>
          </ul>
          <p v-else class="text-sm text-slate-500">查無近期新聞。</p>
          <p class="text-xs text-slate-400 mt-2 leading-relaxed">
            依 Google News 相關性排序,點擊標題開啟原文。極性標示為關鍵字規則比對(含否定詞偵測,如「未通過」判為負面),
            非情感分析模型;滑鼠移至標籤可查看命中的關鍵字。授信情境下負向優先,同時命中時以負面呈現。
          </p>
        </div>
      </div>
    </template>
  </main>
</template>