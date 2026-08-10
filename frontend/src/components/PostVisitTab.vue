<script setup>
// 頁籤 3:拜訪中與後(原「拜訪中提詞」與「拜訪後評分」已合併)
//   ① 防禦提問單對照(面談時逐題確認)
//   ② 會議紀錄輸入(手動輸入或上傳檔案)
//   ③ 結構化萃取 → 評分瀑布 → 產出 PDF 報告
// 資料來源 = 規格書 5.9 /api/postvisit/extract、5.10 /api/postvisit/score、5.6 /api/report
import { ref, computed, onMounted, onUnmounted } from "vue";
import { VERDICT, focusRing, num } from "../constants.js";
import LoadingCard from "./LoadingCard.vue";
import { reviewApi, USE_MOCK, API_BASE } from "../api.js";
import { MOCK, SAMPLE_NOTES } from "../mock.js";
import { store } from "../store.js";
import WaterfallChart from "./WaterfallChart.vue";

const props = defineProps({ c: { type: Object, required: true } });

// ============================================================
// 防禦提問單對照(原「拜訪中提詞」頁籤的內容,合併至此)
// 來源 = 5.7 /api/pre/brief;萃取完成後對應各題是否被化解
// ============================================================
const questions = ref([]);
onMounted(async () => {
  try {
    const brief = await reviewApi("/api/pre/brief",
      { company_id: props.c.id, company_code: props.c.code || "", company_name: props.c.name, company_code: props.c.code || "" },
      { questions: MOCK.questions }, 500);
    questions.value = brief.questions || [];
  } catch (e) { questions.value = []; }
});

/** 將萃取出的風險點回應對應回提問單(以維度名稱或關鍵字重疊比對)。 */
function verdictOf(q) {
  const rs = ext.value?.responses || [];
  const norm = (s) => String(s || "").replace(/\s/g, "");
  const dim = norm(q.dim), text = norm(q.q);
  const hit = rs.find((r) => {
    const risk = norm(r.risk);
    if (!risk) return false;
    if (dim && (risk.includes(dim) || dim.includes(risk))) return true;
    // 取風險描述的前四字與提問內容比對,涵蓋「資金銜接方案」對「資金缺口」這類情形
    const key = risk.slice(0, 4);
    return key.length >= 2 && text.includes(key);
  });
  return hit ? hit.verdict : null;
}

const notes = ref(SAMPLE_NOTES);

// ============================================================
// 會議紀錄輸入:手動輸入 / 貼上 / 上傳檔案(txt、md 前端直讀,docx 由後端解析)
// ============================================================
const fileInput = ref(null);
const fileMsg = ref("");
const fileBusy = ref(false);

function pickFile() { fileInput.value?.click(); }

async function onFile(e) {
  const f = e.target.files?.[0];
  e.target.value = "";                       // 允許重選同一檔
  if (!f) return;
  fileMsg.value = ""; fileBusy.value = true;
  try {
    const lower = f.name.toLowerCase();
    let text = "";
    if (lower.endsWith(".txt") || lower.endsWith(".md")) {
      text = await f.text();
    } else if (lower.endsWith(".docx")) {
      const b64 = await new Promise((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(String(r.result).split(",")[1] || "");
        r.onerror = () => rej(new Error("讀檔失敗"));
        r.readAsDataURL(f);
      });
      const out = await reviewApi("/api/notes/extract_text",
        { filename: f.name, content_b64: b64 }, { text: "" }, 300);
      text = out.text || "";
    } else {
      fileMsg.value = "僅支援 .txt、.md、.docx 檔案。";
      fileBusy.value = false; return;
    }
    if (!text.trim()) { fileMsg.value = "檔案內容為空或無法解析。"; fileBusy.value = false; return; }
    if (notes.value.trim() === SAMPLE_NOTES.trim()) notes.value = "";
    notes.value = (notes.value ? notes.value.replace(/\s*$/, "") + "\n\n" : "") + text.trim();
    fileMsg.value = `已匯入「${f.name}」(${text.trim().length} 字)。`;
  } catch (err2) {
    fileMsg.value = `匯入失敗:${err2.message || err2}`;
  }
  fileBusy.value = false;
}

