<script setup>
// 頁面:授信評分說明
// 用互動方式說明四個階段的評分制度與彼此的關聯:
//   財務／技術 Agent → 審查裁決(拜訪前基準分) → 拜訪後覆評 → 報告封面分數
// 全部數值皆與後端實際規則一致(prompts/*.txt 與 main.py 的確定性計算)。
import { ref, computed } from "vue";

const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-1";
const num = "tabular-nums";

// ── 互動一:財務評分試算 ──────────────────────────────
// 自 90 分起扣,每一條門檻對應固定扣分,與 prompts/finance.txt 完全一致。
const FIN_RULES = [
  { key: "dep30", group: "償債", label: "借款依存度 > 30%", deduct: 12, note: "高度仰賴外部融資" },
  { key: "dep20", group: "償債", label: "借款依存度 20% ~ 30%", deduct: 6, note: "融資依賴偏高" },
  { key: "debt", group: "償債", label: "負債比率 > 50%", deduct: 8, note: "財務槓桿偏高" },
  { key: "cur", group: "償債", label: "流動比率 < 100%", deduct: 10, note: "短期償債能力不足" },
  { key: "loss", group: "獲利", label: "合併總損益為負", deduct: 10, note: "本業尚未獲利" },
  { key: "bigloss", group: "獲利", label: "虧損逾 5 億元", deduct: 15, note: "虧損規模重大" },
  { key: "roe", group: "獲利", label: "ROE 為負", deduct: 8, note: "股東權益報酬不佳" },
  { key: "cf", group: "現金流", label: "營運現金流量為負", deduct: 18, note: "還款來源高度依賴外部籌資" },
  { key: "growth", group: "成長", label: "稅後淨利成長率 < -50%", deduct: 7, note: "獲利大幅衰退" },
];
const finPicked = ref(new Set(["dep30", "cf"]));
function toggleFin(k) {
  const s = new Set(finPicked.value);
  s.has(k) ? s.delete(k) : s.add(k);
  // 借款依存度兩個級距互斥,只能擇一
  if (k === "dep30" && s.has("dep30")) s.delete("dep20");
  if (k === "dep20" && s.has("dep20")) s.delete("dep30");
  finPicked.value = s;
}
const finDeduct = computed(() =>
  FIN_RULES.filter((r) => finPicked.value.has(r.key)).reduce((a, r) => a + r.deduct, 0)
);
const finScore = computed(() => Math.max(5, Math.min(95, 90 - finDeduct.value)));
const finGroups = computed(() => {
  const g = {};
  FIN_RULES.forEach((r) => (g[r.group] ??= []).push(r));
  return g;
});

// ── 互動二:技術評分試算 ──────────────────────────────
// 四構面加總,與 prompts/tech.txt 一致。
const TECH_DIMS = [
  { key: "barrier", label: "技術門檻", max: 30, mid: 15,
    desc: "產品領域的技術與法規壁壘、查驗登記難度" },
  { key: "pricing", label: "定價能力", max: 25, mid: 12,
    desc: "以知識庫毛利率推估:>60% 得 18-25、40-60% 得 10-17、<40% 得 0-9" },
  { key: "momentum", label: "產品線動能", max: 25, mid: 12,
    desc: "產品線廣度、藥證取得情形與銷貨成長" },
  { key: "cycle", label: "產業景氣", max: 20, mid: 10,
    desc: "次產業成長性與新聞面:正向 14-20、平穩 7-13、逆風 0-6" },
];
const techVals = ref({ barrier: 24, pricing: 16, momentum: 17, cycle: 14 });
const techScore = computed(() =>
  TECH_DIMS.reduce((a, d) => a + Number(techVals.value[d.key] || 0), 0)
);

// ── 互動三:基礎分與覆評連動 ───────────────────────────
const baseScore = computed(() => Math.round(finScore.value * 0.6 + techScore.value * 0.4));

// 審查官的增減項(示意值,實際由模型依矛盾點給出)
const JUDGE_ADJ = [
  { label: "期程錯配", value: -11, on: true, why: "技術回收屬長期,現金缺口屬立即" },
  { label: "技術佐證", value: 2, on: true, why: "藥證與產品線佐證技術實力" },
  { label: "敘事衝突", value: -4, on: false, why: "兩位 Agent 對同一事實描述不一致" },
];
const judgeAdj = ref(JUDGE_ADJ.map((x) => ({ ...x })));
const judgeSum = computed(() =>
  judgeAdj.value.filter((a) => a.on).reduce((s, a) => s + a.value, 0)
);
const judgeScore = computed(() => Math.max(0, Math.min(100, baseScore.value + judgeSum.value)));

// 拜訪後增減項
const POST_ADJ = [
  { label: "風險已化解", value: 3, on: true, why: "客戶提出具約束力的證明文件" },
  { label: "部分化解", value: 1, on: true, why: "有方向但尚未提供佐證" },
  { label: "承諾具體", value: 2, on: true, why: "承諾事項帶承諾人與到期日" },
  { label: "新增追蹤事項", value: -2, on: true, why: "面談中發現的新風險" },
];
const postAdj = ref(POST_ADJ.map((x) => ({ ...x })));
const postSum = computed(() =>
  postAdj.value.filter((a) => a.on).reduce((s, a) => s + a.value, 0)
);
const postScore = computed(() => Math.max(0, Math.min(100, judgeScore.value + postSum.value)));

