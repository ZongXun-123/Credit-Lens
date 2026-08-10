// ============================================================
// 示範資料(僅供 EAP/外部 API 失效時的保險絲,以及離線展示)
// ★ 只保留「一筆」示範公司,且名稱、內容皆明確標示【示範資料】,
//   一旦畫面出現這些字樣,就代表當下顯示的不是真實查詢結果。
// 正常情況下(USE_MOCK=false + 後端 OPEN_DATA=true)不會用到本檔內容。
// ============================================================

export const CASES = [
];

export const MOCK = {
  // AgentResult(6.1)— EAP 失效時的降級內容
  finance: { agent: "finance", score: 58, findings: [
    { text: "【示範資料】本段為系統降級時的預設內容,非真實財務分析結果。", cite: "【示範】非真實來源", confidence: 0.5 },
  ]},
  tech: { agent: "tech", score: 81, findings: [
    { text: "【示範資料】本段為系統降級時的預設內容,非真實技術分析結果。", cite: "【示範】非真實來源", confidence: 0.5 },
  ]},
  // JudgeResult(6.3)
  judge: {
    agent: "judge",
    contradictions: [
      { title: "【示範】矛盾點範例", detail: "【示範資料】本段為系統降級時的預設內容,非真實交叉質詢結果。", severity: "medium" },
    ],
    verdict: "【示範資料】本段為系統降級時的預設裁決文字,非真實審查結論。",
    final_score: 71,
    waterfall: [
      { label: "基礎分", value: 60, type: "base" }, { label: "示範加分", value: 18, type: "plus" },
      { label: "示範加分二", value: 9, type: "plus" }, { label: "示範扣分", value: -12, type: "minus" },
      { label: "示範扣分二", value: -4, type: "minus" },
    ],
  },
  // BriefResult(5.7)— 五維雷達 + 防禦提問單
  radar: [
    { key: "tech", label: "技術量能", score: 82, benchmark: 55, agent: "tech", reason: "【示範資料】非真實評分理由。", cites: ["【示範】非真實來源"] },
    { key: "market", label: "市場潛力", score: 74, benchmark: 60, agent: "tech", reason: "【示範資料】非真實評分理由。", cites: ["【示範】非真實來源"] },
    { key: "finance", label: "財務體質", score: 48, benchmark: 65, agent: "finance", reason: "【示範資料】非真實評分理由,為五維最弱項。", cites: ["【示範】非真實來源"] },
    { key: "legal", label: "訴訟風險", score: 71, benchmark: 70, agent: "judge", reason: "【示範資料】非真實評分理由。", cites: ["【示範】非真實來源"] },
    { key: "macro", label: "外部環境", score: 77, benchmark: 62, agent: "finance", reason: "【示範資料】非真實評分理由。", cites: ["【示範】非真實來源"] },
  ],
  questions: [
    { id: 1, dim: "財務體質", q: "【示範資料】此為降級時顯示的預設提問,非 AI 針對本公司產生。", why: "【示範】非真實出題依據" },
    { id: 2, dim: "市場潛力", q: "【示範資料】此為降級時顯示的預設提問,非 AI 針對本公司產生。", why: "【示範】非真實出題依據" },
    { id: 3, dim: "技術方向", q: "【示範資料】此為降級時顯示的預設提問,非 AI 針對本公司產生。", why: "【示範】非真實出題依據" },
  ],
  // ExtractResult(6.9)
  postExtract: {
    commitments: [{ item: "【示範資料】非真實承諾事項", owner: "【示範】", due: "115-08-15" }],
    responses: [{ risk: "【示範】風險點", summary: "【示範資料】非真實回應摘要", verdict: "partial" }],
    new_risks: [{ text: "【示範資料】非真實的新發現風險。" }],
  },
  // PostScoreResult(6.10)
  postScore: {
    final_score: 68,
    waterfall: [
      { label: "拜訪前基準", value: 71, type: "base" }, { label: "示範加分", value: 8, type: "plus" },
      { label: "示範加分二", value: 4, type: "plus" }, { label: "示範扣分", value: -6, type: "minus" },
      { label: "示範扣分二", value: -9, type: "minus" },
    ],
    recommendation: "【示範資料】本段為系統降級時的預設建議,非真實授信建議。",
  },
};

// 情資查詢的離線示範內容(整合後由後端提供真實資料)
export const INTEL = {
};

export const SAMPLE_NOTES = `【示範會議紀錄|請替換為真實內容】
7/16 下午拜訪,出席:財務長、技術長。
資金缺口:已取得創投投資意向書,尚未簽署具約束力文件。
產品進度:主力品項送查中,預計明年上半年取得許可證。
承諾 8/15 前提供:意向書副本、查驗登記進度證明。`;

export const REPORTS = [
];

export const TRACKED_COMMITMENTS = [
  { company: "【示範】模擬生技", item: "【示範資料】非真實承諾事項", owner: "【示範】", due: "115-07-18" },
];

export const ANNOUNCEMENTS = [
  ["115-07-21", "系統說明", "本平臺已介接商工登記、TWSE 營收、食藥署藥品許可證、GDELT 新聞四項公開資料源。"],
];