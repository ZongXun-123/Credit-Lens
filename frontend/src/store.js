// 跨頁籤共用狀態:AI 審查會議的裁決結果
// 「拜訪後評分」需要 base_score(5.10)、「產出報告」需要 judge_result(5.6)
//
// v1.6 一致性原則:
//   財務／技術 Agent 是「可保存、可挑選版本」的分析素材(有歷次紀錄);
//   風險審查官與其下游的拜訪後評分則是「衍生結果」,一律以畫面上當下的
//   財務／技術結果為準。因此兩位 Agent 一有變動,審查官即自動重跑,
//   並更新 judgeStamp,讓已算過拜訪後評分的頁籤知道基準分已過期。
import { reactive } from "vue";

export const store = reactive({
  judgeByCompany: {},   // { [company_id]: JudgeResult }
  judgeStamp: {},       // { [company_id]: number } 裁決更新時間戳,變動即代表基準分已換
});

export function setJudge(companyId, judge) {
  store.judgeByCompany[companyId] = judge;
  store.judgeStamp[companyId] = Date.now();
}