// ── 瀑布圖繪製 ───────────────────────────────────────
function waterfall(base, adjustments, final) {
  const items = [{ label: "基準分", value: base, type: "base" }];
  adjustments.filter((a) => a.on).forEach((a) =>
    items.push({ label: a.label, value: a.value, type: a.value >= 0 ? "plus" : "minus" })
  );
  const maxV = Math.max(base, final, 100);
  let cum = 0;
  return items.map((it) => {
    let start;
    if (it.type === "base") { start = 0; cum = it.value; }
    else if (it.value >= 0) { start = cum; cum += it.value; }
    else { cum += it.value; start = cum; }
    return { ...it, left: (start / maxV) * 100, width: (Math.abs(it.value) / maxV) * 100, cum };
  });
}
const judgeWf = computed(() => waterfall(baseScore.value, judgeAdj.value, judgeScore.value));
const postWf = computed(() => waterfall(judgeScore.value, postAdj.value, postScore.value));

// ── 雷達圖(拜訪前情資)─────────────────────────────────
const RADAR = [
  { key: "tech", label: "技術量能", score: 72, benchmark: 60,
    rule: "以毛利率與毛利成長率推估技術含金量,輔以該產品領域的技術與法規門檻。" },
  { key: "market", label: "市場潛力", score: 65, benchmark: 62,
    rule: "營收與獲利成長趨勢,輔以次產業景氣。" },
  { key: "finance", label: "財務體質", score: 45, benchmark: 62,
    rule: "營運現金流為負、借款依存度 >30%、流動比率 <100% 皆為重大扣分;此維只依知識庫數字評分。" },
  { key: "legal", label: "訴訟風險", score: 65, benchmark: 65,
    rule: "知識庫無訴訟資料時給 60-70 中性分,並註明建議另查司法院裁判書系統。" },
  { key: "macro", label: "外部環境", score: 58, benchmark: 60,
    rule: "利率環境與該產業的資金取得難易度。" },
];
const selDim = ref("finance");
const hoverDim = ref("");   // 滑鼠停留的維度,用於 hover 高亮
const cur = computed(() => RADAR.find((r) => r.key === selDim.value) || RADAR[0]);
const R = 78, CX = 130, CY = 122;
function pt(i, val, n = 5) {
  const ang = -Math.PI / 2 + (i * 2 * Math.PI) / n;
  return [CX + Math.cos(ang) * R * (val / 100), CY + Math.sin(ang) * R * (val / 100)];
}
const poly = (key) => RADAR.map((d, i) => pt(i, d[key]).join(",")).join(" ");
const gridRings = [20, 40, 60, 80, 100];

// 分數帶說明(五維共用)
const BANDS = [
  { range: "80 ~ 100", label: "明顯優於同業", cls: "bg-emerald-50 text-emerald-800 border-emerald-300" },
  { range: "60 ~ 79", label: "穩健", cls: "bg-sky-50 text-sky-800 border-sky-300" },
  { range: "40 ~ 59", label: "有隱憂需提問確認", cls: "bg-amber-50 text-amber-800 border-amber-300" },
  { range: "20 ~ 39", label: "明確弱點", cls: "bg-orange-50 text-orange-800 border-orange-300" },
  { range: "0 ~ 19", label: "重大警訊", cls: "bg-rose-50 text-rose-800 border-rose-300" },
];

// 報告封面分數的優先序
// 注意:Tailwind 只掃描原始碼中的完整類名,不能用字串拼接產生
// (例如 `text-${color}-800` 會完全失效),故一律寫成完整類名。
const COVER = [
  { n: 1, label: "拜訪後綜合評分", cond: "已完成拜訪後覆評",
    active: "bg-violet-50 border-violet-500 text-violet-800 font-bold" },
  { n: 2, label: "審查裁決評分", cond: "已召開審查會議但尚未覆評",
    active: "bg-rose-50 border-rose-500 text-rose-800 font-bold" },
  { n: 3, label: "Agent 加權評分", cond: "僅完成財務與技術分析",
    active: "bg-amber-50 border-amber-500 text-amber-800 font-bold" },
  { n: 4, label: "財務分析評分", cond: "僅完成財務分析",
    active: "bg-teal-50 border-teal-500 text-teal-800 font-bold" },
  { n: 5, label: "尚未評分", cond: "無任何分析結果",
    active: "bg-slate-100 border-slate-400 text-slate-700 font-bold" },
];

const STAGES = [
  { t: "① 財務／技術 Agent", d: "兩位 Agent 各自獨立評分", edge: "border-t-amber-600", text: "text-amber-800" },
  { t: "② 審查裁決", d: "加權為基礎分再依矛盾點增減", edge: "border-t-rose-600", text: "text-rose-800" },
  { t: "③ 拜訪後覆評", d: "以裁決分為起點重新計算", edge: "border-t-violet-600", text: "text-violet-800" },
  { t: "④ 報告封面", d: "依完成度取最新的一個分數", edge: "border-t-sky-600", text: "text-sky-800" },
];

const SUMMARY = computed(() => [
  { t: "財務 Agent", v: finScore.value, d: `90 分起扣，扣 ${finDeduct.value} 分`,
    edge: "border-l-amber-600", text: "text-amber-800" },
  { t: "技術 Agent", v: techScore.value, d: "四構面加總",
    edge: "border-l-teal-600", text: "text-teal-800" },
  { t: "審查裁決", v: judgeScore.value,
    d: `基礎分 ${baseScore.value} ${judgeSum.value >= 0 ? "＋" : "−"} ${Math.abs(judgeSum.value)}`,
    edge: "border-l-rose-600", text: "text-rose-800" },
  { t: "拜訪後覆評", v: postScore.value,
    d: `裁決分 ${judgeScore.value} ${postSum.value >= 0 ? "＋" : "−"} ${Math.abs(postSum.value)}`,
    edge: "border-l-violet-600", text: "text-violet-800" },
]);
const coverStep = ref(1);

