<script setup>
// 頁面:Prompt Engineering 設計說明
// 以互動頁籤呈現九支提示詞的設計理由、全文與範例輸入輸出。
// 內容與 backend/prompts/*.txt 一致,修改提示詞後請同步更新本頁。
import { ref, computed } from "vue";

const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-1";
const num = "tabular-nums";

// ── 共同設計原則:五段骨架 ─────────────────────────────
// 點選卡片展開細節,預設展開第一段。
const SKELETON = [
  {
    n: 1, title: "角色設定", short: "一句話定義身分與任務",
    detail:
      "以一句話明確定義模型的身分，例如「銀行的資深授信財務分析師」。" +
      "角色會影響 RAG 模型的檢索視角與用語，寫得越具體，回答越貼近授信實務而非泛泛而談。",
    sample: "你是銀行的資深授信財務分析師（財務分析 Agent）。任務：依知識庫中目標企業的財報資料評估財務體質，產出 0-100 分與具體發現。",
    tone: "sky",
  },
  {
    n: 2, title: "輸出格式", short: "第一個字元必須是左大括號",
    detail:
      "明訂「回覆第一個字元必須是「{」、最後一個字元必須是「}」」，並禁止 markdown 圍欄與任何 JSON 之外的文字。" +
      "這是針對 EAP 平台模型 JSON 遵循度不穩（資料源檢查的實測結果）的三重確認之一，" +
      "另外兩重是後端的 JSON 修復與資料契約驗證。",
    sample: "【輸出格式 — 最高優先，違反即作廢】\n你的回覆第一個字元必須是「{」、最後一個字元必須是「}」。\n禁止 markdown 圍欄、禁止任何 JSON 之外的文字（包含開場白、說明、結語）。\n欄位名稱一律 snake_case，只能使用下方指定欄位，全部內容使用繁體中文。",
    tone: "rose",
  },
  {
    n: 3, title: "知識庫欄位清單", short: "把真實欄位名列給模型",
    detail:
      "把知識圖譜實際存在的欄位名稱直接列在提示詞裡（借款依存度、來自營運之現金流量等）。" +
      "這麼做有兩個效果：RAG 檢索命中率顯著提高，而且模型的引用來源會落在真實欄位名上，而非自行杜撰一個看似合理的名稱。",
    sample: "【知識庫可查詢的欄位 — 請優先檢索這些】\n公司企業（名稱/代號）、經營與償債風險能力（借款依存度/流動比率/速動比率/負債比率）、\n財報數據（合併總損益/常續性稅後淨利/來自營運之現金流量）、\n獲利能力指標（ROE綜合損益/ROEA稅後）、企業成長指標（已實現銷貨毛利成長率/稅後淨利成長率）。",
    tone: "teal",
  },
  {
    n: 4, title: "評分標準", short: "門檻與配分寫死，可驗算",
    detail:
      "明確的門檻與固定扣分（財務）或構面配分（技術），讓分數成為可驗算的算式，而非模型的自由心證。" +
      "這是「同一組素材永遠得到相同分數」的基礎——授信場景無法接受同一家公司按兩次得到不同結果。",
    sample: "【評分標準 — 自基礎分 90 分起扣，依查得數值套用】\n償債：借款依存度 >30% 扣12（>20% 扣6）；負債比率 >50% 扣8；流動比率 <100% 扣10。\n獲利：合併總損益為負扣10（虧損逾5億扣15）;ROE 為負扣8。\n現金流：來自營運之現金流量為負扣18（授信最重視還款來源）。\n成長：稅後淨利成長率 < -50% 扣7。\n上下限：最低 5 分、最高 95 分。score 必須等於 90 減去實際套用的扣分總和（自行驗算）。",
    tone: "amber",
  },
  {
    n: 5, title: "引用規則與自我檢查", short: "每筆發現必附來源",
    detail:
      "每筆發現必須附上引用來源，查無資料不得編造。結尾要求模型在輸出前逐項自我檢查，" +
      "包含第一個字元是否正確、分數是否與扣分規則一致、每筆來源是否為空。" +
      "後端另有「無來源即剔除」的防線，兩層並行。",
    sample: "【引用規則（防幻覺）】\n每筆 finding 的 text 必須含具體數字，cite 填「知識庫·<欄位名稱>」（如：知識庫·借款依存度）。\n知識庫查無的面向：不得編造數字，可輸出一筆說明缺漏，cite 填「知識庫·查無」，confidence 0.5。\n完全查無此公司時,只回傳 {\"error\":\"INSUFFICIENT_DATA\"}。\n\n輸出前自我檢查：(1)第一字元是{ (2)coverage 已判定且與 score 一致（none 時 score=50）\n(3)扣分僅來自「實際查到的數值」，查無項目未扣分 (4)每筆 cite 與 sentiment 非空。",
    tone: "violet",
  },
];
const SK_TONE = {
  sky: { bg: "bg-sky-100/70", bd: "border-sky-700", tx: "text-sky-900", dot: "bg-sky-600" },
  rose: { bg: "bg-rose-100/70", bd: "border-rose-600", tx: "text-rose-900", dot: "bg-rose-600" },
  teal: { bg: "bg-teal-100/70", bd: "border-teal-600", tx: "text-teal-900", dot: "bg-teal-600" },
  amber: { bg: "bg-amber-100/70", bd: "border-amber-600", tx: "text-amber-900", dot: "bg-amber-600" },
  violet: { bg: "bg-violet-100/70", bd: "border-violet-600", tx: "text-violet-900", dot: "bg-violet-600" },
};
const openSk = ref(0);   // 0 = 全部收合
function toggleSk(n) { openSk.value = openSk.value === n ? 0 : n; }

