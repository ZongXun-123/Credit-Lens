# models.py — 規格書第 6 章共用資料結構(Pydantic 自動驗證)
# 列舉值一律逐一列出(7.1 命名一致性),回應欄位 snake_case
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


# ---------- Requests ----------
class ReviewRequest(BaseModel):
    company_id: str = ""          # 統一編號(8 碼)或證券代號,兩者皆可
    company_name: str = ""
    company_code: str = ""        # 證券代號(EAP 知識圖譜以此為鍵)
    force: bool = False           # v1.3:true = 忽略既有紀錄,強制重新產製


class JudgeRequest(BaseModel):
    company_id: str
    company_code: str = ""      # v1.7:證券代號,確保快取鍵與 EAP 查詢一致
    force: bool = False
    finance_result: "AgentResult"
    tech_result: "AgentResult"


class ReportRequest(BaseModel):
    company_id: str
    company_name: str = ""      # v1.3:報告中心以名稱歸檔
    company_code: str = ""      # v1.3:證券代號(檔名與快取鍵)
    # v1.4:改為選填。未帶入時後端自快取資料庫取該公司最新(或釘選)的裁決結果;
    # 連裁決都沒有時仍可產出報告,僅省略審查官章節,其餘有幾段就印幾段。
    judge_result: Optional["JudgeResult"] = None


class AssessRequest(BaseModel):
    company_id: str
    company_code: str = ""      # v1.7:證券代號,確保快取鍵與 EAP 查詢一致
    question_id: int
    question: str
    answer: str


class ExtractRequest(BaseModel):
    company_id: str
    company_code: str = ""      # v1.7:證券代號,確保快取鍵與 EAP 查詢一致
    notes: str


class PostScoreRequest(BaseModel):
    company_id: str
    company_code: str = ""      # v1.7:證券代號,確保快取鍵與 EAP 查詢一致
    base_score: int = Field(ge=0, le=100)
    extract_result: "ExtractResult"


class IntelRequest(BaseModel):
    query: str


class ReportListRequest(BaseModel):
    status: str = "全部"


# 知識問答(自由對話,不套 Agent 契約)
class EapChatRequest(BaseModel):
    message: str
    chat_id: str = ""          # 空值 = 開新對話;帶值 = 沿用同一聊天室以保留上下文
    session_name: str = ""


# ---------- 6.1 / 6.2 ----------
class Finding(BaseModel):
    text: str
    cite: str  # 必填:無來源的發現後端直接丟棄(防幻覺)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    # v1.6:每筆發現標明對授信的意涵,前端以顏色徽章呈現
    sentiment: Literal["positive", "negative", "neutral"] = "neutral"


class AgentResult(BaseModel):
    agent: Literal["finance", "tech"]
    score: int = Field(ge=0, le=100)
    findings: List[Finding]
    # v1.6:資料覆蓋度。none = 知識庫查無資料,此時 score 不具評價意義,
    # 前端顯示「資料不足」而非分數,審查官加權時亦排除此維度。
    coverage: Literal["full", "partial", "none"] = "full"


# ---------- 6.3 / 6.4 / 6.5 ----------
class Contradiction(BaseModel):
    title: str
    detail: str
    severity: Literal["high", "medium", "low"]


class WaterfallItem(BaseModel):
    label: str
    value: int
    type: Literal["base", "plus", "minus"]


class JudgeResult(BaseModel):
    agent: Literal["judge"] = "judge"
    contradictions: List[Contradiction]
    verdict: str
    final_score: int = Field(ge=0, le=100)
    waterfall: List[WaterfallItem]
    # v1.6:基礎分由後端依 財務×0.6 + 技術×0.4 確定性計算,不由模型自行決定
    base_note: str = ""


# ---------- 6.6 / 6.7(5.7 拜訪前情資)----------
class RadarDim(BaseModel):
    key: Literal["tech", "market", "finance", "legal", "macro"]  # v1.2:移除 esg
    label: str
    score: int = Field(ge=0, le=100)
    benchmark: int = Field(ge=0, le=100)
    agent: Literal["finance", "tech", "judge"]
    reason: str
    cites: List[str]


class Question(BaseModel):
    id: int
    dim: str
    q: str
    why: str


class BriefResult(BaseModel):
    radar: List[RadarDim]
    questions: List[Question]


# ---------- 6.8 / 6.9 / 6.10 ----------
class AssessResult(BaseModel):
    verdict: Literal["resolved", "partial", "unresolved"]
    reason: str
    follow: str


class Commitment(BaseModel):
    item: str
    owner: str
    due: str


class RiskResponse(BaseModel):
    risk: str
    summary: str
    verdict: Literal["resolved", "partial", "unresolved"]


class NewRisk(BaseModel):
    text: str


class ExtractResult(BaseModel):
    commitments: List[Commitment]
    responses: List[RiskResponse]
    new_risks: List[NewRisk]


class PostScoreResult(BaseModel):
    final_score: int = Field(ge=0, le=100)
    waterfall: List[WaterfallItem]
    recommendation: str


class ReportResult(BaseModel):
    report_url: str


JudgeRequest.model_rebuild()
ReportRequest.model_rebuild()
PostScoreRequest.model_rebuild()


# ============================================================
# 股價市場訊號模組(產品說明書 v1.0 §7)
# ============================================================
class MarketSignalRequest(BaseModel):
    company_id: str          # 證券代號(如 4105)
    company_name: str = ""
    force: bool = False      # v1.3:市場交叉解讀重新產製


class MarketUniverseRequest(BaseModel):
    industry: str = ""


class MarketMetrics(BaseModel):
    last_close: Optional[float] = None
    vol_full_pct: Optional[float] = None
    vol_1y_pct: Optional[float] = None
    mdd_pct: Optional[float] = None
    mom_1y_pct: Optional[float] = None
    turnover_pct: Optional[float] = None
    amihud: Optional[float] = None
    mktcap: Optional[float] = None


class MarketReading(BaseModel):
    summary: List[str]
    recommendation: str


class MarketSignalResult(BaseModel):
    company_id: str          # 證券代號
    company_name: str = ""
    ban: Optional[str] = None  # 統一編號(由 TWSE/TPEx 對照表解析;查無為 None)
    market_score: Optional[int] = Field(default=None, ge=0, le=100)  # tier=insufficient 時為 None
    level: Literal["低風險", "中等", "偏高風險", "資料不足"]
    tier: Literal["full", "partial", "insufficient"]
    n_days: int
    waterfall: List[WaterfallItem]      # 第一筆必為 type=base、value=50
    metrics: MarketMetrics
    pctile: dict = {}
    prices_monthly: List[float] = []
    reading: MarketReading
    meta: dict = {}