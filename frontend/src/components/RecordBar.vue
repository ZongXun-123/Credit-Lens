<script setup>
// 共用元件:紀錄列(RecordBar)
// 顯示目前結果的來源(既有紀錄或最新產製)、提供「重新產製」與「歷次紀錄」面板。
// 歷次面板可載入任一筆檢視,並可「設為主要」(釘選):之後預設載入與 Demo 重播皆固定用該筆。
import { ref } from "vue";
import { focusRing, num } from "../constants.js";
import { reviewApi } from "../api.js";

const props = defineProps({
  kind: { type: String, required: true },       // finance / tech / judge / pre_brief / market_read
  cid: { type: String, required: true },        // 證券代號
  current: { type: Object, default: null },     // { recId, cachedAt, fromCache, pinned }
  busy: { type: Boolean, default: false },
  hideRefresh: { type: Boolean, default: false },   // 該頁已有專屬的重新執行按鈕時隱藏,避免功能重複
});
const emit = defineEmits(["refresh", "load"]);

const open = ref(false);
const items = ref([]);
const listBusy = ref(false);
const actBusy = ref(0);

async function toggle() {
  open.value = !open.value;
  if (open.value) await fetchList();
}
async function fetchList() {
  listBusy.value = true;
  try {
    const r = await reviewApi("/api/cache/list", { kind: props.kind, company_id: props.cid, limit: 20 },
      { items: [] }, 200);
    items.value = r.items || [];
  } catch (e) { items.value = []; }
  listBusy.value = false;
}
async function loadRec(it) {
  actBusy.value = it.id;
  try {
    const r = await reviewApi("/api/cache/get", { id: it.id }, null, 200);
    emit("load", { ...r.payload, _rec_id: r.id, _cached_at: r.created_at, _from_cache: true, _pinned: r.pinned });
  } catch (e) { alert(`載入失敗:${e.message}`); }
  actBusy.value = 0;
}
async function pinRec(it) {
  actBusy.value = it.id;
  try {
    await reviewApi("/api/cache/pin", { kind: props.kind, company_id: props.cid, id: it.id }, { pinned: true }, 200);
    await fetchList();
    await loadRec(items.value.find((x) => x.id === it.id) || it);
  } catch (e) { alert(`釘選失敗:${e.message}`); }
  actBusy.value = 0;
}
</script>

<template>
  <div class="border border-slate-300 bg-slate-50">
    <div class="px-3 py-2 flex items-center justify-between gap-3 flex-wrap">
      <span class="text-xs text-slate-600 flex items-center gap-1.5 flex-wrap">
        <template v-if="current && current.recId">
          <span aria-hidden="true" :class="['w-2 h-2 rounded-full shrink-0', current.fromCache ? 'bg-sky-600' : 'bg-emerald-600']" />
          <span class="font-bold" :class="current.fromCache ? 'text-sky-900' : 'text-emerald-800'">
            {{ current.fromCache ? "既有紀錄" : "最新產製" }}
          </span>
          <span :class="num">#{{ current.recId }} · {{ current.cachedAt }}</span>
          <span v-if="current.pinned" class="px-1.5 py-0.5 border border-amber-400 bg-amber-50 text-amber-800 rounded-sm font-bold">主要</span>
        </template>
        <template v-else>尚無紀錄,產製後會自動存檔供日後直接載入。</template>
      </span>
      <span class="flex items-center gap-2 shrink-0">
        <button v-if="!hideRefresh" @click="emit('refresh')" :disabled="busy"
          :class="`px-2.5 h-8 text-xs font-bold text-sky-900 bg-white border border-slate-400 hover:bg-sky-50 disabled:opacity-50 rounded-sm motion-safe:transition-colors ${focusRing}`">
          {{ busy ? "產製中…" : "重新產製" }}
        </button>
        <button @click="toggle"
          :class="`px-2.5 h-8 text-xs text-slate-700 bg-white border border-slate-400 hover:bg-slate-100 rounded-sm motion-safe:transition-colors ${focusRing}`">
          歷次紀錄 {{ open ? "▲" : "▼" }}
        </button>
      </span>
    </div>

    <div v-if="open" class="border-t border-slate-300 bg-white">
      <p v-if="listBusy" class="px-3 py-3 text-xs text-slate-500">載入紀錄中…</p>
      <p v-else-if="items.length === 0" class="px-3 py-3 text-xs text-slate-500">此公司此功能尚無存檔紀錄。</p>
      <ul v-else>
        <li v-for="it in items" :key="it.id"
          class="px-3 py-1.5 border-b border-slate-200 last:border-0 flex items-center gap-3 flex-wrap text-xs hover:bg-sky-50 motion-safe:transition-colors">
          <span :class="`${num} text-slate-500 w-10 shrink-0`">#{{ it.id }}</span>
          <span :class="`${num} text-slate-600 w-32 shrink-0`">{{ it.created_at }}</span>
          <span class="w-14 shrink-0 text-right">
            <span v-if="it.score !== null && it.score !== undefined" :class="`${num} font-bold text-sky-900`">{{ it.score }} 分</span>
            <span v-else class="text-slate-400">—</span>
          </span>
          <span class="flex-1" />
          <span v-if="it.pinned" class="px-1.5 py-0.5 border border-amber-400 bg-amber-50 text-amber-800 rounded-sm font-bold shrink-0">主要</span>
          <button @click="loadRec(it)" :disabled="actBusy === it.id"
            :class="`px-2 h-7 text-xs text-sky-900 bg-white border border-slate-300 hover:bg-sky-50 disabled:opacity-50 rounded-sm ${focusRing}`">
            載入檢視
          </button>
          <button v-if="!it.pinned" @click="pinRec(it)" :disabled="actBusy === it.id"
            :class="`px-2 h-7 text-xs text-amber-800 bg-white border border-amber-300 hover:bg-amber-50 disabled:opacity-50 rounded-sm ${focusRing}`">
            設為主要
          </button>
        </li>
      </ul>
      <p class="px-3 py-1.5 text-xs text-slate-400 border-t border-slate-200">
        「設為主要」後,此功能預設載入與 Demo 重播皆固定使用該筆。
      </p>
    </div>
  </div>
</template>