<script setup>
// 共用載入動畫:AI 文件掃描 — 掃描線在文件上來回移動,底下輪播處理階段文字
import { ref, onMounted, onUnmounted } from "vue";
const props = defineProps({
  title: { type: String, default: "AI 分析中" },
  steps: { type: Array, default: () => ["連線知識庫", "檢索相關資料", "交叉比對來源", "整理分析結果"] },
  compact: { type: Boolean, default: false },
});
const idx = ref(0);
let timer = null;
onMounted(() => { timer = setInterval(() => { idx.value = (idx.value + 1) % props.steps.length; }, 1600); });
onUnmounted(() => clearInterval(timer));
</script>

<template>
  <div :class="['bg-white border border-slate-300 flex items-center gap-4', compact ? 'p-3' : 'p-5']" role="status">
    <!-- 文件掃描動畫 -->
    <div aria-hidden="true" class="relative shrink-0 border-2 border-sky-900 rounded-sm bg-sky-50/50 overflow-hidden"
      :class="compact ? 'w-10 h-12' : 'w-14 h-[4.2rem]'">
      <div class="absolute inset-x-1.5 top-2 space-y-1.5">
        <div class="h-1 rounded shimmer-bar" style="width: 85%" />
        <div class="h-1 rounded shimmer-bar" style="width: 100%" />
        <div class="h-1 rounded shimmer-bar" style="width: 70%" />
        <div v-if="!compact" class="h-1 rounded shimmer-bar" style="width: 92%" />
        <div v-if="!compact" class="h-1 rounded shimmer-bar" style="width: 60%" />
      </div>
      <div class="absolute inset-x-0 h-0.5 bg-sky-600 motion-safe:animate-[scanline_2.2s_ease-in-out_infinite]"
        style="box-shadow: 0 0 6px 1px rgba(2,132,199,.55)" />
    </div>
    <div class="min-w-0">
      <div :class="['font-bold text-sky-950 flex items-center gap-1.5', compact ? 'text-sm' : 'text-base']">
        {{ title }}
        <span aria-hidden="true" class="inline-flex gap-0.5 ml-0.5">
          <i v-for="n in 3" :key="n" class="w-1 h-1 rounded-full bg-sky-800 motion-safe:animate-[dotBounce_1.2s_infinite]"
            :style="{ animationDelay: `${(n - 1) * 0.18}s` }" />
        </span>
      </div>
      <p :key="idx" class="text-xs text-slate-500 mt-1 motion-safe:animate-[fadeUp_.4s_ease-out]">
        {{ steps[idx] }}…
      </p>
    </div>
  </div>
</template>
