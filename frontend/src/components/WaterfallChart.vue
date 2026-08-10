<script setup>
// 評分瀑布圖(規格書 6.5 / 9.4):base 從 0 起畫,增減項自累積位置接續
// 顏色由 type 決定(base=灰、plus=綠、minus=紅),禁止以數值正負推斷
import { computed } from "vue";
import { num } from "../constants.js";

const props = defineProps({
  items: { type: Array, required: true },      // WaterfallItem[]
  finalScore: { type: Number, required: true }, // 對應契約 final_score
});

const bars = computed(() => {
  let cursor = 0;
  return props.items.map((it) => {
    const start = it.type === "base" ? 0 : cursor;
    const left = it.value >= 0 ? start : start + it.value;
    const width = Math.abs(it.value);
    cursor = start + it.value;
    return {
      ...it, left, width,
      bar: it.type === "base" ? "bg-slate-400" : it.type === "plus" ? "bg-emerald-600" : "bg-rose-600",
      tc: it.type === "base" ? "text-slate-600" : it.type === "plus" ? "text-emerald-700" : "text-rose-700",
      display: it.type === "base" ? String(it.value) : (it.value > 0 ? "+" : "") + it.value,
    };
  });
});
</script>

<template>
  <div class="space-y-1.5">
    <div v-for="(it, i) in bars" :key="i" class="flex items-center gap-3 text-sm">
      <div class="w-28 text-slate-700 text-right shrink-0 text-xs">{{ it.label }}</div>
      <div class="flex-1 h-4 bg-slate-100 border border-slate-200 relative overflow-hidden">
        <div :class="`absolute h-full ${it.bar} motion-safe:transition-[left,width] motion-safe:duration-700`"
          :style="{ left: `${it.left}%`, width: `${it.width}%` }" />
      </div>
      <div :class="`w-10 ${num} text-sm text-right ${it.tc}`">{{ it.display }}</div>
    </div>
    <div class="flex items-center justify-between pt-2 mt-1 border-t-2 border-slate-300">
      <span class="text-sm font-bold text-slate-900">綜合評分</span>
      <span :class="`${num} font-bold text-2xl text-sky-900`">{{ finalScore }}<span class="text-xs text-slate-500 font-normal"> 分</span></span>
    </div>
  </div>
</template>
