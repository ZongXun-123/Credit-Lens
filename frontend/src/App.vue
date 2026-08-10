<script setup>
// ============================================================
// 智貸先鋒 企業授信情資服務網 — App 骨架
// 職責:上方工具列 / Header / Footer / 字級調整 / 頁面切換
// 頁面內容見 pages/,四個頁籤元件見 components/
// ============================================================
import { ref, onMounted, onUnmounted, watchEffect, computed } from "vue";
import { focusRing } from "./constants.js";
import DashboardPage from "./pages/DashboardPage.vue";
import CasePage from "./pages/CasePage.vue";
import IntelPage from "./pages/IntelPage.vue";
import ReportPage from "./pages/ReportPage.vue";
import MarketRankPage from "./pages/MarketRankPage.vue";
import AskPage from "./pages/AskPage.vue";
import SitemapPage from "./pages/SitemapPage.vue";
import BackToTop from "./components/BackToTop.vue";
import PromptPage from "./pages/PromptPage.vue";
import ScoringPage from "./pages/ScoringPage.vue";

const page = ref("dashboard");
const current = ref(null);
const nav = ref("案件總覽");
const intelQuery = ref("");   // 由案件詳情帶入的統編/公司名
const fontScale = ref("m");
// 字級調整:Tailwind 的 text-sm / text-lg 等以 rem 為單位,rem 參照的是 <html> 根字級。
// 若只套在內層容器的 font-size,僅未指定字級的元素會變化(先前只有部分地方有反應的原因)。
// 因此直接改 documentElement 的 font-size,全站字級一併等比縮放。
const FONT_PX = { s: "14.5px", m: "16px", l: "18.5px" };
watchEffect(() => {
  if (typeof document !== "undefined") {
    document.documentElement.style.fontSize = FONT_PX[fontScale.value] || "16px";
  }
});
// v1.6:header 改為固定高度,scrolled 僅用於陰影(不影響版面高度,不會造成抖動)
const scrolled = ref(false);
const onWinScroll = () => { scrolled.value = window.scrollY > 40; };
onMounted(() => window.addEventListener("scroll", onWinScroll, { passive: true }));
onUnmounted(() => window.removeEventListener("scroll", onWinScroll));

const fontSizes = [{ k: "s", label: "小" }, { k: "m", label: "中" }, { k: "l", label: "大" }];
const navItems = ["案件總覽", "情資查詢", "市場訊號", "知識問答", "報告中心"];
// 上方工具列的說明類連結。與頁尾共用 footerNav(),要增減項目改這裡即可。
const TOOLBAR_LINKS = [ "網站導覽","Prompt 設計", "授信評分說明"];
const NAV_PAGE = { "案件總覽": "dashboard", "情資查詢": "intel", "市場訊號": "market", "知識問答": "ask", "報告中心": "reports" };

function goHome() { page.value = "dashboard"; current.value = null; nav.value = "案件總覽"; }
function onNav(t) {
  if (!NAV_PAGE[t]) return; // 關於平臺:尚未實作,維持現頁
  nav.value = t; current.value = null; intelQuery.value = ""; page.value = NAV_PAGE[t];
}
function openCase(c) { current.value = c; page.value = "case"; nav.value = "案件總覽"; }
// 案件詳情 →「查詢公開情資」:帶統編(無統編時帶公司名)切到情資查詢頁
function openIntel(q) { intelQuery.value = String(q || ""); page.value = "intel"; nav.value = "情資查詢"; }
// 說明類頁面的跳轉。工具列與頁尾共用,兩處的名稱都在此對照。
const INFO_PAGE = {
  "網站導覽": "sitemap",
  "Prompt Engineering": "prompt", "Prompt 設計": "prompt",
  "授信評分說明": "scoring", "評分說明": "scoring",
};
function footerNav(t) {
  const target = INFO_PAGE[t];
  if (!target) return;
  page.value = target;
  nav.value = "";          // 清掉主導覽的選取狀態
}
</script>

