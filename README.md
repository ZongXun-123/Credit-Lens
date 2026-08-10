# 智貸先鋒 Credit-Lens

> 生技製藥產業授信 AI 情資平臺 ─ 精誠 SEI 競賽作品

把授信人員（AO）的工作流拆成「拜訪前、拜訪中、拜訪後」三段，每段配置對應的 AI 能力：
拜訪前由三個 AI Agent 交叉驗證產出風險裁決，拜訪中提供即時提詞判定，
拜訪後把口頭面談轉回可稽核的結構化資料與評分。

---

## 目錄

1. [快速開始](#1-快速開始)
2. [系統架構](#2-系統架構)
3. [核心設計](#3-核心設計)
4. [檔案結構](#4-檔案結構)
5. [API 端點](#5-api-端點)
6. [PROMPT 提示詞](#6-提示詞)
7. [環境變數](#7-環境變數)
8. [工具腳本](#8-工具腳本)
9. [疑難排解](#9-疑難排解)

---

## 1. 快速開始

需要 Python 3.11+ 與 Node.js 18+。**後端與前端請開兩個終端機視窗分別執行。**
**使用前建議於.env置換自己的EAP_TOKEN與EAP_PROJECT_ID，並確保連線暢通。**

### 視窗一 ─ 後端

```powershell
cd backend
pip install -r requirements.txt
pip install openpyxl                # 讀取股價 xlsx 用,requirements 未列
copy .env.example .env              # 已有 .env 且填好 Token 時請跳過此行
notepad .env                        # 填入 EAP_TOKEN 與 EAP_PROJECT_ID
python prefetch.py                  # 建立統編與證券代號對照表(首次執行)
python -m uvicorn main:app --reload --port 8000
```

### 視窗二 ─ 前端

```powershell
cd frontend
npm ci
npm run dev                         # 開啟 http://localhost:5173
```

> **常見錯誤**：`Could not import module "main"` 代表目錄跑錯了，`main.py` 在 `backend/` 底下。
> 從 backend 切到前端要用 `cd ..\frontend`。

### 確認一切正常

```powershell
python check_token.py               # Token 是否有效、何時到期
python check_sources.py 13159100    # 各資料源連通性
```

---

## 2. 系統架構

```
前端 Vue 3（六個頁面）
  案件總覽 · 案件頁（四頁籤）· 情資查詢 · 知識問答 · 報告中心 · 網站導覽 · prompt/評分機制說明
                    │
後端 FastAPI（26 個端點）
  eap.py 平臺封裝 │ cache_store.py 成功快取 │ models.py 資料契約
  opendata.py │ market.py │ tfda.py │ eap_export.py
                    │
資料來源
  精誠 EAP 知識圖譜 · 經濟部商工登記 · TWSE 月營收
  食藥署藥品許可證 · GDELT 新聞 · TEJ 股價（離線）
                    │
  prompts/ 九支提示詞驅動全部 AI 能力
```

### 使用者流程

| 階段 | 步驟 | 頁面 |
|---|---|---|
| 拜訪前 | ① 挑選案件 | 案件總覽 |
| 拜訪前 | ② 查背景資料 | 情資查詢 |
| 拜訪前 | ③ 召開 AI 審查會議 | 案件頁 · 審查會議 |
| 拜訪前 | ④ 取得五維雷達與提問單 | 案件頁 · 拜訪前情資 |
| 拜訪前 | ⑤ 檢視市場訊號 | 案件頁 · 市場訊號 |
| 拜訪中 | ⑥ 面談即時判定 | 案件頁 · 拜訪中與後 |
| 拜訪後 | ⑦ 輸入會議紀錄 | 案件頁 · 拜訪中與後 |
| 拜訪後 | ⑧ 結構化萃取與覆評 | 案件頁 · 拜訪中與後 |
| 拜訪後 | ⑨ 產出授信報告 | 案件頁右上角 |

兩條跨階段資料流：**拜訪前的提問單帶進面談使用**；**審查會議的裁決分成為拜訪後覆評的基準分**。

---

## 3. 核心設計

### 3.1 分數由程式算，AI 只負責判斷與敘述

授信場景無法接受「同一家公司按兩次得到不同分數」。因此：

- **審查官基礎分**由後端計算（財務 × 0.6 ＋ 技術 × 0.4）後帶入提示詞，模型只需填入。
- **市場評分**完全由離線程式依股價計算，AI 只做文字交叉解讀。
- **評分瀑布**由後端驗算，數學不一致或扣分超過基礎分時自動修正。

### 3.2 防幻覺四道防線

提示詞只能「要求」模型，不能「保證」。回應依序通過：

1. **JSON 修復** ─ 去除 markdown 圍欄、修補常見格式錯誤
2. **無來源剔除** ─ 每筆發現必須附 `cite`，沒有的直接丟棄
3. **瀑布驗算** ─ 基礎分 ＋ 增減項必須等於最終分
4. **資料契約** ─ Pydantic 驗證欄位型別與範圍


---

## 4. 檔案結構

### 後端 `backend/`

| 檔案 | 職責 |
|---|---|
| `main.py` | FastAPI 主程式，全部 API 端點、四道防線、基礎分計算、PDF 報告產生器 |
| `eap.py` | 精誠 EAP 平臺封裝：建立對話、送出提問、解析信封、修復 JSON |
| `cache_store.py` | 成功結果快取（SQLite）：存檔、釘選、歷次查詢、素材完整度盤點 |
| `models.py` | Pydantic 資料契約，防幻覺的最後一道防線 |
| `opendata.py` | 經濟部商工登記、TWSE 月營收、統編與代號對照 |
| `market.py` | 市場訊號查詢層（讀取 `market_signal.json`） |
| `tfda.py` | 食藥署藥品許可證查詢 |
| `eap_export.py` | 知識圖譜本地匯出檔解析與確定性財務計算 |
| `mock_data.py` | 降級用示範資料，一律以「【示範資料】」開頭 |
| `envtools.py` | 環境變數讀取工具 |

### 前端 `frontend/src/`

| 檔案 | 職責 |
|---|---|
| `App.vue` | 固定頂端標頭、導覽、字級調整、頁面路由 |
| `pages/DashboardPage.vue` | 案件總覽，依素材完整度排序，四種排序方式 |
| `pages/CasePage.vue` | 案件詳情容器，四頁籤以 KeepAlive 保活 |
| `pages/IntelPage.vue` | 情資查詢，整合四類公開情資 |
| `pages/AskPage.vue` | 知識問答，與 EAP 自由對話 |
| `pages/ReportPage.vue` | 報告中心，下載、加星、刪除 |
| `pages/SitemapPage.vue` | 網站導覽，互動流程地圖 |
| `components/CommitteeTab.vue` | AI 審查會議，三 Agent 卡片與歷次紀錄 |
| `components/PreVisitTab.vue` | 互動式五維雷達圖與防禦提問單 |
| `components/PostVisitTab.vue` | 面談判定、會議紀錄輸入、萃取、覆評 |
| `components/MarketSignalTab.vue` | 市場量化指標與 EAP 交叉解讀 |
| `components/RecordBar.vue` | 歷次紀錄列，載入檢視與設為主要 |
| `components/LoadingCard.vue` | 載入動畫與階段文字輪播 |
| `components/BackToTop.vue` | 回到頂端，含閱讀進度環 |
| `api.js` / `store.js` | API 封裝（逾時、降級）／跨頁籤共用狀態 |

### 資料 `backend/data/`

| 項目 | 說明 |
|---|---|
| `credit_lens.db` | 成功結果快取（**展示資產，記得備份**） |
| `market_signal.json` | 市場訊號離線計算結果（53 家） |
| `prices/` | TEJ 股價 xlsx 原始檔 |
| `demo_notes/` | 展示用會議紀錄（由 `curate_demo.py` 產生） |
| `eap_exports/` | EAP 知識圖譜匯出檔 |

- 運作成功的審查會議資料會存入快取'credit_lens.db'中，以利快速查看。
- 若要實際執行，可點擊系統畫面中之**重新產製**按鈕。


---

## 5. API 端點

### AI 分析類（使用提示詞）

| 端點 | 提示詞 | 說明 |
|---|---|---|
| `/api/review/finance` | `finance` | 財務體質分析 |
| `/api/review/tech` | `tech` | 技術護城河評估，併入外部情資 |
| `/api/review/judge` | `judge` | 交叉質詢與裁決，基礎分由後端帶入 |
| `/api/pre/brief` | `pre_brief` | 五維雷達與防禦提問單 |
| `/api/interview/assess` | `assess` | 面談回答即時判定 |
| `/api/postvisit/extract` | `extract` | 會議紀錄結構化萃取 |
| `/api/postvisit/score` | `score` | 拜訪後覆評與評分瀑布 |
| `/api/eap/universe` | `universe` | 清點知識庫全部公司 |
| `/api/market/eap_read` | `market_read` | 市場指標與財報交叉判讀 |
| `/api/eap/chat` | （無） | 知識問答自由對話 |

### 資料查詢類

`/api/intel/lookup`（多源情資）、`/api/company/search`（公司查詢）、
`/api/market/signal`、`/api/market/universe`（市場訊號）、
`/api/eap/coverage`（圖譜涵蓋範圍）、`/api/eap/status`（連線狀態）、
`/api/notes/extract_text`（解析上傳檔案）

### 系統管理類

`/api/report`（產出報告）、`/api/reports/list · star · delete`（報告管理）、
`/api/cache/stats · coverage · list · get · pin`（快取管理）

---

## 6. PROMPT 提示詞

全部位於 `backend/prompts/`。**修改後不需重啟**，下一次呼叫即生效。

| 檔案 | 階段 | 核心規則 |
|---|---|---|
| `finance.txt` | 拜訪前 | 90 分起扣、固定扣分；查無不扣分並標記覆蓋度；每筆發現標正負意涵 |
| `tech.txt` | 拜訪前 | 四構面加總；三類來源強制標示；只能引用外部情資出現過的數字 |
| `judge.txt` | 拜訪前 | 不得產生新事實；基礎分由系統給定；扣分不得使分數為負 |
| `pre_brief.txt` | 拜訪前 | 五維各有評分規則；查無給中性分並註明；提問須以具體數據開頭 |
| `market_read.txt` | 拜訪前 | 指標為確定性計算結果不得重算；四條交叉判讀規則 |
| `assess.txt` | 拜訪中 | 三段判定標準；理由限 120 字；強制輸出追問方向 |
| `extract.txt` | 拜訪後 | 三陣列皆可為空；承諾強制帶承諾人與到期日 |
| `score.txt` | 拜訪後 | 瀑布第一筆強制為基準分；建議限 150 字 |
| `universe.txt` | 系統層 | 不得遺漏不得新增；代號須為純數字字串 |

### PROMPT 共同五段骨架

1. **角色設定** ─ 一句話定義身分與任務
2. **輸出格式鎖** ─ 第一字元必須是 `{`、最後必須是 `}`，禁止 markdown 圍欄
3. **知識庫欄位清單** ─ 把圖譜實際欄位列給模型，提高檢索命中率
4. **評分標準** ─ 明確門檻與固定配分，讓分數可驗算
5. **引用規則與自我檢查** ─ 每筆發現必附來源；輸出前逐項自檢

> **公司識別格式**一律為「名稱（code:代號）」。EAP 知識圖譜以證券代號為鍵，
> 用統一編號檢索不到。後端會自動處理統編轉代號與浮點污染（`1711.0` → `1711`）。

---

## 7. 環境變數

複製 `.env.example` 為 `.env` 後填寫。**註解要獨立成行**，寫在值後面會被當成值讀入。

| 變數 | 預設 | 說明 |
|---|---|---|
| `EAP_TOKEN` | （必填） | 平臺存取權杖，**有效期僅 24 小時** |
| `EAP_PROJECT_ID` | （必填） | 專案識別碼 |
| `EAP_API_BASE` | `https://cloud.geminidata.com/api/v1` | API 位址 |
| `EAP_TENANT` | 空 | 留空自 Token 的 `g_tid` 自動解析 |
| `EAP_DEBUG` | `false` | 印出 EAP 原始回應（排查格式問題） |
| `CACHE_MODE` | `record` | 快取模式，展示當天改 `replay` |
| `DEMO_COMPANIES` | 空 | 展示優先清單（逗號分隔代號），留空則依素材完整度自動排序 |
| `MOCK_MODE` | `false` | 全離線示範模式 |
| `FALLBACK_ON_ERROR` | `true` | 外部服務失效時是否降級 |
| `OPEN_DATA` | `true` | 是否啟用政府開放資料 |
| `ALLOW_ORIGINS` | `http://localhost:5173` | CORS 白名單 |

---

## 8. 工具腳本

於 `backend/` 目錄執行。多數支援 `--dry` 預覽。

| 指令 | 用途 |
|---|---|
| `python warmup.py --list` | 列出各公司的素材缺口，不執行 |
| `python warmup.py` | 只補「還沒有完整資料」的公司，可重複執行接續 |
| `python warmup.py --all` | 所有公司都跑，已有紀錄的項目仍會略過 |
| `python warmup.py --force` | 連已有紀錄的項目也重跑 |
| `python warmup.py 4105 --repeat 3` | 單一公司重跑多次，累積可挑選的版本 |
| `python curate_demo.py --dry` | 檢視資料品質分級 |
| `python curate_demo.py` | 修復紀錄並產生展示用會議紀錄（不刪除公司） |
| `python curate_demo.py --prune` | 額外刪除素材不足的公司 |
| `python repair_cache.py --dry` | 檢視待修復的紀錄 |
| `python build_market_signal.py --dry` | 由股價 xlsx 重建市場訊號 |
| `python check_sources.py 統編` | 各資料源連通性健檢 |
| `python check_token.py` | Token 有效性與到期時間 |
| `python prefetch.py` | 建立統編與代號對照表 |

### 快速盤點（不需啟動後端）

```powershell
python -c "import cache_store,json;print(json.dumps(cache_store.coverage(),ensure_ascii=False,indent=2))"
python -c "import cache_store,json;print(json.dumps(cache_store.readiness(),ensure_ascii=False,indent=2))"
```

## 9. 疑難排解

| 症狀 | 處理方式 |
|---|---|
| `Could not import module "main"` | 目錄跑錯，`main.py` 在 `backend/` 底下 |
| `Failed to resolve import` | 前端缺檔案，確認 `src/components/` 是否完整 |
| EAP 回應 401 或 Token 失效 | Token 有效期僅 24 小時，重新取得後更新 `.env` |
| 分數異常偏低或出現負分 | `python repair_cache.py --dry` 檢視後修復 |
| 市場訊號顯示 `COMPANY_NOT_FOUND` | 把 TEJ 股價 xlsx 放入 `data/prices/`，執行 `build_market_signal.py` |
| 點進案件每次都重跑 | 確認前端有傳 `company_code`；快取鍵以證券代號為準 |
| 報告 PDF 不是標楷體 | 把 `kaiu.ttf` 複製到 `backend/fonts/`，產出時記錄檔會印出實際採用的字型 |
| PowerShell 的 `curl` 參數錯誤 | 用 `Invoke-RestMethod` 或 `curl.exe` |

### PowerShell 呼叫 API 的正確寫法

```powershell
Invoke-RestMethod -Uri http://localhost:8000/api/cache/coverage `
  -Method Post -ContentType "application/json" -Body '{}'
```

---

## 技術棧

**前端** Vue 3 · Vite 6 · Tailwind CSS 4
**後端** Python · FastAPI · httpx · Pydantic · ReportLab · SQLite
**AI** 精誠 EAP 平臺（知識圖譜 RAG）

## 授權與聲明

本專案為精誠 SEI 競賽作品。AI 輸出僅供授信人員參考，最終決策仍由審查人員為之。