function clearNotes() { notes.value = ""; fileMsg.value = ""; }

const stage = ref("idle");
const ext = ref(null);
const sc = ref(null);
const busy = computed(() => stage.value === "extracting" || stage.value === "scoring");

// 基準分過期偵測:審查會議頁若重跑了財務／技術,裁決分會更新,
// 已算出的拜訪後評分即與新基準脫節,需提示重新評分。
const scoredStamp = ref(0);
const baseStale = computed(() =>
  !!sc.value && scoredStamp.value > 0 && (store.judgeStamp[props.c.id] || 0) > scoredStamp.value);

const runErr = ref(null);

async function run() {
  ext.value = null; sc.value = null; runErr.value = null; stage.value = "extracting";
  try {
    // 5.9:會議紀錄結構化萃取
    ext.value = await reviewApi("/api/postvisit/extract",
      { company_id: props.c.id, company_code: props.c.code || "", notes: notes.value }, MOCK.postExtract, 1700);
    stage.value = "scoring";
    // 5.10:base_score = AI 審查會議產出的拜訪前基準分(store);未召開過會議時退回 Mock 的 71
    const baseScore = store.judgeByCompany[props.c.id]?.final_score ?? MOCK.judge.final_score;
    scoredStamp.value = store.judgeStamp[props.c.id] || 0;   // 記錄本次評分所依據的裁決版本
    sc.value = await reviewApi("/api/postvisit/score",
      { company_id: props.c.id, company_code: props.c.code || "", base_score: baseScore, extract_result: ext.value }, MOCK.postScore, 1500);
    stage.value = "done";
  } catch (e) {
    runErr.value = e; stage.value = "idle"; // 7.3:顯示 error.message + 重試
  }
}

// 5.6:產出授信審查報告 PDF → 新分頁開啟 report_url
const reporting = ref(false);
// v1.4:與案件頁右上的按鈕行為一致 — 不強制先開審查會議,後端彙整現有分析結果。
async function makeReport() {
  if (USE_MOCK) { alert("Demo(USE_MOCK):整合日將呼叫 POST /api/report 並開啟 PDF"); return; }
  reporting.value = true;
  try {
    const body = { company_id: props.c.id, company_code: props.c.code || "", company_name: props.c.name || "", company_code: props.c.code || "" };
    const judge = store.judgeByCompany[props.c.id];
    if (judge) body.judge_result = judge;
    const r = await reviewApi("/api/report", body, { report_url: "" });
    if (r.report_url) window.open(new URL(r.report_url, API_BASE).href, "_blank");
  } catch (e) {
    alert(e.code === "NO_MATERIAL"
      ? "此公司尚無任何分析結果,無法產出報告。請先執行「AI 審查會議」或「拜訪前情資」。"
      : `報告產出失敗(${e.code}):${e.message}`);
  }
  reporting.value = false;
}
</script>