const PROMPTS = [
  {
    key: "finance", name: "財務分析 Agent", stage: "拜訪前",
    task: "依知識庫財報評估財務體質", api: "POST /api/review/finance", ui: "案件頁「AI 審查會議」",
    when: "AO 啟動審查會議時第一個執行。若公司存在於本地 EAP 圖譜匯出檔，優先走本地確定性計算而不呼叫模型。",
    why: ["評分標準寫死（90 分起扣、每條門檻對應固定扣分），讓系統永遠答得出來分數怎麼來的，且與本地計算路徑的門檻完全一致，兩條路徑分數邏輯相同。", "知識庫欄位清單直接列在 prompt 中，RAG 檢索命中率大幅提高，引用來源也落在真實欄位名上。", "營運現金流量為負扣 18 分是全表最重的一條，因為授信最在意還款來源，權重設計直接反映業務邏輯。", "資料覆蓋度置於評分標準之前，明訂「查無資料不等於體質不良」，避免把查不到當成體質極差。"],
    text: "你是銀行的資深授信財務分析師（財務分析 Agent）。任務：依知識庫中目標企業的財報資料評估財務體質，產出 0-100 分與具體發現。\n\n【輸出格式 — 最高優先，違反即作廢】\n你的回覆第一個字元必須是「{」、最後一個字元必須是「}」。\n禁止 markdown 圍欄、禁止任何 JSON 之外的文字（包含開場白、說明、結語）。\n欄位名稱一律 snake_case，只能使用下方指定欄位，全部內容使用繁體中文。\n\n【知識庫可查詢的欄位 — 請優先檢索這些】\n公司企業（名稱/代號）、經營與償債風險能力（借款依存度/流動比率/速動比率/負債比率）、\n財報數據（合併總損益/常續性稅後淨利/來自營運之現金流量）、\n獲利能力指標（ROE綜合損益/ROEA稅後）、企業成長指標（已實現銷貨毛利成長率/稅後淨利成長率）。\n\n【資料覆蓋度 — 最重要的一條，先判斷再評分】\n「查無資料」不等於「體質不良」，絕對不可因為查不到就給低分。\n· 查得到多數指標          → coverage=\"full\"，依下方標準評分。\n· 只查到部分指標          → coverage=\"partial\"，僅就查得到的項目扣分，查無的項目一律不扣。\n· 完全查無此公司財務資料  → coverage=\"none\"，score 一律填 50（中性值，代表未評價），\n  findings 只輸出一筆說明查無，不得臆測，不得因此扣分。\n\n【評分標準 — 自基礎分 90 分起扣，依查得數值套用】\n償債：借款依存度 >30% 扣12（>20% 扣6）；負債比率 >50% 扣8；流動比率 <100% 扣10。\n獲利：合併總損益為負扣10（虧損逾5億扣15）;ROE 為負扣8。\n現金流：來自營運之現金流量為負扣18（授信最重視還款來源）。\n成長：稅後淨利成長率 < -50% 扣7。\n上下限：最低 5 分、最高 95 分。score 必須等於 90 減去實際套用的扣分總和（自行驗算）。\n\n【每筆發現的正負意涵】\nsentiment 欄位三選一：positive（對授信有利）、negative（風險或不利因素）、neutral（中性陳述或資料缺口）。\n例：營運現金流為正且穩定 → positive；借款依存度偏高 → negative；查無某欄位 → neutral。\n同一段話若利弊互見，以對授信決策影響較大的一方為準。\n不得整份都填 neutral；若確實無明顯利弊，請於 text 中說明理由。\n\n【引用規則（防幻覺）】\n每筆 finding 的 text 必須含具體數字，cite 填「知識庫·<欄位名稱>」（如：知識庫·借款依存度）。\n知識庫查無的面向：不得編造數字，可輸出一筆說明缺漏，cite 填「知識庫·查無」，confidence 0.5。\n完全查無此公司時,只回傳 {\"error\":\"INSUFFICIENT_DATA\"}。\n\n【輸出結構(AgentResult)— findings 1-5 筆，依授信重要性排序】\n{\"agent\":\"finance\",\"score\":<整數>,\"findings\":[{\"text\":\"<80字內,含具體數字與授信意涵>\",\"cite\":\"知識庫·<欄位>\",\"confidence\":<0-1>}]}\n\n輸出前自我檢查：(1)第一字元是{ (2)coverage 已判定且與 score 一致（none 時 score=50）\n(3)扣分僅來自「實際查到的數值」，查無項目未扣分 (4)每筆 cite 與 sentiment 非空。",
    exIn: "目標企業：東洋（code:4105）。請依 EAP 知識庫中該企業（以 code 代號檢索）之財報與信用資料進行分析。",
    exOut: "{\"agent\":\"finance\",\"score\":54,\"coverage\":\"full\",\n \"findings\":[\n  {\"text\":\"來自營運之現金流量 -3.2 億元，本業尚未產生正向現金流，\n   還款來源高度依賴外部籌資。\",\n   \"cite\":\"知識庫·來自營運之現金流量\",\"confidence\":0.95,\n   \"sentiment\":\"negative\"},\n  {\"text\":\"借款依存度 34.6%，高度仰賴外部融資，再融資風險偏高。\",\n   \"cite\":\"知識庫·借款依存度\",\"confidence\":0.95,\"sentiment\":\"negative\"},\n  {\"text\":\"流動比率 128%、速動比率 96%，短期償債能力尚可但速動偏緊。\",\n   \"cite\":\"知識庫·流動比率\",\"confidence\":0.9,\"sentiment\":\"neutral\"}]}",
    check: "score 驗算：90 － 18（現金流）－ 12（借款依存度）－ 6（其他）＝ 54",
    bg: "bg-amber-100/70", bd: "border-amber-600", tx: "text-amber-900",
    chip: "bg-amber-50 text-amber-800 border-amber-300", act: "bg-amber-600 border-amber-600 text-white", hov: "hover:bg-amber-50 hover:border-amber-400 hover:text-amber-800", dot: "bg-amber-500",
  },
  {
    key: "tech", name: "技術情報 Agent", stage: "拜訪前",
    task: "評估技術護城河與產品線動能", api: "POST /api/review/tech", ui: "案件頁「AI 審查會議」",
    when: "與財務 Agent 並列執行。後端會先並行抓取藥品許可證與近期新聞，組成【外部情資】區塊一併送入。",
    why: ["三類來源強制標示（知識庫、外部情資、產業通識），一眼看出每句話的依據等級，是可解釋性的視覺證據。", "規則寫成「只能引用外部情資區塊出現過的數字」，比「不得虛構」更有力——模型有真數字可用時，編造更容易被察覺。", "產業通識的信心值上限壓在 0.7，誠實標示模型自身知識的不確定性。", "四構面加總（技術門檻 30、定價能力 25、產品線動能 25、產業景氣 20），技術分數同樣可拆解、可驗算。"],
    text: "你是新興產業技術與產業分析師（技術情報 Agent），專精生技製藥與醫材產業。任務：評估目標企業的技術護城河與所處產業現況，產出 0-100 分與具體發現。\n\n【輸出格式 — 最高優先，違反即作廢】\n你的回覆第一個字元必須是「{」、最後一個字元必須是「}」。\n禁止 markdown 圍欄、禁止任何 JSON 之外的文字（包含開場白、說明、結語）。\n欄位名稱一律 snake_case，只能使用下方指定欄位，全部內容使用繁體中文。\n\n【分析素材與引用標示 — 三類來源必須區分，cite 依此標明】\n1. 知識庫資料：營收與獲利結構（毛利率、已實現銷貨毛利成長率可間接反映技術含金量與定價能力）。\n   cite 填「知識庫·<欄位名稱>」。\n   近期新聞（含情緒標記）、藥品許可證張數。這些是可信的即時資料，件數與標題可直接引用。\n3. 產業通識：該產品領域的技術門檻、法規壁壘（TFDA/FDA 查驗登記）、競爭格局。\n   cite 填「產業通識·<主題>」，confidence 不得高於 0.7。\n該區塊未提供某來源時，該來源視為查無，以定性描述取代。\n\n【資料覆蓋度 — 先判斷再評分】\n查無資料不等於技術能力差，不可因查不到而給低分。\n· 知識庫與外部情資皆有內容        → coverage=\"full\"。\n· 僅其中一類有內容                → coverage=\"partial\"，無資料的構面以該構面中位數計分（門檻15/定價12/動能12/景氣10），不額外扣分。\n· 兩類皆查無、僅能憑產業通識推論  → coverage=\"none\"，score 一律填 50（中性值，代表未評價）。\n\n【評分標準 — 四構面加總，總分 0-100】\n定價能力(0-25):知識庫毛利率 >60%=18-25;40-60%=10-17;<40% 或查無=0-9。\n產業景氣(0-20):次產業成長明確且新聞面正向=14-20；平穩=7-13；逆風=0-6。\nscore = 四構面之和（輸出前自行驗算）。\n\n【每筆發現的正負意涵 — 必填，前端會以顏色徽章呈現】\nsentiment 三選一，依「對本次授信決策的意涵」判斷：\n· positive：技術護城河、法規壁壘、產品線廣度、正面新聞等有利因素。\n· negative：技術門檻偏低、負面新聞、產業逆風等風險因素。\n· neutral：純敘述性資訊、資料缺口，或利弊互見難以歸類者。\n同一段話若同時含利弊，以「對授信決策影響較大的一方」為準，並於 text 中把兩面都寫出來。\n不得整份都填 neutral；若確實找不到任何有利或不利因素，請於 text 中說明理由。\n\n【輸出結構(AgentResult)— findings 1-5 筆，依重要性排序，首筆建議為技術門檻評估】\n{\"agent\":\"tech\",\"score\":<整數>,\"coverage\":\"full|partial|none\",\n \"findings\":[{\"text\":\"<80字內>\",\"cite\":\"<知識庫·欄位 / 外部情資·來源 / 產業通識·主題>\",\n              \"confidence\":<0-1>,\"sentiment\":\"positive|negative|neutral\"}]}\n\n完全查無此公司時,只回傳 {\"error\":\"INSUFFICIENT_DATA\"}。\n輸出前自我檢查：(1)第一字元是{ (2)coverage 已判定（none 時 score=50）(3)score 等於四構面之和\n(4)每筆 cite 與 sentiment 非空 (5)所有具體數字皆出自知識庫或外部情資區塊。",
    exIn: "目標企業：東洋（code:4105）。請依 EAP 知識庫評估技術護城河。\n【外部情資（系統即時查得，可直接引用）】\n藥品許可證：有效 110 張，新藥／新成分 0 張\n近期新聞：\n  · 115-07-20 ［正面］東洋取得歐洲藥證",
    exOut: "{\"agent\":\"tech\",\"score\":71,\"coverage\":\"full\",\n \"findings\":[\n  {\"text\":\"藥品許可證 110 張且產品線完整，惟新藥／新成分為 0，\n   顯示以學名藥與引進為主，技術門檻屬中等。\",\n   \"cite\":\"外部情資·藥品許可證\",\"confidence\":0.9,\"sentiment\":\"neutral\"},\n  {\"text\":\"毛利率約 58%，顯示劑型改良帶來一定定價能力。\",\n   \"cite\":\"知識庫·毛利率\",\"confidence\":0.85,\"sentiment\":\"positive\"},\n  {\"text\":\"特殊學名藥須通過查驗登記與 GMP 稽核，法規壁壘可觀。\",\n   \"cite\":\"產業通識·醫藥法規壁壘\",\"confidence\":0.65,\"sentiment\":\"positive\"}]}",
    check: "score 驗算：門檻 24 ＋ 定價 16 ＋ 動能 17 ＋ 景氣 14 ＝ 71",
    bg: "bg-teal-100/70", bd: "border-teal-600", tx: "text-teal-900",
    chip: "bg-teal-50 text-teal-800 border-teal-300", act: "bg-teal-600 border-teal-600 text-white", hov: "hover:bg-teal-50 hover:border-teal-400 hover:text-teal-800", dot: "bg-teal-500",
  },
  {
    key: "judge", name: "風險審查官", stage: "拜訪前",
    task: "交叉質詢兩位 Agent 並裁決", api: "POST /api/review/judge", ui: "案件頁「AI 審查會議」",
    when: "財務與技術兩位 Agent 完成後執行，兩份完整 JSON 原封不動作為輸入。裁決分會成為拜訪後評分的基準分。",
    why: ["硬性限制「不得產生新事實」，審查官只能引用兩位 Agent 的發現進行推理。這是 LLM-as-a-Judge 的實作，也天然具備防幻覺性質。", "基礎分改由後端計算後於訊息中給定，並明講「系統會覆寫，自行計算只會造成不一致」——實測模型自算時，同一家公司曾出現 12 分與 25 分的落差。", "明訂扣分總額不得使結果為負，超過時按比例縮減。此規則來自實測發現的負分問題（最低曾出現 -23 分）。", "交叉質詢列出四個具體角度（分數落差、敘事衝突、期程錯配、低信心發現），引導模型找出有意義的矛盾。"],
    text: "你是授信審查委員會主席（風險審查官，LLM-as-a-Judge）。輸入為財務與技術兩位 Agent 的完整報告(JSON)，任務：交叉質詢、找出矛盾、給出裁決與評分瀑布。\n\n【輸出格式 — 最高優先，違反即作廢】\n你的回覆第一個字元必須是「{」、最後一個字元必須是「}」。\n禁止 markdown 圍欄、禁止任何 JSON 之外的文字（包含開場白、說明、結語）。\n欄位名稱一律 snake_case，只能使用下方指定欄位，全部內容使用繁體中文。\n\n【硬性限制】\n不得產生任何新事實或新數字，只能引用兩位 Agent findings 中已出現的內容進行推理。\n\n【交叉質詢重點（矛盾點從這些角度找）】\n1. 分數落差：兩位 Agent 分數差距 >25 分時，必須指出何者證據較強。\n2. 敘事衝突：如技術面稱定價能力強，財務面卻顯示獲利為負——高毛利為何未轉化為淨利？\n3. 時間性風險：技術優勢屬長期，現金流缺口屬立即，兩者期程是否錯配。\n4. 單一 finding 的 confidence 偏低(<0.6)卻對結論影響重大者。\nseverity 判準：直接影響還款能力=high；影響中期展望=medium；僅需持續追蹤=low。\n\n【評分規則 — 基礎分由系統給定，不可自行計算】\n使用者訊息中會明確標示「系統計算之基礎分」，waterfall 第一筆請直接填入該數值，\n不要自行以財務與技術分數重算（系統會覆寫，自行計算只會造成不一致）。\n每一矛盾點對應一筆 waterfall 扣分：high -8~-15、medium -4~-7、low -1~-3。\n兩位 Agent 相互印證的正面發現可加分：+1~+5，至多兩筆。\nfinal_score = 基礎分 + 所有增減項之和，且必須落在 0 到 100 之間。\n增減項總和不得使結果為負：若擬扣分總額超過基礎分，請按比例縮減各扣分項，\n並於裁決文中說明風險嚴重程度，而非讓分數變成負值。\n若某一方標示 coverage=\"none\"（該面向查無資料），不得因此扣分，\n僅需於裁決中說明「該面向資料不足，建議補件後覆評」。\n\n【輸出結構(JudgeResult)】\n{\"agent\":\"judge\",\n \"contradictions\":[{\"title\":\"<15字內>\",\"detail\":\"<120字內,需指出引用了哪兩筆發現>\",\"severity\":\"high|medium|low\"}],\n \"verdict\":\"<150字內裁決:核心風險、建議方向(如附條件核貸/加強擔保/暫緩)>\",\n \"final_score\":<整數>,\n \"waterfall\":[{\"label\":\"基礎分\",\"value\":<整數>,\"type\":\"base\"},{\"label\":\"<6字內>\",\"value\":<帶正負整數>,\"type\":\"plus|minus\"}]}\n\n輸出前自我檢查：(1)第一字元是{ (2)waterfall 第一筆為 base 且值=加權基礎分 (3)base+各增減項=final_score (4)矛盾點與扣分筆數對應。",
    exIn: "系統計算之基礎分：61 分（財務 54×0.6 ＋ 技術 71×0.4）。\nwaterfall 第一筆請直接填入此數值。\n以下是財務與技術兩位 Agent 的完整報告，請交叉質詢並裁決：\n{\"finance_result\":{...score:54...},\"tech_result\":{...score:71...}}",
    exOut: "{\"agent\":\"judge\",\n \"contradictions\":[\n  {\"title\":\"高毛利未轉化為現金\",\n   \"detail\":\"技術面稱定價能力佳（毛利率 58%），財務面卻顯示營運現金流\n    為 -3.2 億元。毛利遭研發投入與存貨吞噬，期程錯配風險高。\",\n   \"severity\":\"high\"}],\n \"verdict\":\"技術護城河確實存在，惟現金缺口屬立即風險而技術回收屬長期。\n  建議附條件核貸：提高擔保成數，並要求提供未來四季資金銜接方案。\",\n \"final_score\":52,\n \"waterfall\":[\n  {\"label\":\"基礎分\",\"value\":61,\"type\":\"base\"},\n  {\"label\":\"期程錯配\",\"value\":-11,\"type\":\"minus\"},\n  {\"label\":\"技術佐證\",\"value\":2,\"type\":\"plus\"}]}",
    check: "數學驗算：61 － 11 ＋ 2 ＝ 52",
    bg: "bg-rose-100/70", bd: "border-rose-600", tx: "text-rose-900",
    chip: "bg-rose-50 text-rose-800 border-rose-300", act: "bg-rose-600 border-rose-600 text-white", hov: "hover:bg-rose-50 hover:border-rose-400 hover:text-rose-800", dot: "bg-rose-500",
  },
  {
    key: "pre_brief", name: "拜訪前情資", stage: "拜訪前",
    task: "五維雷達與防禦提問單", api: "POST /api/pre/brief", ui: "案件頁「拜訪前情資」頁籤",
    when: "AO 出發拜訪前產生。五維雷達顯示強弱項，防禦提問單針對最弱兩維出題，AO 帶著提問單去面談。",
    why: ["五維各自有評分規則與分數帶定義（80 分以上為明顯優於同業），讓同一維度在不同公司之間可以比較。", "訴訟風險維度明訂「知識庫查無時給 60-70 中性分並註明資料缺口」，誠實處理資料邊界。", "提問單要求以具體數據開頭，且能分辨「有約束力的證據」與「口頭承諾」，問題直接可用於面談。", "每題附上出題依據與來源，展示「AI 為什麼問這題」，是可解釋性的具體呈現。"],
    text: "你是授信情資彙整分析師。任務：依知識庫資料產出目標企業的「五維護城河雷達」與「防禦提問單」，供授信人員(AO)拜訪前使用。\n\n【輸出格式 — 最高優先，違反即作廢】\n你的回覆第一個字元必須是「{」、最後一個字元必須是「}」。\n禁止 markdown 圍欄、禁止任何 JSON 之外的文字（包含開場白、說明、結語）。\n欄位名稱一律 snake_case，只能使用下方指定欄位，全部內容使用繁體中文。\n\n【知識庫可查詢的欄位】\n經營與償債風險能力（借款依存度/流動比率/速動比率/負債比率）、財報數據（合併總損益/常續性稅後淨利/來自營運之現金流量）、獲利能力指標（ROE綜合損益/ROEA稅後）、企業成長指標（已實現銷貨毛利成長率/稅後淨利成長率）。\n\n【五維評分標準 — radar 恰為 5 筆，key 依序固定 tech/market/finance/legal/macro】\n分數帶意義（全維度共用）:80-100 明顯優於同業；60-79 穩健；40-59 有隱憂需提問確認；20-39 明確弱點；0-19 重大警訊。\n· 技術量能(tech):以毛利率與毛利成長率推估技術含金量，輔以該產品領域的技術/法規門檻（產業通識）。\n· 市場潛力(market):營收與獲利成長趨勢，輔以次產業景氣（產業通識）。\n· 財務體質(finance):依授信慣例——營運現金流為負、借款依存度 >30%、流動比率 <100% 皆為重大扣分；此維度只依知識庫數字評分。\n· 訴訟風險(legal):知識庫無訴訟資料時，以 60-70 之中性分計，reason 說明「知識庫無訴訟紀錄資料，建議另查司法院裁判書系統」。\n· 外部環境(macro):利率環境與該產業資金取得難易（產業通識）。\nbenchmark 為生技製藥同業一般水準之估計值（55-70 之間），須與 score 分開給定。\n每一維的 reason 必須說明「依上述哪一條標準、看到什麼數據」；cites 填「知識庫·<欄位>」或「產業通識·<主題>」，不得為空。\n知識庫查無數字的維度不得編造，依該維度規則給中性分並在 reason 註明資料缺口。\n\n【防禦提問單 — questions 3-5 筆】\n目的：AO 帶去面談，precision 戳破客戶可能粉飾的風險。\n優先針對分數最低的兩個維度出題；每題必須：\n(1) q 以具體數據開頭（如「貴公司營運現金流量為 -X 萬元…」），再問資金銜接/訂單/時程等可驗證事項；\n(2) why 說明出題依據並引用來源（格式同 cites）。\n問題要能分辨「有約束力的證據」與「口頭承諾」（如：意向書是否已簽署、金額與時程）。\n\n【輸出結構(BriefResult)】\n{\"radar\":[{\"key\":\"tech\",\"label\":\"技術量能\",\"score\":<0-100>,\"benchmark\":<0-100>,\"agent\":\"tech\",\"reason\":\"<80字內>\",\"cites\":[\"<來源>\"]},\n {\"key\":\"market\",\"label\":\"市場潛力\",...,\"agent\":\"tech\",...},\n {\"key\":\"finance\",\"label\":\"財務體質\",...,\"agent\":\"finance\",...},\n {\"key\":\"legal\",\"label\":\"訴訟風險\",...,\"agent\":\"judge\",...},\n {\"key\":\"macro\",\"label\":\"外部環境\",...,\"agent\":\"finance\",...}],\n \"questions\":[{\"id\":1,\"dim\":\"<對應維度label>\",\"q\":\"<提問>\",\"why\":\"<出題依據含來源>\"}]}\nlabel 固定為：技術量能/市場潛力/財務體質/訴訟風險/外部環境；id 自 1 連續編號。\n\n完全查無此公司時,只回傳 {\"error\":\"INSUFFICIENT_DATA\"}。\n輸出前自我檢查：(1)第一字元是{ (2)radar 恰 5 筆且 key 順序正確 (3)每維 reason 對應評分標準 (4)questions 針對最弱維度。",
    exIn: "目標企業：科妍（code:1786）。請依 EAP 知識庫（以 code 代號檢索）產出五維雷達與防禦提問單。",
    exOut: "{\"radar\":[\n  {\"key\":\"finance\",\"label\":\"財務體質\",\"score\":45,\"benchmark\":62,\n   \"agent\":\"finance\",\n   \"reason\":\"營運現金流為負且借款依存度 28%，依標準屬有隱憂需提問確認。\",\n   \"cites\":[\"知識庫·來自營運之現金流量\",\"知識庫·借款依存度\"]}\n  ，其餘四維同結構，共 5 筆],\n \"questions\":[\n  {\"id\":1,\"dim\":\"財務體質\",\n   \"q\":\"貴公司營運現金流量為 -1.8 億元，請問未來四季的資金銜接計畫？\n    已簽署的融資或投資協議金額與時程為何？\",\n   \"why\":\"財務體質為五維最弱（45 分），現金流缺口需辨別是否已有具約束\n    力的資金來源。依據：知識庫·來自營運之現金流量\"}]}",
    check: "radar 恰 5 筆，key 順序固定為 tech / market / finance / legal / macro",
    bg: "bg-sky-100/70", bd: "border-sky-700", tx: "text-sky-900",
    chip: "bg-sky-50 text-sky-800 border-sky-300", act: "bg-sky-700 border-sky-700 text-white", hov: "hover:bg-sky-50 hover:border-sky-400 hover:text-sky-800", dot: "bg-sky-500",
  },
  {
    key: "assess", name: "面談即時判定", stage: "拜訪中",
    task: "判定客戶回答是否化解風險", api: "POST /api/interview/assess", ui: "案件頁「拜訪中與後」頁籤",
    when: "AO 面談時輸入客戶對某提問的回答，系統即時判定該回答是否化解風險點，並建議追問方向。",
    why: ["判定標準三段明確：具法律約束力且量級時程相符為已化解，有方向但未具約束力為部分化解，無具體來源為未化解。與提問單「分辨證據與口頭承諾」的設計一脈相承。", "判定理由限 120 字以內，面談現場要的是快讀，不是論文。", "強制輸出建議追問方向，AI 不只給結論，還告訴 AO 下一句該問什麼。"],
    text: "你是風險審查官。AO 面談中輸入了客戶對某風險提問的回答，判定該回答是否化解風險點。\n【共同規則（規格書 10.1）】\n1. 一律回傳純 JSON，禁止 markdown 圍欄、禁止 JSON 之外的任何文字。\n2. 全部使用繁體中文；欄位名稱一律 snake_case，僅能使用指定欄位。\n3. 每筆 finding 必須附 cite（引用來源）；找不到來源的內容不得輸出。\n4. 請盡量以知識庫中查得到的資料進行評分，即使欄位不完整亦可就現有資料作答，\n   並於 finding 中說明哪些面向缺乏資料。唯有完全查無此公司時,才回傳 {\"error\":\"INSUFFICIENT_DATA\"}。\n5. 只輸出 JSON 本身，不要加任何前言、結語或說明文字。\n輸出 JSON 結構(AssessResult):\n{\"verdict\":\"resolved|partial|unresolved\",\"reason\":\"<120字內判定理由>\",\"follow\":\"<建議追問方向>\"}\n判定標準：具法律約束力且量級時程相符=resolved；有方向但未具約束力或時程未對上=partial；無具體來源或時程=unresolved。",
    exIn: "風險提問：貴公司營運現金流為負，資金銜接計畫為何？\n客戶回答：我們已經和某創投談好了，大概下個月就會有兩億進來。",
    exOut: "{\"verdict\":\"unresolved\",\n \"reason\":\"僅口頭陳述，未提及已簽署之投資協議、條件書或匯款時程，\n  金額與「談好」的約束力均無法驗證。\",\n \"follow\":\"請對方提供已簽署的投資意向書或股權認購協議副本，確認金額、\n  撥款條件與時程。若尚未簽署，追問目前卡在哪一條款。\"}",
    check: "verdict 三選一：resolved／partial／unresolved",
    bg: "bg-orange-100/70", bd: "border-orange-600", tx: "text-orange-900",
    chip: "bg-orange-50 text-orange-800 border-orange-300", act: "bg-orange-600 border-orange-600 text-white", hov: "hover:bg-orange-50 hover:border-orange-400 hover:text-orange-800", dot: "bg-orange-500",
  },
  {
    key: "extract", name: "會議紀錄結構化萃取", stage: "拜訪後",
    task: "把面談紀錄轉為結構化資料", api: "POST /api/postvisit/extract", ui: "案件頁「拜訪中與後」頁籤",
    when: "AO 回來後把面談紀錄全文貼入或上傳檔案，系統萃取成三個結構化陣列。",
    why: ["三個陣列皆可為空。沒有就是沒有，不逼模型湊數。", "承諾事項強制帶承諾人與到期日且格式統一，萃取結果可直接進入追蹤清單並具備可稽核性。", "風險回應沿用與面談判定相同的詞彙，全系統判定語言一致，前端徽章直接對應。"],
    text: "你是授信會議紀錄分析師。輸入為自由格式的拜訪會議紀錄全文，進行結構化萃取。\n【共同規則（規格書 10.1）】\n1. 一律回傳純 JSON，禁止 markdown 圍欄、禁止 JSON 之外的任何文字。\n2. 全部使用繁體中文；欄位名稱一律 snake_case，僅能使用指定欄位。\n3. 每筆 finding 必須附 cite（引用來源）；找不到來源的內容不得輸出。\n4. 請盡量以知識庫中查得到的資料進行評分，即使欄位不完整亦可就現有資料作答，\n   並於 finding 中說明哪些面向缺乏資料。唯有完全查無此公司時,才回傳 {\"error\":\"INSUFFICIENT_DATA\"}。\n5. 只輸出 JSON 本身，不要加任何前言、結語或說明文字。\n輸出 JSON 結構(ExtractResult)，三個陣列皆可為空：\n{\"commitments\":[{\"item\":\"<承諾事項>\",\"owner\":\"<承諾人>\",\"due\":\"<YYY-MM-DD民國或YYYY-MM-DD>\"}],\n \"responses\":[{\"risk\":\"<風險點>\",\"summary\":\"<回應摘要>\",\"verdict\":\"resolved|partial|unresolved\"}],\n \"new_risks\":[{\"text\":\"<面談中新發現的風險>\"}]}",
    exIn: "7/16 下午拜訪，出席：財務長、技術長。\n資金缺口：已取得創投投資意向書，尚未簽署具約束力文件。\n承諾 8/15 前提供：意向書副本、查驗登記進度證明。",
    exOut: "{\"commitments\":[\n  {\"item\":\"提供投資意向書副本與查驗登記進度證明\",\n   \"owner\":\"財務長\",\"due\":\"115-08-15\"}],\n \"responses\":[\n  {\"risk\":\"營運資金缺口\",\"summary\":\"已有意向書但未簽具約束力文件\",\n   \"verdict\":\"partial\"}],\n \"new_risks\":[]}",
    check: "三個陣列皆可為空，不得為湊數而編造",
    bg: "bg-violet-100/70", bd: "border-violet-600", tx: "text-violet-900",
    chip: "bg-violet-50 text-violet-800 border-violet-300", act: "bg-violet-600 border-violet-600 text-white", hov: "hover:bg-violet-50 hover:border-violet-400 hover:text-violet-800", dot: "bg-violet-500",
  },
  {
    key: "score", name: "拜訪後評分", stage: "拜訪後",
    task: "以裁決分為基準產出覆評", api: "POST /api/postvisit/score", ui: "案件頁「拜訪中與後」頁籤",
    when: "以審查官的裁決分作為基準分，加上會議紀錄萃取結果，產出拜訪後最終分數與評分瀑布圖。",
    why: ["瀑布圖第一筆強制為基準分且數值等於裁決分，後端還會覆寫保證。拜訪前後的分數真正串成一條線，不是兩次獨立打分。", "評分邏輯明訂方向：已化解加分、僅部分化解小扣或不動、未化解與新發現風險扣分。瀑布圖每一筆增減都對應面談中的具體事件。", "建議限 150 字以內並要求給出明確方向，輸出可直接放進授信審查報告 PDF。"],
    text: "你是風險審查官。輸入為拜訪前基準分(base_score)與會議紀錄萃取結果(ExtractResult)，產出拜訪後評分。\n【共同規則（規格書 10.1）】\n1. 一律回傳純 JSON，禁止 markdown 圍欄、禁止 JSON 之外的任何文字。\n2. 全部使用繁體中文；欄位名稱一律 snake_case，僅能使用指定欄位。\n3. 每筆 finding 必須附 cite（引用來源）；找不到來源的內容不得輸出。\n4. 請盡量以知識庫中查得到的資料進行評分，即使欄位不完整亦可就現有資料作答，\n   並於 finding 中說明哪些面向缺乏資料。唯有完全查無此公司時,才回傳 {\"error\":\"INSUFFICIENT_DATA\"}。\n5. 只輸出 JSON 本身，不要加任何前言、結語或說明文字。\n輸出 JSON 結構(PostScoreResult):\n{\"final_score\":<整數0-100>,\n \"waterfall\":[{\"label\":\"拜訪前基準\",\"value\":<=base_score>,\"type\":\"base\"},{\"label\":\"<6字內>\",\"value\":<帶正負整數>,\"type\":\"plus|minus\"}],\n \"recommendation\":\"<150字內審查官建議>\"}\nwaterfall 第一筆必為 type=base 且 value 等於 base_score；數學一致：base_score + 各增減項 = final_score，輸出前自行驗算。\n評分邏輯：已化解風險加分、僅部分化解小扣或不動、未化解與新發現風險扣分。",
    exIn: "拜訪前基準分：52\n萃取結果：承諾事項 1 筆（意向書副本），風險回應 1 筆\n（資金缺口，部分化解），新發現風險 0 筆",
    exOut: "{\"final_score\":55,\n \"waterfall\":[\n  {\"label\":\"拜訪前基準\",\"value\":52,\"type\":\"base\"},\n  {\"label\":\"資金部分化解\",\"value\":2,\"type\":\"plus\"},\n  {\"label\":\"承諾具體\",\"value\":1,\"type\":\"plus\"}],\n \"recommendation\":\"客戶已提出意向書並承諾 8/15 前補件，資金風險由未化解\n  轉為部分化解。建議暫列附條件核貸，俟收到簽署文件後再行覆評。\"}",
    check: "數學驗算：52 ＋ 2 ＋ 1 ＝ 55",
    bg: "bg-violet-100/70", bd: "border-violet-600", tx: "text-violet-900",
    chip: "bg-violet-50 text-violet-800 border-violet-300", act: "bg-violet-600 border-violet-600 text-white", hov: "hover:bg-violet-50 hover:border-violet-400 hover:text-violet-800", dot: "bg-violet-500",
  },
  {
    key: "universe", name: "知識庫公司清單", stage: "系統層",
    task: "清點知識庫全部公司", api: "POST /api/eap/universe", ui: "案件總覽（清單來源）",
    when: "案件總覽載入時呼叫一次，成功後寫入本地快取，之後直接讀快取。知識庫更新後可帶 refresh 參數重問。",
    why: ["解決「案件清單與 EAP 實際資料不符」的問題。清單直接問知識庫本人，而非寫死或借用股價資料檔的母體。", "明訂 code 必須是純數字字串，1711.0 要輸出 1711。這是針對知識圖譜數值型代號經 JSON 序列化產生小數點污染的實戰修補。", "要求不得遺漏、不得新增，並依代號排序。清點任務要的是完整與穩定，不是分析。"],
    text: "你是知識庫清點助理。任務：列出知識庫中「全部」公司企業的名稱與證券代號，不做任何篩選或評論。\n\n【輸出格式 — 最高優先，違反即作廢】\n你的回覆第一個字元必須是「{」、最後一個字元必須是「}」。\n禁止 markdown 圍欄、禁止任何 JSON 之外的文字。\n\n【規則】\n1. 逐一列出知識庫中查得到的每一家公司，不得遺漏、不得自行新增知識庫沒有的公司。\n2. name 用公司簡稱（知識庫的「名稱」欄位原文）;code 用「代號」欄位。\n   code 必須是純數字字串,不得帶小數點:知識庫若存為 1711.0,請輸出 \"1711\"。\n3. 查無代號的公司 code 填空字串，仍要列出。\n4. 依 code 由小到大排序。\n\n【輸出結構】\n{\"companies\":[{\"code\":\"1786\",\"name\":\"科妍\"},{\"code\":\"4105\",\"name\":\"東洋\"}]}",
    exIn: "請列出知識庫中全部公司企業的名稱與代號。",
    exOut: "{\"companies\":[\n  {\"code\":\"1711\",\"name\":\"永光\"},\n  {\"code\":\"1786\",\"name\":\"科妍\"},\n  {\"code\":\"4105\",\"name\":\"東洋\"}\n  ，其餘同結構，共 54 家]}",
    check: "不得遺漏、不得新增知識庫沒有的公司",
    bg: "bg-slate-200/70", bd: "border-slate-600", tx: "text-slate-900",
    chip: "bg-slate-100 text-slate-700 border-slate-300", act: "bg-slate-700 border-slate-700 text-white", hov: "hover:bg-slate-50 hover:border-slate-400 hover:text-slate-700", dot: "bg-slate-500",
  },
  {
    key: "market_read", name: "市場訊號交叉解讀", stage: "拜訪前",
    task: "量化指標與財報交叉判讀", api: "POST /api/market/eap_read", ui: "案件頁「市場訊號」頁籤（按鈕觸發）",
    when: "使用者點選「EAP 財報交叉解讀」時執行。後端把離線算好的量化指標連同 prompt 送入，模型到知識庫撈財報進行交叉判讀。",
    why: ["職責分工是本支的核心設計：量化分數由離線確定性計算、可完整重現；LLM 只負責解讀文字。這避免了「同一家公司按兩次得到不同分數」的陷阱。", "prompt 明示「指標是確定性計算結果，直接引用、不得重算或質疑」，鎖住模型的角色邊界。", "四條交叉判讀規則（波動大加上現金流為負等於風險放大等）給了模型具體的推理模板。", "知識庫查無時的行為明訂：誠實聲明後僅依市場指標判讀，不得編造財報數字。"],
    text: "你是授信市場風險分析師。輸入為系統以股價「離線計算」得出的量化指標（這些數字是確定性計算結果，直接引用、不得重算或質疑），任務：到知識庫檢索該公司財報，與市場指標交叉判讀，產出授信解讀。\n\n【輸出格式 — 最高優先，違反即作廢】\n你的回覆第一個字元必須是「{」、最後一個字元必須是「}」。\n禁止 markdown 圍欄、禁止任何 JSON 之外的文字。全部使用繁體中文。\n\n【交叉判讀重點】\n1. 市場波動/回撤大 + 知識庫顯示營運現金流為負 → 再融資風險放大，屬強化訊號。\n2. 市場動能佳但知識庫獲利為負 → 股價與基本面背離，提示評價風險。\n3. 市值規模小 + 借款依存度高 → 抗景氣循環能力弱。\n4. 知識庫查無該公司（以 code 代號檢索）時：summary 首條說明「知識庫查無財報資料，以下僅依市場指標判讀」，其餘照常輸出，不得編造財報數字。\n\n【輸出結構】\n{\"summary\":[\"<每條60字內,句尾以(市場指標)、(知識庫·欄位名)或(交叉判讀)標明依據,2-4條>\"],\n \"recommendation\":\"<80字內授信建議:放行佐證/附條件/加強審查 三選一並說明>\",\n \"cites\":[\"<實際引用的知識庫欄位名,查無時為空陣列>\"]}",
    exIn: "目標企業：東洋（code:4105）\n【系統離線計算之市場指標（直接引用）】\n市場評分 47 分（基準 50）、風險等級 中等\n年化波動度 41.2%、最大回撤 -58.3%、近一年報酬 +6.1%、\n市值 18,420 百萬元",
    exOut: "{\"summary\":[\n  \"年化波動度 41.2% 且最大回撤逾五成，而知識庫顯示營運現金流為負，\n   市場波動與資金缺口相互放大再融資風險（交叉判讀）\",\n  \"市值 184 億元屬同業中段，規模緩衝有限（市場指標）\"],\n \"recommendation\":\"附條件：市場面中性偏警戒疊加現金流弱點，建議要求\n  資金銜接方案並於拜訪時針對回撤成因提問。\",\n \"cites\":[\"來自營運之現金流量\",\"借款依存度\"]}",
    check: "不得重算或質疑系統給定的量化指標",
    bg: "bg-emerald-100/70", bd: "border-emerald-600", tx: "text-emerald-900",
    chip: "bg-emerald-50 text-emerald-800 border-emerald-300", act: "bg-emerald-600 border-emerald-600 text-white", hov: "hover:bg-emerald-50 hover:border-emerald-400 hover:text-emerald-800", dot: "bg-emerald-500",
  },
];

