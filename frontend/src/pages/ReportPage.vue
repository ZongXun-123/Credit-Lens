<script setup>
// 頁面 4:報告中心(v1.4:報告歸檔 + 星號標記 + 刪除)
// 資料流:列表 = 後端 reports/ 目錄實際 PDF + 快取資料庫分數;星號存資料庫,重整不掉。
import { ref, computed, onMounted } from "vue";
import { focusRing, num } from "../constants.js";
import { reviewApi, API_BASE } from "../api.js";
import { REPORTS } from "../mock.js";
import LoadingCard from "../components/LoadingCard.vue";

const emit = defineEmits(["open-case"]);
const reports = ref([]);
const live = ref(false);
const loading = ref(true);
onMounted(load);
async function load() {
  loading.value = true;
  try {
    const r1 = await reviewApi("/api/reports/list", { status: "全部" }, { reports: REPORTS }, 400);
    reports.value = r1.reports;
    live.value = r1.source === "live";
  } catch (e) { reports.value = []; }
  loading.value = false;
}

const filter = ref("全部");
const filterOptions = ["全部", "已加星"];
const reportList = computed(() =>
  reports.value.filter((r) => filter.value === "全部" || r.starred));

const scored = computed(() => reports.value.filter((r) => r.score !== null && r.score !== undefined));
const stats = computed(() => [
  ["已歸檔報告", `${reports.value.length} 份`],
  ["平均綜合評分", scored.value.length ? `${Math.round(scored.value.reduce((a, r) => a + r.score, 0) / scored.value.length)} 分` : "—"],
  ["已加星報告", `${reports.value.filter((r) => r.starred).length} 份`],
]);

// 點公司名稱 → 回到該案件頁(帶最少必要欄位,案件頁會自行載入其餘資料)
function openCase(r) {
  emit("open-case", {
    id: r.id, code: r.id, ban: null, name: r.company,
    industry: "生技製藥", stage: "post", score: r.score ?? null, updated: r.date,
  });
}

function download(r) {
  if (r.report_url) window.open(new URL(r.report_url, API_BASE).href, "_blank");
  else alert("此為示範資料列,無實體 PDF。至案件頁完成審查會議後點「產出報告」即可歸檔。");
}

// 星號:標記重點報告(存後端資料庫)
const acting = ref("");
async function toggleStar(r) {
  if (!r.filename) return;
  acting.value = r.filename;
  try {
    await reviewApi("/api/reports/star", { filename: r.filename, id: r.id, starred: !r.starred },
      { starred: !r.starred }, 200);
    r.starred = !r.starred;
  } catch (e) { alert(`標記失敗:${e.message}`); }
  acting.value = "";
}

// 刪除:先確認,成功後自列表移除
async function removeReport(r) {
  if (!r.filename) return;
  if (!confirm(`確定刪除「${r.company}」${r.version} 的報告?此動作無法復原。`)) return;
  acting.value = r.filename;
  try {
    await reviewApi("/api/reports/delete", { filename: r.filename }, { deleted: r.filename }, 200);
    reports.value = reports.value.filter((x) => x.filename !== r.filename);
  } catch (e) { alert(`刪除失敗:${e.message}`); }
  acting.value = "";
}
</script>