<template>
  <div class="space-y-4">
    <!-- ① 防禦提問單對照:面談前需釐清的風險點,萃取後標示是否化解 -->
    <div v-if="questions.length" class="bg-white border border-slate-300 border-l-4 border-l-sky-700 p-4 motion-safe:animate-[fadeUp_.35s_ease-out]">
      <div class="flex items-baseline justify-between gap-3 mb-2 flex-wrap">
        <h3 class="text-sm font-bold text-slate-900">面談需釐清的風險點</h3>
        <span class="text-xs text-slate-500">
          {{ ext ? "已依會議紀錄判定各題是否化解" : "面談時逐題確認,回來後輸入紀錄即可自動判定" }}
        </span>
      </div>
      <ol>
        <li v-for="(q, i) in questions" :key="q.id"
          class="border-b border-slate-200 last:border-0 py-2 flex gap-3 items-start motion-safe:animate-[fadeUp_.35s_ease-out]"
          :style="{ animationDelay: `${i * 50}ms` }">
          <span :class="`${num} text-sky-900 font-bold text-sm shrink-0 w-8`">Q{{ q.id }}</span>
          <div class="min-w-0 flex-1">
            <p class="text-sm text-slate-900 leading-relaxed">{{ q.q }}</p>
            <p class="text-xs text-slate-500 mt-0.5">{{ q.dim }} · {{ q.why }}</p>
          </div>
          <span v-if="verdictOf(q)"
            :class="['text-xs px-1.5 py-0.5 border rounded-sm shrink-0 motion-safe:animate-[fadeUp_.3s_ease-out]', VERDICT[verdictOf(q)].cls]">
            {{ VERDICT[verdictOf(q)].label }}
          </span>
          <span v-else class="text-xs text-slate-400 shrink-0">{{ ext ? "紀錄未提及" : "待確認" }}</span>
        </li>
      </ol>
    </div>

    <!-- ② 會議紀錄輸入 -->
    <div class="bg-white border border-slate-300 p-4">
      <div class="flex items-center justify-between gap-3 mb-2 flex-wrap">
        <label for="notes" class="text-sm font-bold text-slate-900">
          會議紀錄<span class="ml-2 text-xs font-normal text-slate-500">面談後可打字、貼上或口述,AI 自動結構化萃取</span>
        </label>
        <div class="flex items-center gap-2">
          <button @click="pickFile" type="button" :disabled="fileBusy"
            :class="`px-3 h-9 text-xs font-bold bg-white border border-slate-400 text-slate-700 hover:bg-slate-100 disabled:opacity-50 rounded-sm motion-safe:transition-colors ${focusRing}`">
            {{ fileBusy ? "匯入中…" : "上傳檔案" }}
          </button>
          <input ref="fileInput" type="file" accept=".txt,.md,.docx" class="sr-only" @change="onFile" aria-label="上傳會議紀錄檔案" />
          <button @click="clearNotes" type="button"
            :class="`px-3 h-9 text-xs text-slate-600 border border-slate-300 rounded-sm hover:bg-slate-100 motion-safe:transition-colors ${focusRing}`">
            清空
          </button>
        </div>
      </div>
      <textarea id="notes" v-model="notes" rows="7" spellcheck="false"
        :class="`w-full border border-slate-300 p-3 text-sm leading-relaxed text-slate-800 resize-none rounded-sm bg-slate-50 focus:bg-white focus:border-sky-700 ${focusRing}`" />
      <p v-if="fileMsg" role="status" class="mt-2 text-xs text-slate-600 motion-safe:animate-[fadeUp_.3s_ease-out]">{{ fileMsg }}</p>
      <p v-else class="mt-2 text-xs text-slate-400">可直接輸入或貼上文字,亦可上傳 .txt / .md / .docx 檔案,內容會接在現有文字之後。</p>

      <button @click="run" :disabled="busy || !notes.trim()"
        :class="`mt-2.5 px-6 h-10 text-sm font-bold text-white bg-sky-900 hover:bg-sky-800 disabled:bg-slate-300 disabled:text-slate-500 rounded-sm motion-safe:transition-colors ${focusRing}`">
        {{ busy ? "分析中…" : "開始分析" }}
      </button>
    </div>

    <div v-if="runErr" role="alert" class="border border-rose-300 border-l-4 border-l-rose-600 bg-rose-50 p-4 flex items-center justify-between gap-4 flex-wrap">
      <div>
        <div class="font-bold text-rose-800 text-sm mb-0.5">分析中斷({{ runErr.code }})</div>
        <p class="text-sm text-slate-800 leading-relaxed">{{ runErr.message }}</p>
      </div>
      <button @click="run" class="px-5 h-10 text-sm font-bold text-white bg-rose-700 hover:bg-rose-600 rounded-sm motion-safe:transition-colors">重試</button>
    </div>

    <LoadingCard v-if="stage === 'extracting'" title="正在分析會議紀錄"
      :steps="['讀取紀錄全文', '辨識承諾事項與期限', '比對風險回應', '標記新發現風險']" />

    <div v-if="ext" class="bg-white border border-slate-300 border-t-4 border-t-sky-900 p-4 space-y-4 motion-safe:animate-[fadeUp_.4s_ease-out]">
      <h3 class="font-bold text-slate-900">結構化萃取結果</h3>

      <div>
        <div class="text-xs font-bold text-slate-700 mb-1.5">一、承諾事項({{ ext.commitments.length }} 項,自動列入追蹤)</div>
        <table class="w-full text-sm border-collapse">
          <thead>
            <tr class="bg-slate-100 text-slate-700 text-xs">
              <th scope="col" class="border border-slate-300 px-2 py-1.5 text-left font-bold">承諾內容</th>
              <th scope="col" class="border border-slate-300 px-2 py-1.5 text-left font-bold w-28">承諾人</th>
              <th scope="col" class="border border-slate-300 px-2 py-1.5 text-left font-bold w-28">期限</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(cm, i) in ext.commitments" :key="i" class="hover:bg-sky-50">
              <td class="border border-slate-300 px-2 py-1.5 text-slate-800">{{ cm.item }}</td>
              <td class="border border-slate-300 px-2 py-1.5 text-slate-600">{{ cm.owner }}</td>
              <td :class="`border border-slate-300 px-2 py-1.5 text-amber-800 ${num}`">{{ cm.due }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div>
        <div class="text-xs font-bold text-slate-700 mb-1.5">二、風險點回應(對應防禦提問單)</div>
        <div v-for="(rp, i) in ext.responses" :key="i"
          class="border border-slate-300 border-t-0 first:border-t px-3 py-2 flex items-center gap-3 flex-wrap hover:bg-sky-50">
          <span class="text-sm text-slate-900 font-medium w-44 shrink-0">{{ rp.risk }}</span>
          <span class="text-xs text-slate-600 flex-1 min-w-40">{{ rp.summary }}</span>
          <span :class="['text-xs px-1.5 py-0.5 border rounded-sm shrink-0', VERDICT[rp.verdict].cls]">{{ VERDICT[rp.verdict].label }}</span>
        </div>
      </div>

      <div v-if="ext.new_risks.length > 0">
        <div class="text-xs font-bold text-rose-800 mb-1.5">三、面談中新發現的風險</div>
        <div v-for="(n, i) in ext.new_risks" :key="i"
          class="border border-rose-300 border-l-4 border-l-rose-600 bg-rose-50 p-3 text-sm text-slate-800 leading-relaxed">{{ n.text }}</div>
      </div>
    </div>

    <div v-if="baseStale" role="alert"


      class="border border-amber-400 border-l-4 border-l-amber-500 bg-amber-50 px-3.5 py-2.5 flex items-center justify-between gap-3 flex-wrap motion-safe:animate-[fadeUp_.3s_ease-out]">


      <span class="text-sm text-amber-900">


        審查會議的裁決分已更新,目前顯示的拜訪後評分是依舊基準算出的,建議重新評分。


      </span>


      <button @click="run()" :disabled="busy"


        :class="`px-3 h-8 text-xs font-bold text-white bg-amber-700 hover:bg-amber-600 disabled:opacity-50 rounded-sm motion-safe:transition-colors ${focusRing}`">


        以新基準重新評分


      </button>


    </div>


    <LoadingCard v-if="stage === 'scoring'" title="正在計算拜訪後評分"
      :steps="['帶入拜訪前基準分', '評估風險化解程度', '計算加減分項', '產出審查建議']" />

    <div v-if="sc" class="bg-white border border-slate-300 border-t-4 border-t-emerald-600 p-4 motion-safe:animate-[fadeUp_.4s_ease-out]">
      <h3 class="font-bold text-slate-900 mb-3">評分瀑布 — 每一分的來源</h3>
      <WaterfallChart :items="sc.waterfall" :final-score="sc.final_score" />
      <div class="mt-4 bg-slate-50 border border-slate-300 p-3 text-sm leading-relaxed">
        <span class="font-bold text-sky-900">審查官建議:</span>
        <span class="text-slate-800"> {{ sc.recommendation }}</span>
      </div>
      <button @click="makeReport"
        :class="`mt-3 px-6 h-11 text-sm font-bold text-white bg-emerald-700 hover:bg-emerald-600 rounded-sm motion-safe:transition-colors ${focusRing}`">
        {{ reporting ? "報告產出中…" : "產出授信審查報告(PDF)" }}
      </button>
    </div>
  </div>
</template>