<template>
  <div class="min-h-screen bg-slate-50 text-slate-800 flex flex-col"
    :style="{ fontFamily: `'Noto Sans TC','PingFang TC','Microsoft JhengHei',sans-serif`, colorScheme: 'light' }">

    <a href="#main" class="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-2 focus:left-2 focus:px-3 focus:py-2 focus:bg-sky-900 focus:text-white focus:rounded-sm">
      跳至主要內容
    </a>

    <!-- v1.6:工具列與主標頭整組固定於頂端,高度固定不隨捲動變化,僅陰影加深 -->
    <div :class="['sticky top-0 z-50 motion-safe:transition-shadow duration-200', scrolled ? 'shadow-lg shadow-slate-900/10' : '']">
    <!-- 上方工具列(深色細帶):政府網站標配 -->
    <div class="bg-sky-950 text-sky-100 text-xs">
      <div class="max-w-5xl mx-auto px-4 h-8 flex items-center justify-between">
        <span>精誠 SEI 競賽展示系統 · 非正式金融服務</span>
        <div class="flex items-center gap-3">
          <!-- 說明類頁面:與頁尾共用 footerNav(),新增頁面只需改一處 -->
          <template v-for="(t, i) in TOOLBAR_LINKS" :key="t">
            <button @click="footerNav(t)"
              :class="`hover:underline underline-offset-2 rounded-sm px-0.5 ${focusRing}`">{{ t }}</button>
            <span v-if="i < TOOLBAR_LINKS.length - 1" aria-hidden="true" class="text-sky-800">|</span>
          </template>
          <span aria-hidden="true" class="text-sky-800">|</span>
          <span class="flex items-center gap-1" role="group" aria-label="字級調整">
            字級
            <button v-for="s in fontSizes" :key="s.k" @click="fontScale = s.k" :aria-pressed="fontScale === s.k"
              :class="[`w-6 h-6 rounded-sm ${focusRing}`, fontScale === s.k ? 'bg-sky-100 text-sky-950 font-bold' : 'hover:bg-sky-800']">
              {{ s.label }}
            </button>
          </span>
        </div>
      </div>
    </div>

    <!-- Header(固定高度,不隨捲動縮放) -->
    <header class="bg-white border-b-4 border-sky-900">
      <div class="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between gap-6 flex-wrap">
        <button @click="onNav('案件總覽')" :class="`flex items-center gap-3 rounded-sm ${focusRing}`">
          <span aria-hidden="true" class="grid place-items-center rounded-sm bg-sky-900 text-white w-11 h-11">
            <svg viewBox="0 0 24 24" class="w-6 h-6" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /><path d="M8 11h6M11 8v6" />
            </svg>
          </span>
          <span class="text-left">
            <span class="block font-bold text-sky-950 leading-tight text-xl">智貸先鋒 企業授信情資服務網</span>
            <span class="block text-xs text-slate-500 leading-tight tracking-wide">Credit-Lens Corporate Credit Intelligence</span>
          </span>
        </button>
        <nav aria-label="主選單">
          <ul class="flex items-center gap-1">
            <li v-for="t in navItems" :key="t">
              <button @click="onNav(t)" :aria-current="nav === t ? 'page' : undefined"
                :class="[`px-3 py-2 text-sm font-medium border-b-2 motion-safe:transition-colors ${focusRing}`,
                  nav === t ? 'border-sky-800 text-sky-900 font-bold' : 'border-transparent text-slate-600 hover:text-sky-900 hover:border-sky-300']">
                {{ t }}
              </button>
            </li>
          </ul>
        </nav>
      </div>
    </header>
    </div>

    <div class="flex-1">
      <DashboardPage v-if="page === 'dashboard'" @open-case="openCase" />
      <IntelPage v-else-if="page === 'intel'" :initial-query="intelQuery" @open-case="openCase" />
      <MarketRankPage v-else-if="page === 'market'" @open-case="openCase" />
      <AskPage v-else-if="page === 'ask'" />
      <ReportPage v-else-if="page === 'reports'" @open-case="openCase" />
      <PromptPage v-else-if="page === 'prompt'" />
      <ScoringPage v-else-if="page === 'scoring'" />
      <SitemapPage v-else-if="page === 'sitemap'" @go="onNav" @open-intel="openIntel" />
      <CasePage v-else :c="current" @go-home="goHome" @open-intel="openIntel" />
    </div>

    <BackToTop />

    <!-- Footer -->
    <footer class="bg-slate-800 text-slate-300 mt-12">
      <div class="max-w-5xl mx-auto px-4 py-8 grid gap-6 sm:grid-cols-3 text-sm">
        <div>
          <div class="text-white font-bold mb-2">智貸先鋒 企業授信情資服務網</div>
          <p class="text-xs leading-relaxed text-slate-400">
            主辦單位:精誠 SEI 競賽第 1 組<br />
            技術架構:Multi-Agent · GraphRAG · LLM-as-a-Judge<br />
            本站為競賽展示系統,所有企業資料皆為模擬情境。
          </p>
        </div>
        <div>
          <div class="text-white font-bold mb-2">介接資料來源</div>
          <ul class="text-xs space-y-1 text-slate-400">
            <li v-for="t in ['TWSE 公開資訊觀測站', '經濟部商工登記(data.gov.tw)']" :key="t">
              <a href="#" @click.prevent :class="`hover:text-white hover:underline underline-offset-2 rounded-sm ${focusRing}`">{{ t }}</a>
            </li>
          </ul>
        </div>
        <div>
          <div class="text-white font-bold mb-2">網站資訊</div>
          <ul class="text-xs space-y-1 text-slate-400">
            <li v-for="t in ['網站導覽','Prompt Engineering', '授信評分說明' ]" :key="t" @click="footerNav(t)">
              <a href="#" @click.prevent :class="`hover:text-white hover:underline underline-offset-2 rounded-sm ${focusRing}`">{{ t }}</a>
            </li>
          </ul>
        </div>
      </div>
      <div class="border-t border-slate-700">
        <div class="max-w-5xl mx-auto px-4 py-3 text-xs text-slate-500 flex justify-between flex-wrap gap-2">
          <span>建議使用 Chrome、Edge、Firefox、Safari 瀏覽器</span>
          <span>© 2026 Credit-Lens Team. All Rights Reserved.</span>
        </div>
      </div>
    </footer>
  </div>
</template>

<style>
/* 全域(不加 scoped):fadeUp 供各子元件的 motion-safe:animate-[fadeUp_...] 使用 */
@keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes growUp { from { height: 0 !important; opacity: .3; } }
@keyframes shake { 0%,100% { transform: translateX(0); } 25% { transform: translateX(-4px); } 75% { transform: translateX(4px); } }
@keyframes slideIn { from { opacity: 0; transform: translateX(-8px); } to { opacity: 1; transform: translateX(0); } }
/* 卡片浮現預設不可見,避免動畫前閃現 */
[class*="animate-[fadeUp"] { animation-fill-mode: backwards; }
[class*="animate-[slideIn"] { animation-fill-mode: backwards; }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
button { touch-action: manipulation; }
</style>