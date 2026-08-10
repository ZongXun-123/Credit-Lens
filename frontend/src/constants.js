// ============================================================
// 全站共用常數(設計語言與規格書 7.1/7.2 詞彙)
// ============================================================
export const focusRing = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-700 focus-visible:ring-offset-1";
export const num = "tabular-nums";

// 三個 Agent 的識別(政府風:白卡 + 左側色條,不用大面積色塊)
// 規格書 7.2:finance #D97706 amber / tech #0891B2 cyan / judge #E11D48 rose
export const AGENT = {
  finance: { name: "財務分析", edge: "border-l-amber-500", text: "text-amber-800", chip: "bg-amber-50 text-amber-800 border-amber-300" },
  tech: { name: "技術情報", edge: "border-l-cyan-600", text: "text-cyan-800", chip: "bg-cyan-50 text-cyan-800 border-cyan-300" },
  judge: { name: "風險審查", edge: "border-l-rose-600", text: "text-rose-800", chip: "bg-rose-50 text-rose-800 border-rose-300" },
};

// 判定詞彙(規格書 7.1:resolved / partial / unresolved,全系統統一)
export const VERDICT = {
  resolved: { label: "已化解", cls: "bg-emerald-50 text-emerald-800 border-emerald-400" },
  partial: { label: "部分化解", cls: "bg-amber-50 text-amber-800 border-amber-400" },
  unresolved: { label: "未化解", cls: "bg-rose-50 text-rose-800 border-rose-400" },
};

export const STAGE_LABEL = { pre: "拜訪前", mid: "拜訪中", post: "拜訪後" };

// 矛盾嚴重度(規格書 6.4):severity 決定警示框顏色深淺
export const SEVERITY = {
  high:   { label: "高", box: "border-rose-400 bg-rose-100",  chip: "bg-rose-600 text-white border-rose-600" },
  medium: { label: "中", box: "border-rose-300 bg-rose-50",   chip: "bg-rose-50 text-rose-800 border-rose-400" },
  low:    { label: "低", box: "border-rose-200 bg-white",     chip: "bg-white text-rose-700 border-rose-300" },
};

export const TABS = [
  { key: "committee", label: "AI 審查會議" },
  { key: "pre", label: "拜訪前情資" },
  { key: "post", label: "拜訪中與後" },
  { key: "market", label: "市場訊號" },   // 股價市場訊號模組 v1.0
];