<template>
  <main id="main" class="max-w-5xl mx-auto px-4 py-6 w-full">
    <nav aria-label="麵包屑" class="text-sm text-slate-500">
      <ol class="flex items-center gap-1 flex-wrap">
        <li>首頁</li>
        <li class="flex items-center gap-1"><span aria-hidden="true" class="text-slate-400 px-0.5">/</span><span aria-current="page" class="text-slate-700">報告中心</span></li>
      </ol>
    </nav>

    <!-- 統計小卡 -->
    <div class="mt-4 grid sm:grid-cols-3 gap-3">
      <div v-for="[k, v] in stats" :key="k" class="bg-white border border-slate-300 border-t-4 border-t-sky-900 px-4 py-3">
        <div class="text-xs text-slate-500">{{ k }}</div>
        <div :class="`${num} font-bold text-2xl text-sky-900 mt-0.5`">{{ v }}</div>
      </div>
    </div>

    <!-- 報告列表 -->
    <div class="mt-6">
      <div class="flex items-center justify-between gap-4 mb-3 flex-wrap">
        <h2 class="border-l-4 border-sky-800 pl-3 text-lg font-bold text-slate-900">授信審查報告</h2>
        <div class="flex items-center gap-2 text-sm">
          <label for="rep-filter" class="text-slate-600">狀態</label>
          <select id="rep-filter" v-model="filter"
            :class="`h-9 px-2 border border-slate-400 rounded-sm bg-white text-slate-800 ${focusRing}`">
            <option v-for="o in filterOptions" :key="o" :value="o">{{ o }}</option>
          </select>
        </div>
      </div>

      <LoadingCard v-if="loading" title="正在整理報告清單"
        :steps="['掃描報告目錄', '比對評分紀錄', '解析公司名稱']" />

      <div v-else-if="reportList.length === 0" class="border border-slate-300 bg-white p-10 text-center">
        <p class="text-sm text-slate-500">尚無符合條件的報告。</p>
        <p class="text-xs text-slate-400 mt-1.5 leading-relaxed">
          至案件頁完成「AI 審查會議」後,於「拜訪中與後」頁籤點「產出審查報告」即會自動歸檔於此。
        </p>
      </div>
      <ul v-else class="border-t-2 border-sky-900">
        <li v-for="(r, i) in reportList" :key="i"
          class="border-b border-slate-300 bg-white px-4 py-3 flex items-center gap-4 flex-wrap hover:bg-sky-50 motion-safe:transition-colors">
          <span class="w-24 shrink-0">
            <span :class="`${num} block text-xs text-slate-500`">{{ r.date }}</span>
            <span v-if="r.time" :class="`${num} block text-xs text-slate-400`">{{ r.time }}</span>
          </span>
          <span class="flex-1 min-w-48">
            <button @click="openCase(r)"
              :class="`text-slate-900 font-medium hover:text-sky-800 hover:underline underline-offset-2 text-left rounded-sm ${focusRing}`">
              {{ r.company }} <span aria-hidden="true" class="text-sky-700 text-xs">→</span>
            </button>
            <span :class="`block text-xs text-slate-500 mt-0.5 ${num}`">代號 {{ r.id }}</span>
          </span>
          <span class="text-xs px-1.5 py-0.5 border border-sky-300 bg-sky-50 text-sky-900 rounded-sm shrink-0">{{ r.version }}</span>
          <span class="w-24 text-right shrink-0">
            <template v-if="r.score !== null && r.score !== undefined">
              <span :class="`${num} font-bold text-lg text-sky-900`">{{ r.score }}</span><span class="text-xs text-slate-500"> 分</span>
              <span v-if="r.score_src" class="block text-xs text-slate-400">{{ r.score_src }}</span>
            </template>
            <span v-else class="text-xs text-slate-400">未評分</span>
          </span>
          <button @click="toggleStar(r)" :disabled="acting === r.filename || !r.filename"
            :aria-pressed="r.starred" :aria-label="r.starred ? '取消星號' : '加上星號'"
            :class="[`w-9 h-9 text-lg border rounded-sm shrink-0 motion-safe:transition-colors ${focusRing}`,
              r.starred ? 'text-amber-500 border-amber-300 bg-amber-50 hover:bg-amber-100'
                        : 'text-slate-300 border-slate-300 bg-white hover:text-amber-400 hover:border-amber-300',
              (!r.filename) && 'opacity-40 cursor-not-allowed']">
            {{ r.starred ? "★" : "☆" }}
          </button>
          <button @click="download(r)"
            :class="`px-3 h-9 text-xs font-bold text-white bg-sky-900 hover:bg-sky-800 rounded-sm shrink-0 motion-safe:transition-colors ${focusRing}`">
            下載 PDF
          </button>
          <button @click="removeReport(r)" :disabled="acting === r.filename || !r.filename"
            :class="[`px-2.5 h-9 text-xs border rounded-sm shrink-0 motion-safe:transition-colors ${focusRing}`,
              'text-rose-800 border-rose-300 bg-white hover:bg-rose-50 disabled:opacity-40']">
            刪除
          </button>
        </li>
      </ul>
    </div>

  </main>
</template>