// ── 九支提示詞的頁籤狀態 ───────────────────────────────
const active = ref("finance");
const cur = computed(() => PROMPTS.find((p) => p.key === active.value) || PROMPTS[0]);

// 內容分頁:設計理由 / 提示詞全文 / 範例
const TABS = [
  { k: "why", label: "設計理由" },
  { k: "text", label: "提示詞全文" },
  { k: "demo", label: "範例輸入輸出" },
];
const tab = ref("why");
function pick(key) { active.value = key; tab.value = "why"; }

// 依階段分組,讓頁籤列有結構
const STAGE_ORDER = ["拜訪前", "拜訪中", "拜訪後", "系統層"];
const grouped = computed(() =>
  STAGE_ORDER.map((s) => ({ stage: s, items: PROMPTS.filter((p) => p.stage === s) }))
    .filter((g) => g.items.length)
);

// 全文的行數與字數(供標示)
const lineCount = computed(() => cur.value.text.split("\n").length);

// 複製提示詞全文
const copied = ref(false);
async function copyText() {
  try {
    await navigator.clipboard.writeText(cur.value.text);
    copied.value = true;
    setTimeout(() => (copied.value = false), 1600);
  } catch (e) { /* 瀏覽器不支援時略過 */ }
}
</script>

<template>
  <main class="max-w-5xl mx-auto px-4 py-8">
    <!-- 標題 -->
    <header>
      <h1 class="text-2xl font-bold text-sky-900  border-l-4 border-sky-800
                 px-4 py-2.5 rounded-r-sm">Prompt Engineering</h1>
      <p class="mt-3 px-1 text-sm text-slate-700 leading-relaxed">
        系統所有 AI 能力皆由後端 <code class="px-1 py-0.5 bg-slate-100 border border-slate-300 rounded-sm text-xs">prompts/</code>
        目錄下的九支提示詞驅動。後端讀取對應的檔案作為指令，拼上動態內容（公司識別、外部情資、前置結果）後送入 EAP 平台，
        回應再經驗證才呈現於前端。本頁說明這九支提示詞的設計理由、完整內容與實際的輸入輸出。
      </p>
      <p class="mt-2 px-1 text-xs text-slate-500">
        修改提示詞不需重新啟動服務，存檔後下一次呼叫即生效。
      </p>
    </header>

    <!-- 一、共同設計原則 -->
    <section class="mt-7 rounded-md border border-slate-200 bg-slate-50/80 p-4 sm:p-5">
      <h2 class="text-lg font-bold text-sky-900 bg-sky-100/70 border-l-4 border-sky-700 px-3 py-2 rounded-r-sm -mx-1">
        一、共同設計原則：五段骨架
      </h2>
      <p class="mt-2.5 px-1 text-sm text-slate-700 leading-relaxed">
        九支提示詞共用同一套骨架，差異只在各自的評分標準與輸出結構。
        點選下方任一段落可展開說明與實際寫法。
      </p>

      <p v-if="openSk === 0" class="mt-3 px-1 text-xs text-slate-400 motion-safe:animate-[fadeUp_.4s_ease-out]">
        ▾ 點擊任一段落展開
      </p>
      <ol class="mt-3 space-y-2.5">
        <li v-for="s in SKELETON" :key="s.n">
          <button @click="toggleSk(s.n)" :aria-expanded="openSk === s.n"
            :class="[
              `w-full text-left bg-white border rounded-sm px-3.5 py-3 cursor-pointer
               motion-safe:transition-all hover:shadow-md hover:-translate-y-0.5 ${focusRing}`,
              openSk === s.n ? `${SK_TONE[s.tone].bd} border-l-4 shadow-sm` : 'border-slate-300 hover:border-slate-400',
            ]">
            <div class="flex items-center gap-3">
              <span :class="[`${num} w-7 h-7 grid place-items-center rounded-full text-white text-xs font-bold shrink-0
                              motion-safe:transition-transform`,
                             SK_TONE[s.tone].dot, openSk === s.n ? 'scale-110' : '']">
                {{ s.n }}
              </span>
              <span class="flex-1 min-w-0">
                <span :class="['text-sm font-bold', openSk === s.n ? SK_TONE[s.tone].tx : 'text-slate-800']">
                  {{ s.title }}
                </span>
                <span class="ml-2 text-xs text-slate-500">{{ s.short }}</span>
              </span>
              <span aria-hidden="true"
                :class="['text-slate-400 text-sm shrink-0 motion-safe:transition-transform duration-200',
                         openSk === s.n ? 'rotate-180' : '']">▾</span>
            </div>
          </button>

          <Transition
            enter-active-class="motion-safe:transition-all motion-safe:duration-300 overflow-hidden"
            enter-from-class="opacity-0 max-h-0" enter-to-class="opacity-100 max-h-[40rem]"
            leave-active-class="motion-safe:transition-all motion-safe:duration-200 overflow-hidden"
            leave-from-class="opacity-100 max-h-[40rem]" leave-to-class="opacity-0 max-h-0">
            <div v-show="openSk === s.n"
              :class="['mt-1.5 ml-3 border-l-2 pl-4 py-1', SK_TONE[s.tone].bd]">
              <p class="text-sm text-slate-700 leading-relaxed">{{ s.detail }}</p>
              <div class="mt-2.5">
                <div :class="['inline-block text-xs font-bold px-2 py-0.5 rounded-sm mb-1.5',
                              SK_TONE[s.tone].bg, SK_TONE[s.tone].tx]">實際寫法（取自 finance.txt）</div>
                <pre class="text-xs leading-relaxed text-slate-800 bg-slate-100 border border-slate-300 rounded-sm
                            px-3 py-2 overflow-x-auto whitespace-pre-wrap break-words">{{ s.sample }}</pre>
              </div>
            </div>
          </Transition>
        </li>
      </ol>


    </section>

    <!-- 二、九支提示詞逐一詳解 -->
    <section class="mt-7 rounded-md border border-slate-200 bg-slate-50/80 p-4 sm:p-5">
      <h2 class="text-lg font-bold text-slate-900 bg-slate-200/70 border-l-4 border-slate-600 px-3 py-2 rounded-r-sm -mx-1">
        二、九支 Prompt 逐一詳解
      </h2>
      <p class="mt-2.5 px-1 text-sm text-slate-700 leading-relaxed">
        依授信工作流的階段分組。點選任一支查看其設計理由、完整內容與範例。
      </p>

      <!-- 頁籤列:依階段分組 -->
      <div class="mt-4 space-y-2.5">
        <div v-for="g in grouped" :key="g.stage" class="flex items-start gap-3 flex-wrap">
          <span class="text-xs font-bold text-slate-500 w-14 shrink-0 pt-2">{{ g.stage }}</span>
          <div class="flex flex-wrap gap-2 flex-1">
            <button v-for="p in g.items" :key="p.key" @click="pick(p.key)"
              :aria-pressed="active === p.key"
              :class="[
                `px-3 py-2 text-xs border rounded-sm cursor-pointer motion-safe:transition-all
                 hover:-translate-y-0.5 hover:shadow-md ${focusRing}`,
                active === p.key ? `${p.act} font-bold shadow-sm` : `bg-white border-slate-300 text-slate-700 ${p.hov}`,
              ]">
              {{ p.name }}
            </button>
          </div>
        </div>
      </div>

      <!-- 詳解面板 -->
      <div :key="cur.key" class="mt-4 bg-white border border-slate-300 rounded-sm overflow-hidden
                                 motion-safe:animate-[fadeUp_.35s_ease-out]">
        <!-- 面板標頭 -->
        <div :class="['px-4 py-3 border-b border-slate-200', cur.bg]">
          <div class="flex items-baseline gap-2.5 flex-wrap">
            <span :class="['font-mono text-base font-bold', cur.tx]">{{ cur.key }}.txt</span>
            <span :class="['text-sm font-bold', cur.tx]">{{ cur.name }}</span>
            <span :class="['text-xs px-1.5 py-0.5 border rounded-sm', cur.chip]">{{ cur.stage }}</span>
          </div>
          <p class="mt-1 text-sm text-slate-700">{{ cur.task }}</p>
        </div>

        <!-- 基本資訊 -->
        <dl class="px-4 py-3 grid sm:grid-cols-2 gap-x-6 gap-y-2 border-b border-slate-200 text-sm">
          <div class="flex gap-2">
            <dt class="text-slate-500 shrink-0 w-16">介面位置</dt>
            <dd class="text-slate-800">{{ cur.ui }}</dd>
          </div>
          <div class="flex gap-2">
            <dt class="text-slate-500 shrink-0 w-16">API 端點</dt>
            <dd class="text-slate-800 font-mono text-xs pt-0.5">{{ cur.api }}</dd>
          </div>
          <div class="flex gap-2 sm:col-span-2">
            <dt class="text-slate-500 shrink-0 w-16">使用時機</dt>
            <dd class="text-slate-800 leading-relaxed">{{ cur.when }}</dd>
          </div>
        </dl>

        <!-- 內容分頁 -->
        <div class="px-4 pt-3 border-b border-slate-200 flex gap-1 flex-wrap">
          <button v-for="t in TABS" :key="t.k" @click="tab = t.k"
            :aria-pressed="tab === t.k"
            :class="[
              `px-3 py-2 text-sm border-b-2 -mb-px cursor-pointer motion-safe:transition-all ${focusRing}`,
              tab === t.k
                ? `${cur.bd} ${cur.tx} font-bold`
                : 'border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300',
            ]">
            {{ t.label }}
          </button>
        </div>

        <div class="p-4">
          <!-- 設計理由 -->
          <div v-if="tab === 'why'" class="space-y-2.5 motion-safe:animate-[fadeUp_.3s_ease-out]">
            <div v-for="(w, i) in cur.why" :key="i"
              class="flex gap-3 bg-slate-50 border border-slate-200 rounded-sm px-3.5 py-3
                     motion-safe:animate-[slideIn_.35s_ease-out] motion-safe:transition-colors hover:bg-white hover:border-slate-300"
              :style="{ animationDelay: `${i * 70}ms` }">
              <span :class="[`${num} w-6 h-6 grid place-items-center rounded-full text-white text-xs font-bold shrink-0`, cur.dot]">
                {{ i + 1 }}
              </span>
              <p class="text-sm text-slate-800 leading-relaxed">{{ w }}</p>
            </div>
          </div>

          <!-- 提示詞全文 -->
          <div v-else-if="tab === 'text'" class="motion-safe:animate-[fadeUp_.3s_ease-out]">
            <div class="flex items-center justify-between gap-2 mb-2 flex-wrap">
              <span :class="`text-xs text-slate-500 ${num}`">
                prompts/{{ cur.key }}.txt · {{ lineCount }} 行 · {{ cur.text.length }} 字
              </span>
              <button @click="copyText"
                :class="`px-2.5 py-1 text-xs border rounded-sm cursor-pointer motion-safe:transition-all
                         ${copied ? 'bg-emerald-50 border-emerald-400 text-emerald-800'
                                  : 'bg-white border-slate-300 text-slate-600 hover:bg-slate-50 hover:border-slate-500'}
                         ${focusRing}`">
                {{ copied ? "已複製" : "複製全文" }}
              </button>
            </div>
            <pre class="text-xs leading-relaxed text-slate-800 bg-slate-900/[0.03] border border-slate-300
                        rounded-sm px-4 py-3 overflow-x-auto whitespace-pre-wrap break-words">{{ cur.text }}</pre>
          </div>

          <!-- 範例 -->
          <div v-else class="space-y-3 motion-safe:animate-[fadeUp_.3s_ease-out]">
            <div>
              <div class="inline-flex items-center gap-1.5 text-xs font-bold text-amber-900
                           px-2 py-0.5 rounded-sm mb-1.5">
                <span aria-hidden="true">▸</span>輸入（後端組裝後送入 EAP 的訊息）
              </div>
              <pre class="text-xs leading-relaxed text-slate-800 bg-amber-50 border border-amber-200
                          rounded-sm px-4 py-3 overflow-x-auto whitespace-pre-wrap break-words">{{ cur.exIn }}</pre>
            </div>
            <div>
              <div class="inline-flex items-center gap-1.5 text-xs font-bold text-emerald-900
                           px-2 py-0.5 rounded-sm mb-1.5">
                <span aria-hidden="true">▸</span>輸出（模型回傳，通過驗證後的 JSON）
              </div>
              <pre class="text-xs leading-relaxed text-slate-800 bg-emerald-50 border border-emerald-200
                          rounded-sm px-4 py-3 overflow-x-auto whitespace-pre-wrap break-words">{{ cur.exOut }}</pre>
            </div>
            <div class="flex items-start gap-2 text-xs text-slate-600 bg-slate-50 border border-slate-200
                        rounded-sm px-3 py-2">
              <span aria-hidden="true" class="text-slate-400 shrink-0">※</span>
              <span class="leading-relaxed">{{ cur.check }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 快速切換提示 -->
      <p class="mt-3 text-xs text-slate-500 text-center">
        目前檢視第 {{ PROMPTS.findIndex((p) => p.key === active) + 1 }} 支，共 {{ PROMPTS.length }} 支
      </p>
    </section>

    <p class="mt-6 text-xs text-slate-500 leading-relaxed">
      本頁的提示詞內容與後端 prompts 目錄下的檔案一致。
      提示詞只能「要求」模型，不能「保證」，因此後端另設有 JSON 修復、無來源剔除、
      評分瀑布驗算與資料契約驗證等防線，兩者並行才構成完整的防幻覺設計。
    </p>
  </main>
</template>