const level = (s) => (s >= 67 ? "低風險" : s >= 45 ? "中等" : "偏高風險");
const levelCls = (s) =>
  s >= 67 ? "text-emerald-700" : s >= 45 ? "text-amber-700" : "text-rose-700";
</script>

<template>
  <main class="max-w-5xl mx-auto px-4 py-8">
    <!-- 標題 -->
    <header>
      <h1 class="text-2xl font-bold text-slate-900 border-l-4 border-sky-800 pl-3">授信評分說明</h1>
      <p class="mt-3 pl-3 text-sm text-slate-700 leading-relaxed">
        系統共有四個階段的評分，彼此串成一條線而非各自獨立。
        本頁說明每個階段的計算方式，並提供可操作的試算，調整條件即可看到分數如何連動。
      </p>
    </header>

    <!-- 總覽:四階段流程 -->
    <section class="mt-7 rounded-md border border-slate-200 bg-slate-50/80 p-4 sm:p-5">
      <h2 class="text-lg font-bold text-sky-900 bg-sky-100/70 border-l-4 border-sky-700 px-3 py-2 rounded-r-sm -mx-1 mb-3">評分的四個階段</h2>
      <div class="grid md:grid-cols-4 gap-3">
        <div v-for="(s, i) in STAGES" :key="i"
          :class="['relative bg-white border border-slate-300 border-t-4 p-3.5 rounded-sm',
                   'motion-safe:animate-[fadeUp_.4s_ease-out] motion-safe:transition-all',
                   'hover:-translate-y-1 hover:shadow-lg hover:border-slate-400',
                   s.edge]"
          :style="{ animationDelay: `${i * 80}ms` }">
          <div :class="['text-sm font-bold', s.text]">{{ s.t }}</div>
          <p class="mt-1 text-xs text-slate-600 leading-relaxed">{{ s.d }}</p>
          <span v-if="i < 3" aria-hidden="true"
            class="hidden md:block absolute -right-2.5 top-1/2 -translate-y-1/2 text-slate-400 text-lg">›</span>
        </div>
      </div>
      <p class="mt-3 text-xs text-slate-500 leading-relaxed">
        關鍵設計：所有<strong class="text-slate-700">分數的合成</strong>都由後端程式計算，
        AI 只負責判斷各項條件是否成立、以及給出文字說明。
        因此同一組素材無論執行幾次，分數都完全相同。
      </p>
    </section>

    <!-- 一、財務分析 Agent -->
    <section class="mt-7 rounded-md border border-slate-200 bg-slate-50/80 p-4 sm:p-5">
      <h2 class="text-lg font-bold text-amber-900 bg-amber-100/70 border-l-4 border-amber-600 px-3 py-2 rounded-r-sm -mx-1">
        一、財務分析 Agent（自 90 分起扣）
      </h2>
      <p class="mt-2.5 px-1 text-sm text-slate-700 leading-relaxed">
        起始 90 分，每命中一條門檻就扣固定分數，最低 5 分、最高 95 分。
        扣分權重直接反映授信邏輯——<strong>營運現金流為負扣 18 分是全表最重</strong>，
        因為授信最在意的是還款來源。
      </p>

      <div class="mt-4 grid lg:grid-cols-3 gap-4 items-start">
        <!-- 可勾選的條件 -->
        <div class="lg:col-span-2 bg-white border border-slate-300 p-4 rounded-sm">
          <p class="text-xs text-slate-500 mb-3">點選下方條件試算（可複選）</p>
          <div v-for="(rules, g) in finGroups" :key="g" class="mb-3 last:mb-0">
            <div class="text-xs font-bold text-slate-500 mb-1.5">{{ g }}</div>
            <div class="flex flex-wrap gap-2">
              <button v-for="r in rules" :key="r.key" @click="toggleFin(r.key)"
                :aria-pressed="finPicked.has(r.key)" :title="r.note"
                :class="[
                  `px-2.5 py-1.5 text-xs border rounded-sm motion-safe:transition-all ${focusRing}`,
                  'cursor-pointer hover:-translate-y-0.5 hover:shadow-md',
                  finPicked.has(r.key)
                    ? 'bg-rose-100 border-rose-500 text-rose-900 font-bold shadow-sm hover:bg-rose-200'
                    : 'bg-white border-slate-300 text-slate-600 hover:border-rose-400 hover:bg-rose-50 hover:text-rose-800',
                ]">
                {{ r.label }}
                <span :class="`ml-1 ${num}`">−{{ r.deduct }}</span>
              </button>
            </div>
          </div>
        </div>

        <!-- 即時計算結果 -->
        <div class="bg-white border border-slate-300 border-t-4 border-t-amber-600 p-4 rounded-sm">
          <div class="text-xs text-slate-500">財務評分</div>
          <div class="flex items-baseline gap-1.5 mt-1">
            <span :key="finScore"
              :class="`${num} text-4xl font-bold text-amber-800 motion-safe:animate-[popIn_.3s_ease-out]`">
              {{ finScore }}
            </span>
            <span class="text-sm text-slate-500">分</span>
          </div>
          <div class="mt-3 pt-3 border-t border-slate-200 text-xs text-slate-600 space-y-1">
            <div class="flex justify-between"><span>起始分</span><span :class="num">90</span></div>
            <div v-for="r in FIN_RULES.filter((x) => finPicked.has(x.key))" :key="r.key"
              class="flex justify-between text-rose-700 motion-safe:animate-[slideIn_.25s_ease-out]">
              <span class="truncate pr-2">{{ r.label }}</span>
              <span :class="num">−{{ r.deduct }}</span>
            </div>
            <div class="flex justify-between font-bold text-slate-900 pt-1.5 border-t border-slate-200">
              <span>合計</span><span :class="num">{{ finScore }}</span>
            </div>
          </div>
          <p v-if="finDeduct > 85" class="mt-2 text-xs text-slate-500 leading-relaxed">
            扣分已觸及下限，分數固定為 5 分。
          </p>
        </div>
      </div>
      <p class="mt-3 text-xs text-slate-500 leading-relaxed">
        <strong class="text-slate-700">資料查無時不扣分。</strong>
        若知識庫查無該公司財報，系統標記為「資料不足」並給中性值 50 分，
        而非低分——查不到資料不等於體質不良。
      </p>
    </section>

    <!-- 二、技術情報 Agent -->
    <section class="mt-7 rounded-md border border-slate-200 bg-slate-50/80 p-4 sm:p-5">
      <h2 class="text-lg font-bold text-teal-900 bg-teal-100/70 border-l-4 border-teal-600 px-3 py-2 rounded-r-sm -mx-1">
        二、技術情報 Agent（四構面加總）
      </h2>
      <p class="mt-2.5 px-1 text-sm text-slate-700 leading-relaxed">
        與財務相反，技術是<strong>由零往上加</strong>。四個構面各有配分上限，加總即為技術評分。
        拖曳下方滑桿可看到分數變化。
      </p>

      <div class="mt-4 grid lg:grid-cols-3 gap-4 items-start">
        <div class="lg:col-span-2 bg-white border border-slate-300 p-4 rounded-sm space-y-4">
          <div v-for="d in TECH_DIMS" :key="d.key">
            <div class="flex items-center justify-between gap-2 mb-1">
              <label :for="`t-${d.key}`" class="text-sm font-medium text-slate-800">{{ d.label }}</label>
              <span :class="`${num} text-sm font-bold text-teal-800`">
                {{ techVals[d.key] }} <span class="text-xs text-slate-400 font-normal">/ {{ d.max }}</span>
              </span>
            </div>
            <input :id="`t-${d.key}`" type="range" min="0" :max="d.max" v-model.number="techVals[d.key]"
              :class="`w-full accent-teal-700 cursor-pointer slider-hover ${focusRing}`" />
            <p class="mt-1 text-xs text-slate-500 leading-relaxed">{{ d.desc }}</p>
          </div>
        </div>

        <div class="bg-white border border-slate-300 border-t-4 border-t-teal-600 p-4 rounded-sm">
          <div class="text-xs text-slate-500">技術評分</div>
          <div class="flex items-baseline gap-1.5 mt-1">
            <span :key="techScore"
              :class="`${num} text-4xl font-bold text-teal-800 motion-safe:animate-[popIn_.3s_ease-out]`">
              {{ techScore }}
            </span>
            <span class="text-sm text-slate-500">分</span>
          </div>
          <!-- 構面堆疊條 -->
          <div class="mt-3 flex h-3 rounded-sm overflow-hidden bg-slate-100">
            <div v-for="(d, i) in TECH_DIMS" :key="d.key"
              :class="['h-full motion-safe:transition-all duration-300',
                       ['bg-teal-800', 'bg-teal-600', 'bg-teal-400', 'bg-teal-300'][i]]"
              :style="{ width: `${techVals[d.key]}%` }" :title="`${d.label} ${techVals[d.key]}`" />
          </div>
          <div class="mt-3 pt-3 border-t border-slate-200 text-xs text-slate-600 space-y-1">
            <div v-for="(d, i) in TECH_DIMS" :key="d.key" class="flex justify-between items-center">
              <span class="flex items-center gap-1.5">
                <span :class="['w-2 h-2 rounded-sm inline-block',
                               ['bg-teal-800', 'bg-teal-600', 'bg-teal-400', 'bg-teal-300'][i]]" />
                {{ d.label }}
              </span>
              <span :class="num">{{ techVals[d.key] }}</span>
            </div>
            <div class="flex justify-between font-bold text-slate-900 pt-1.5 border-t border-slate-200">
              <span>合計</span><span :class="num">{{ techScore }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 三、審查裁決 -->
    <section class="mt-7 rounded-md border border-slate-200 bg-slate-50/80 p-4 sm:p-5">
      <h2 class="text-lg font-bold text-rose-900 bg-rose-100/70 border-l-4 border-rose-600 px-3 py-2 rounded-r-sm -mx-1">
        三、審查裁決評分（拜訪前基準分）
      </h2>
      <p class="mt-2.5 px-1 text-sm text-slate-700 leading-relaxed">
        審查官不重新分析，而是把兩位 Agent 的結論加權成<strong>基礎分</strong>，
        再依交叉質詢找到的矛盾點增減。
        <strong class="text-rose-800">基礎分由後端計算後帶入，模型不得自行計算</strong>——
        這是分數可重現的關鍵。
      </p>

      <!-- 加權公式 -->
      <div class="mt-4 bg-white border border-slate-300 p-4 rounded-sm">
        <div class="flex items-center justify-center gap-3 flex-wrap text-center">
          <div class="px-3 py-2 border border-amber-300 bg-amber-50 rounded-sm">
            <div class="text-xs text-amber-800">財務</div>
            <div :class="`${num} text-xl font-bold text-amber-800`">{{ finScore }}</div>
          </div>
          <span :class="`${num} text-sm text-slate-500`">× 0.6</span>
          <span class="text-lg text-slate-400">＋</span>
          <div class="px-3 py-2 border border-teal-300 bg-teal-50 rounded-sm">
            <div class="text-xs text-teal-800">技術</div>
            <div :class="`${num} text-xl font-bold text-teal-800`">{{ techScore }}</div>
          </div>
          <span :class="`${num} text-sm text-slate-500`">× 0.4</span>
          <span class="text-lg text-slate-400">＝</span>
          <div class="px-4 py-2 border-2 border-rose-500 bg-rose-50 rounded-sm">
            <div class="text-xs text-rose-800">基礎分</div>
            <div :key="baseScore"
              :class="`${num} text-2xl font-bold text-rose-800 motion-safe:animate-[popIn_.3s_ease-out]`">
              {{ baseScore }}
            </div>
          </div>
        </div>
        <p class="mt-3 text-xs text-slate-500 text-center leading-relaxed">
          財務占六成是刻意的設計：授信最終要問的是「還不還得出來」，技術面是輔證。
          若任一方為「資料不足」，該面向會被排除，改由另一方單獨代表。
        </p>
      </div>

      <!-- 增減項與瀑布圖 -->
      <div class="mt-4 grid lg:grid-cols-5 gap-4 items-start">
        <div class="lg:col-span-2 bg-white border border-slate-300 p-4 rounded-sm">
          <p class="text-xs text-slate-500 mb-2.5">審查官的增減項（點選切換）</p>
          <div class="space-y-2">
            <button v-for="a in judgeAdj" :key="a.label" @click="a.on = !a.on"
              :aria-pressed="a.on"
              :class="[
                `w-full text-left px-3 py-2 border rounded-sm motion-safe:transition-all ${focusRing}`,
                'cursor-pointer hover:shadow-md hover:-translate-y-0.5',
                a.on ? (a.value >= 0
                          ? 'bg-emerald-50 border-emerald-400 hover:bg-emerald-100 hover:border-emerald-500'
                          : 'bg-rose-50 border-rose-400 hover:bg-rose-100 hover:border-rose-500')
                     : 'bg-white border-slate-300 opacity-55 hover:opacity-100 hover:border-slate-500 hover:bg-slate-50',
              ]">
              <div class="flex items-center justify-between gap-2">
                <span class="flex items-center gap-1.5 text-sm font-medium text-slate-800">
                  <span aria-hidden="true"
                    :class="['w-2.5 h-2.5 rounded-full border-2 shrink-0 motion-safe:transition-colors',
                             a.on ? (a.value >= 0 ? 'bg-emerald-600 border-emerald-600' : 'bg-rose-600 border-rose-600')
                                  : 'bg-white border-slate-400']" />
                  {{ a.label }}
                </span>
                <span :class="`${num} text-sm font-bold ${a.value >= 0 ? 'text-emerald-700' : 'text-rose-700'}`">
                  {{ a.value > 0 ? "+" : "" }}{{ a.value }}
                </span>
              </div>
              <p class="text-xs text-slate-500 mt-0.5 leading-relaxed">{{ a.why }}</p>
            </button>
          </div>
        </div>

        <div class="lg:col-span-3 bg-white border border-slate-300 p-4 rounded-sm">
          <p class="text-xs text-slate-500 mb-3">評分瀑布</p>
          <div class="space-y-1.5">
            <div v-for="(w, i) in judgeWf" :key="i" class="flex items-center gap-2">
              <span class="w-20 text-xs text-slate-600 text-right shrink-0 truncate">{{ w.label }}</span>
              <div class="flex-1 h-5 relative bg-slate-50 rounded-sm overflow-hidden">
                <div :class="['absolute h-full rounded-sm motion-safe:transition-all duration-500',
                              w.type === 'base' ? 'bg-slate-700' : w.type === 'plus' ? 'bg-emerald-600' : 'bg-rose-600']"
                  :style="{ left: `${w.left}%`, width: `${Math.max(w.width, 1)}%` }" />
              </div>
              <span :class="`${num} w-9 text-xs text-right shrink-0
                ${w.type === 'base' ? 'text-slate-700' : w.type === 'plus' ? 'text-emerald-700' : 'text-rose-700'}`">
                {{ w.type !== "base" && w.value > 0 ? "+" : "" }}{{ w.value }}
              </span>
            </div>
            <div class="flex items-center gap-2 pt-2 border-t border-slate-200">
              <span class="w-20 text-xs font-bold text-rose-800 text-right shrink-0">裁決分</span>
              <div class="flex-1 h-6 relative bg-slate-50 rounded-sm overflow-hidden">
                <div class="absolute left-0 h-full bg-rose-700 rounded-sm motion-safe:transition-all duration-500"
                  :style="{ width: `${judgeScore}%` }" />
              </div>
              <span :class="`${num} w-9 text-sm font-bold text-rose-800 text-right shrink-0`">{{ judgeScore }}</span>
            </div>
          </div>
          <p class="mt-3 text-xs text-slate-500 leading-relaxed">
            後端會驗算「基礎分 ＋ 各增減項 ＝ 裁決分」。
            若扣分總額超過基礎分導致負數，系統會<strong>等比縮減各扣分項</strong>，
            保留相對嚴重度但不讓分數變成負值。
          </p>
        </div>
      </div>
    </section>

    <!-- 四、拜訪前情資雷達 -->
    <section class="mt-7 rounded-md border border-slate-200 bg-slate-50/80 p-4 sm:p-5">
      <h2 class="text-lg font-bold text-sky-900 bg-sky-100/70 border-l-4 border-sky-700 px-3 py-2 rounded-r-sm -mx-1">
        四、拜訪前情資的五維雷達
      </h2>
      <p class="mt-2.5 px-1 text-sm text-slate-700 leading-relaxed">
        雷達圖是<strong>獨立的一組評分</strong>，不參與上述加權，
        用途是找出最弱的面向以決定面談時該問什麼。五維共用同一套分數帶定義。
      </p>

      <div class="mt-4 grid lg:grid-cols-2 gap-4 items-start">
        <div class="bg-white border border-slate-300 p-4 rounded-sm">
          <svg viewBox="0 0 260 250" class="w-full select-none" style="max-height: 250px"
            role="img" aria-label="五維雷達圖，點選頂點可查看該維度的評分規則">
            <polygon v-for="(r, i) in gridRings" :key="'g' + i"
              :points="RADAR.map((_, j) => pt(j, r).join(',')).join(' ')"
              fill="none" stroke="#e2e8f0" stroke-width="1" />
            <line v-for="(d, i) in RADAR" :key="'a' + i"
              :x1="CX" :y1="CY" :x2="pt(i, 100)[0]" :y2="pt(i, 100)[1]"
              :stroke="d.key === selDim ? '#0284c7' : d.key === hoverDim ? '#7dd3fc' : '#e2e8f0'"
              :stroke-width="d.key === selDim || d.key === hoverDim ? 1.8 : 1"
              style="transition: stroke .2s ease" />
            <polygon :points="poly('benchmark')" fill="#94a3b8" fill-opacity="0.12"
              stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4 4" />
            <polygon :points="poly('score')" fill="#0369a1" fill-opacity="0.2"
              stroke="#0c4a6e" stroke-width="2"
              class="motion-safe:animate-[popIn_.5s_cubic-bezier(.34,1.3,.5,1)]" />
            <g v-for="(d, i) in RADAR" :key="'p' + d.key">
              <circle v-if="d.key === selDim || d.key === hoverDim" :cx="pt(i, d.score)[0]" :cy="pt(i, d.score)[1]"
                r="11" fill="#0284c7" :fill-opacity="d.key === selDim ? 0.2 : 0.12"
                class="motion-safe:animate-[pulseDot_1.6s_ease-out_infinite]" />
              <circle :cx="pt(i, d.score)[0]" :cy="pt(i, d.score)[1]"
                :r="d.key === selDim ? 6.5 : d.key === hoverDim ? 6 : 4.5"
                :fill="d.key === selDim ? '#0c4a6e' : d.key === hoverDim ? '#0284c7' : '#0369a1'"
                stroke="#fff" stroke-width="2"
                style="cursor: pointer; transition: r .18s ease, fill .18s ease"
                @click="selDim = d.key" @mouseenter="hoverDim = d.key" @mouseleave="hoverDim = ''" />
            </g>
            <g v-for="(d, i) in RADAR" :key="'l' + d.key" style="cursor: pointer"
              @click="selDim = d.key" @mouseenter="hoverDim = d.key" @mouseleave="hoverDim = ''">
              <text :x="pt(i, 128)[0]" :y="pt(i, 128)[1]" text-anchor="middle"
                :fill="d.key === selDim ? '#0c4a6e' : d.key === hoverDim ? '#0284c7' : '#475569'" font-size="11"
                :font-weight="d.key === selDim || d.key === hoverDim ? 700 : 400"
                style="transition: fill .18s ease">
                {{ d.label }} {{ d.score }}
                <tspan :fill="d.score >= d.benchmark ? '#059669' : '#e11d48'" font-size="9">
                  {{ d.score >= d.benchmark ? "▲" : "▼" }}
                </tspan>
              </text>
            </g>
          </svg>
          <p class="text-xs text-slate-500 text-center">
            實線為本公司、虛線為同業基準；點選頂點或名稱可查看評分規則
          </p>
        </div>

        <div class="space-y-3">
          <div :key="cur.key" class="bg-white border border-slate-300 border-t-4 border-t-sky-700 p-4 rounded-sm
                                      motion-safe:animate-[fadeUp_.3s_ease-out]">
            <div class="flex items-baseline justify-between gap-2">
              <h3 class="text-base font-bold text-slate-900">{{ cur.label }}</h3>
              <div>
                <span :class="`${num} text-2xl font-bold text-sky-900`">{{ cur.score }}</span>
                <span class="text-xs text-slate-500"> / 同業 {{ cur.benchmark }}</span>
              </div>
            </div>
            <p class="mt-2 text-sm text-slate-700 leading-relaxed">{{ cur.rule }}</p>
          </div>

          <div class="bg-white border border-slate-300 p-4 rounded-sm">
            <h4 class="text-xs font-bold text-slate-500 mb-2">分數帶定義（五維共用）</h4>
            <div class="space-y-1.5">
              <div v-for="(b, i) in BANDS" :key="b.range"
                :class="['flex items-center gap-2 px-2 py-1 border rounded-sm text-xs', b.cls,
                         'motion-safe:animate-[slideIn_.3s_ease-out]']"
                :style="{ animationDelay: `${i * 50}ms` }">
                <span :class="`${num} font-bold w-16 shrink-0`">{{ b.range }}</span>
                <span>{{ b.label }}</span>
              </div>
            </div>
            <p class="mt-2.5 text-xs text-slate-500 leading-relaxed">
              系統會針對<strong>分數最低的兩個維度</strong>產出防禦提問單，
              並要求每題以具體數據開頭。
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- 五、拜訪後覆評 -->
    <section class="mt-7 rounded-md border border-slate-200 bg-slate-50/80 p-4 sm:p-5">
      <h2 class="text-lg font-bold text-violet-900 bg-violet-100/70 border-l-4 border-violet-600 px-3 py-2 rounded-r-sm -mx-1">
        五、拜訪後覆評（最終評分）
      </h2>
      <p class="mt-2.5 px-1 text-sm text-slate-700 leading-relaxed">
        覆評<strong>不是重新打分</strong>，而是以審查裁決分為起點，
        依面談結果加減。因此瀑布圖的第一筆一定等於裁決分——拜訪前後是同一條線。
      </p>

      <div class="mt-4 grid lg:grid-cols-5 gap-4 items-start">
        <div class="lg:col-span-2 bg-white border border-slate-300 p-4 rounded-sm">
          <p class="text-xs text-slate-500 mb-2.5">面談結果的增減項（點選切換）</p>
          <div class="space-y-2">
            <button v-for="a in postAdj" :key="a.label" @click="a.on = !a.on"
              :aria-pressed="a.on"
              :class="[
                `w-full text-left px-3 py-2 border rounded-sm motion-safe:transition-all ${focusRing}`,
                'cursor-pointer hover:shadow-md hover:-translate-y-0.5',
                a.on ? (a.value >= 0
                          ? 'bg-emerald-50 border-emerald-400 hover:bg-emerald-100 hover:border-emerald-500'
                          : 'bg-rose-50 border-rose-400 hover:bg-rose-100 hover:border-rose-500')
                     : 'bg-white border-slate-300 opacity-55 hover:opacity-100 hover:border-slate-500 hover:bg-slate-50',
              ]">
              <div class="flex items-center justify-between gap-2">
                <span class="flex items-center gap-1.5 text-sm font-medium text-slate-800">
                  <span aria-hidden="true"
                    :class="['w-2.5 h-2.5 rounded-full border-2 shrink-0 motion-safe:transition-colors',
                             a.on ? (a.value >= 0 ? 'bg-emerald-600 border-emerald-600' : 'bg-rose-600 border-rose-600')
                                  : 'bg-white border-slate-400']" />
                  {{ a.label }}
                </span>
                <span :class="`${num} text-sm font-bold ${a.value >= 0 ? 'text-emerald-700' : 'text-rose-700'}`">
                  {{ a.value > 0 ? "+" : "" }}{{ a.value }}
                </span>
              </div>
              <p class="text-xs text-slate-500 mt-0.5 leading-relaxed">{{ a.why }}</p>
            </button>
          </div>
          <p class="mt-3 text-xs text-slate-500 leading-relaxed">
            評分方向：已化解風險加分、僅部分化解小扣或不動、未化解與新發現風險扣分。
          </p>
        </div>

        <div class="lg:col-span-3 bg-white border border-slate-300 p-4 rounded-sm">
          <p class="text-xs text-slate-500 mb-3">覆評瀑布</p>
          <div class="space-y-1.5">
            <div v-for="(w, i) in postWf" :key="i" class="flex items-center gap-2">
              <span class="w-20 text-xs text-slate-600 text-right shrink-0 truncate">
                {{ i === 0 ? "拜訪前基準" : w.label }}
              </span>
              <div class="flex-1 h-5 relative bg-slate-50 rounded-sm overflow-hidden">
                <div :class="['absolute h-full rounded-sm motion-safe:transition-all duration-500',
                              w.type === 'base' ? 'bg-rose-700' : w.type === 'plus' ? 'bg-emerald-600' : 'bg-rose-600']"
                  :style="{ left: `${w.left}%`, width: `${Math.max(w.width, 1)}%` }" />
              </div>
              <span :class="`${num} w-9 text-xs text-right shrink-0
                ${w.type === 'base' ? 'text-rose-800' : w.type === 'plus' ? 'text-emerald-700' : 'text-rose-700'}`">
                {{ w.type !== "base" && w.value > 0 ? "+" : "" }}{{ w.value }}
              </span>
            </div>
            <div class="flex items-center gap-2 pt-2 border-t border-slate-200">
              <span class="w-20 text-xs font-bold text-violet-800 text-right shrink-0">最終評分</span>
              <div class="flex-1 h-6 relative bg-slate-50 rounded-sm overflow-hidden">
                <div class="absolute left-0 h-full bg-violet-700 rounded-sm motion-safe:transition-all duration-500"
                  :style="{ width: `${postScore}%` }" />
              </div>
              <span :class="`${num} w-9 text-sm font-bold text-violet-800 text-right shrink-0`">{{ postScore }}</span>
            </div>
          </div>
          <div class="mt-3 pt-3 border-t border-slate-200 flex items-center justify-between gap-3 flex-wrap">
            <span class="text-xs text-slate-500">風險等級</span>
            <span :class="`text-sm font-bold ${levelCls(postScore)}`">
              {{ level(postScore) }}
              <span class="text-xs text-slate-400 font-normal">（≥67 低風險、≥45 中等、其餘偏高）</span>
            </span>
          </div>
        </div>
      </div>

      <!-- 一致性提醒 -->
      <div class="mt-4 border border-sky-300 border-l-4 border-l-sky-600 bg-sky-50 p-3.5 rounded-sm">
        <h3 class="text-sm font-bold text-sky-900">上游變動時會發生什麼</h3>
        <p class="mt-1 text-sm text-slate-800 leading-relaxed">
          財務或技術 Agent 一旦重跑，基礎分就會改變，審查裁決會<strong>自動重新計算</strong>；
          若當時已算出拜訪後評分，系統會顯示「基準分已更新」提示，建議重新覆評。
          這確保衍生的分數永遠不會與素材脫節。
        </p>
      </div>
    </section>

    <!-- 六、報告封面分數 -->
    <section class="mt-7 rounded-md border border-slate-200 bg-slate-50/80 p-4 sm:p-5">
      <h2 class="text-lg font-bold text-slate-900 bg-slate-200/70 border-l-4 border-slate-600 px-3 py-2 rounded-r-sm -mx-1">
        六、報告封面顯示哪個分數
      </h2>
      <p class="mt-2.5 px-1 text-sm text-slate-700 leading-relaxed">
        一份案件可能只完成到某個階段。報告封面會依<strong>完成度由高到低</strong>取第一個可用的分數，
        並在標籤上標明來源，不會讓人誤以為是最終結論。
      </p>

      <div class="mt-4 bg-white border border-slate-300 p-4 rounded-sm">
        <div class="flex flex-wrap gap-2 mb-4">
          <button v-for="c in COVER" :key="c.n" @click="coverStep = c.n"
            :class="[
              `px-3 py-1.5 text-xs border rounded-sm motion-safe:transition-all ${focusRing}`,
              'cursor-pointer hover:-translate-y-0.5 hover:shadow-md',
              coverStep === c.n ? c.active
                : 'bg-white border-slate-300 text-slate-600 hover:bg-sky-50 hover:border-sky-400 hover:text-sky-800',
            ]">
            {{ c.n }}. {{ c.label }}
          </button>
        </div>

        <div class="grid sm:grid-cols-2 gap-4 items-center">
          <!-- 模擬報告封面 -->
          <div class="border border-slate-300 rounded-sm overflow-hidden">
            <div class="h-1.5 bg-sky-900" />
            <div class="p-3 flex items-stretch gap-3">
              <div class="flex-1 bg-slate-100 p-2.5 rounded-sm">
                <div class="text-sm font-bold text-slate-900">寶齡富錦生技</div>
                <div :class="`text-xs text-slate-500 mt-1 ${num}`">證券代號 1760</div>
              </div>
              <div class="w-24 bg-sky-900 text-white p-2 rounded-sm text-center flex flex-col justify-center">
                <div class="text-xs leading-tight">
                  {{ COVER.find((c) => c.n === coverStep)?.label }}
                </div>
                <div :key="coverStep" :class="`${num} text-2xl font-bold mt-0.5 motion-safe:animate-[popIn_.3s_ease-out]`">
                  {{ [postScore, judgeScore, baseScore, finScore, "—"][coverStep - 1] }}
                </div>
              </div>
            </div>
          </div>

          <div>
            <ol class="space-y-1.5">
              <li v-for="c in COVER" :key="c.n"
                :class="['flex items-start gap-2 text-xs px-2 py-1.5 border rounded-sm motion-safe:transition-all',
                         coverStep === c.n ? 'border-sky-400 bg-sky-50' : 'border-transparent']">
                <span :class="`${num} font-bold w-4 shrink-0`"
                  :style="{ color: coverStep === c.n ? '#0c4a6e' : '#94a3b8' }">{{ c.n }}</span>
                <span>
                  <strong class="text-slate-800">{{ c.label }}</strong>
                  <span class="block text-slate-500 mt-0.5">{{ c.cond }}</span>
                </span>
              </li>
            </ol>
          </div>
        </div>
      </div>
    </section>

    <!-- 完整範例 -->
    <section class="mt-7 rounded-md border border-slate-200 bg-slate-50/80 p-4 sm:p-5">
      <h2 class="text-lg font-bold text-emerald-900 bg-emerald-100/70 border-l-4 border-emerald-600 px-3 py-2 rounded-r-sm -mx-1">
        七、完整範例：一次看懂四個分數的關係
      </h2>
      <div class="mt-4 bg-white border border-slate-300 p-4 rounded-sm">
        <p class="text-sm text-slate-700 leading-relaxed mb-4">
          以目前的試算值為例，同一家公司的四個分數是這樣一路推導出來的：
        </p>
        <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div v-for="(s, i) in SUMMARY" :key="i"
            :class="['relative bg-white border border-slate-300 border-l-4 p-3 rounded-sm', s.edge]">
            <div class="text-xs text-slate-500">{{ s.t }}</div>
            <div :key="s.v" :class="[num, 'text-2xl font-bold motion-safe:animate-[popIn_.3s_ease-out]', s.text]">
              {{ s.v }}<span class="text-xs text-slate-400 font-normal"> 分</span>
            </div>
            <div class="text-xs text-slate-600 mt-1">{{ s.d }}</div>
          </div>
        </div>
        <div class="mt-4 pt-3 border-t border-slate-200 text-xs text-slate-600 leading-relaxed space-y-1">
          <p>· 財務與技術<strong>各自獨立</strong>，互不影響。</p>
          <p>· 審查裁決<strong>吃前兩者</strong>：改動任一方，基礎分立刻跟著變。</p>
          <p>· 拜訪後覆評<strong>吃裁決分</strong>：它的起點永遠是裁決分，不會另起爐灶。</p>
          <p>· 雷達圖<strong>不參與</strong>這條線，用途是決定面談要問什麼。</p>
        </div>
      </div>
    </section>

    <p class="mt-6 text-xs text-slate-500 leading-relaxed">
      本頁的計算方式與系統實際規則一致（財務扣分表、技術四構面配分、加權比例、
      分數上下限與風險等級切點）。AI 負責判斷條件是否成立與撰寫說明，
      分數的合成一律由後端程式計算，因此可完整重現。
    </p>
  </main>
</template>

<style scoped>
/* 滑桿:滑鼠移入時把拉柄放大並加深,讓「這裡可以拖」更明顯 */
.slider-hover::-webkit-slider-thumb {
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.slider-hover:hover::-webkit-slider-thumb {
  transform: scale(1.25);
  box-shadow: 0 0 0 4px rgb(13 148 136 / 0.18);
}
.slider-hover::-moz-range-thumb {
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.slider-hover:hover::-moz-range-thumb {
  transform: scale(1.25);
  box-shadow: 0 0 0 4px rgb(13 148 136 / 0.18);
}

/* 尊重使用者的減少動態偏好 */
@media (prefers-reduced-motion: reduce) {
  .slider-hover:hover::-webkit-slider-thumb,
  .slider-hover:hover::-moz-range-thumb { transform: none; }
}
</style>