<script setup>
// 回到頂端:捲動超過一個畫面高度才浮現
import { ref, onMounted, onUnmounted } from "vue";
import { focusRing } from "../constants.js";
const show = ref(false);
const onScroll = () => { show.value = window.scrollY > 420; };
onMounted(() => window.addEventListener("scroll", onScroll, { passive: true }));
onUnmounted(() => window.removeEventListener("scroll", onScroll));
const toTop = () => window.scrollTo({ top: 0, behavior: "smooth" });
</script>

<template>
  <Transition enter-active-class="motion-safe:animate-[popIn_.25s_ease-out]" leave-active-class="opacity-0 transition-opacity duration-200">
    <button v-if="show" @click="toTop" aria-label="回到頁面頂端"
      :class="`fixed bottom-6 right-5 z-50 w-11 h-11 grid place-items-center rounded-sm bg-sky-900 text-white
               hover:bg-sky-800 shadow-lg motion-safe:animate-[pulseRing_2.4s_ease-out_infinite] ${focusRing}`">
      <svg viewBox="0 0 24 24" class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true">
        <path d="M12 19V5m-6 6 6-6 6 6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      <span class="sr-only">TOP</span>
    </button>
  </Transition>
</template>
