# mock_data.py — 示範資料(僅供 EAP 失效時的降級保險絲)
# ★ 只保留「一筆」示範公司,內容皆標示【示範資料】;畫面出現這些字樣即代表非真實結果。
# 與前端 src/mock.js 逐欄位一致;任何變更需兩邊同步。


FINANCE = {
    "agent": "finance", "score": 58,
    "findings": [
        {"text": "【示範資料】本段為系統降級時的預設內容,非真實財務分析結果。", "cite": "【示範】非真實來源", "confidence": 0.5},
    ],
}

TECH = {
    "agent": "tech", "score": 81,
    "findings": [
        {"text": "【示範資料】本段為系統降級時的預設內容,非真實技術分析結果。", "cite": "【示範】非真實來源", "confidence": 0.5},
    ],
}

JUDGE = {
    "agent": "judge",
    "contradictions": [
        {"title": "【示範】矛盾點範例", "detail": "【示範資料】本段為系統降級時的預設內容,非真實交叉質詢結果。", "severity": "medium"},
    ],
    "verdict": "【示範資料】本段為系統降級時的預設裁決文字,非真實審查結論。",
    "final_score": 71,
    "waterfall": [
        {"label": "基礎分", "value": 60, "type": "base"},
        {"label": "示範加分", "value": 18, "type": "plus"},
        {"label": "示範加分二", "value": 9, "type": "plus"},
        {"label": "示範扣分", "value": -12, "type": "minus"},
        {"label": "示範扣分二", "value": -4, "type": "minus"},
    ],
}

BRIEF = {
    "radar": [
        {"key": "tech", "label": "技術量能", "score": 82, "benchmark": 55, "agent": "tech",
         "reason": "【示範資料】非真實評分理由。", "cites": ["【示範】非真實來源"]},
        {"key": "market", "label": "市場潛力", "score": 74, "benchmark": 60, "agent": "tech",
         "reason": "【示範資料】非真實評分理由。", "cites": ["【示範】非真實來源"]},
        {"key": "finance", "label": "財務體質", "score": 48, "benchmark": 65, "agent": "finance",
         "reason": "【示範資料】非真實評分理由,為五維最弱項。", "cites": ["【示範】非真實來源"]},
        {"key": "legal", "label": "訴訟風險", "score": 71, "benchmark": 70, "agent": "judge",
         "reason": "【示範資料】非真實評分理由。", "cites": ["【示範】非真實來源"]},
        {"key": "macro", "label": "外部環境", "score": 77, "benchmark": 62, "agent": "finance",
         "reason": "【示範資料】非真實評分理由。", "cites": ["【示範】非真實來源"]},
    ],
    "questions": [
        {"id": 1, "dim": "財務體質", "q": "【示範資料】此為降級時顯示的預設提問,非 AI 針對本公司產生。", "why": "【示範】非真實出題依據"},
        {"id": 2, "dim": "市場潛力", "q": "【示範資料】此為降級時顯示的預設提問,非 AI 針對本公司產生。", "why": "【示範】非真實出題依據"},
        {"id": 3, "dim": "技術方向", "q": "【示範資料】此為降級時顯示的預設提問,非 AI 針對本公司產生。", "why": "【示範】非真實出題依據"},
    ],
}

ASSESS = {
    "verdict": "partial",
    "reason": "【示範資料】本段為系統降級時的預設判定理由,非真實判定結果。",
    "follow": "【示範資料】非真實的建議追問方向。",
}

EXTRACT = {
    "commitments": [{"item": "【示範資料】非真實承諾事項", "owner": "【示範】", "due": "115-08-15"}],
    "responses": [{"risk": "【示範】風險點", "summary": "【示範資料】非真實回應摘要", "verdict": "partial"}],
    "new_risks": [{"text": "【示範資料】非真實的新發現風險。"}],
}

POST_SCORE = {
    "final_score": 68,
    "waterfall": [
        {"label": "拜訪前基準", "value": 71, "type": "base"},
        {"label": "示範加分", "value": 8, "type": "plus"},
        {"label": "示範加分二", "value": 4, "type": "plus"},
        {"label": "示範扣分", "value": -6, "type": "minus"},
        {"label": "示範扣分二", "value": -9, "type": "minus"},
    ],
}
POST_SCORE["recommendation"] = "【示範資料】本段為系統降級時的預設建議,非真實授信建議。"

# 情資查詢的離線示範內容:已移除模擬公司 00000000,改為空集合
# (離線模式下情資查詢會回 404,由前端顯示查無資料的提示)
INTEL = {}


# 離線模式的報告清單:留空,由前端顯示「尚無報告」的引導文字
REPORTS = []

COMMITMENTS = []   # 承諾事項追蹤功能已移除,保留空值供舊引用相容