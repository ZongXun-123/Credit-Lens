# 智貸先鋒 Credit-Lens

> Hybrid RAG 金融授信輔助決策系統，聚焦生技製藥產業的拜訪前情資、拜訪中提問判定與拜訪後報告生成。

Credit-Lens 將授信人員（AO）原本需要分散蒐集、人工判讀與事後整理的流程，整理成一套可稽核的 AI 情資平台。系統整合結構化財務資料與非結構化技術/新聞/法規資訊，協助授信人員更快理解企業技術量能、市場訊號與違約風險。

[系統 Demo](https://youtu.be/oNbtibC2INA)

## 專案亮點

- **拜訪前**：三位 AI Agent 分別進行財務分析、技術情報評估與風險交叉質詢，產出裁決分數與專業提問單。
- **拜訪中**：根據拜訪前風險點，即時判斷客戶回覆是否充分，並提示可延伸追問方向。
- **拜訪後**：把會議紀錄萃取成承諾事項、風險補充與覆評分數，最後產出授信報告 PDF。
- **Hybrid RAG**：結合 Graph Data 的財報/指標關聯與 Vector Data 的技術、新聞、法規脈絡。
- **可驗算評分**：財務、技術、裁決與覆評都有固定規則，避免同一案件多次執行產生不可解釋分數。

## 解決的問題

| 授信階段 | 常見痛點 | Credit-Lens 做法 |
|---|---|---|
| 拜訪前 | 生技產業資料分散，財報、許可證、新聞與技術資訊難以整合 | 跨源情資查詢、AI 審查會議、五維雷達與防禦提問單 |
| 拜訪中 | 不易即時判斷企業回答是否補足風險缺口 | 面談回答判定、追問方向提示 |
| 拜訪後 | 會議紀錄難以快速轉成可稽核的授信依據 | 紀錄萃取、覆評瀑布、PDF 報告中心 |

## 功能總覽

| 模組 | 功能 |
|---|---|
| 案件總覽 | 依素材完整度排序企業案件，快速挑選可展示或可分析標的 |
| 情資查詢 | 整合公司基本資料、月營收、藥品許可證、新聞與市場訊號 |
| AI 審查會議 | 財務 Agent、技術 Agent、風險 Agent 交叉驗證並產出裁決 |
| 拜訪前情資 | 五維雷達圖、風險摘要、建議提問項目 |
| 拜訪中與後 | 面談即時判定、會議紀錄萃取、拜訪後覆評 |
| 市場訊號 | 股價、市值與量化市場指標，搭配 EAP 交叉解讀 |
| 知識問答 | 直接與 EAP 知識圖譜自由對話 |
| 報告中心 | 產生、下載、加星與刪除授信報告 |
| Prompt / 評分說明 | 展示 Prompt 設計與授信評分邏輯 |

## 系統架構

```text
Vue 3 + Vite 前端
  案件總覽 / 案件頁 / 情資查詢 / 知識問答 / 報告中心 / Prompt 與評分說明
        |
        v
FastAPI 後端
  main.py       API 端點、評分流程、PDF 報告
  eap.py        精誠 EAP / Hybrid RAG 串接
  cache_store.py SQLite 成功結果快取
  models.py     Pydantic 資料契約
  opendata.py   商工登記與 TWSE 月營收
  tfda.py       食藥署藥品許可證
  market.py     市場訊號查詢
        |
        v
資料來源
  精誠 EAP 知識圖譜
  經濟部商工登記 API
  TWSE OpenAPI
  食藥署開放資料
  GDELT 新聞
  TEJ 股價資料（離線）
```

## 技術棧

| 層級 | 技術 |
|---|---|
| 前端 | Vue 3、Vite 6、Tailwind CSS 4 |
| 後端 | Python、FastAPI、Pydantic、httpx、ReportLab |
| 儲存 | SQLite 成功結果快取、本地 JSON 資料 |
| AI / RAG | 精誠 EAP 知識圖譜、Hybrid RAG |
| 外部資料 | 經濟部商工登記、TWSE、食藥署、GDELT、TEJ |

## 快速開始

### 前置需求

- Python 3.11+
- Node.js 18+
- 精誠 EAP 的 `EAP_TOKEN` 與 `EAP_PROJECT_ID`

> 如果只拿到已打包好的前端 `dist/`，可以不安裝 Node.js；但本專案目前是 Vue/Vite 原始碼，開發模式需要 Node.js。

### 1. 啟動後端

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
```

編輯 `backend/.env`，至少填入：

```env
EAP_TOKEN=你的_EAP_TOKEN
EAP_PROJECT_ID=你的_EAP_PROJECT_ID
```

首次執行可先建立統編與證券代號對照：

```bash
python prefetch.py
python -m uvicorn main:app --reload --port 8000
```

後端啟動後可開：

```text
http://localhost:8000
```

### 2. 啟動前端

另開一個終端機：

```bash
cd frontend
npm ci
npm run dev
```

前端預設網址：

```text
http://localhost:5173
```

### 3. 驗證環境

在 `backend/` 目錄執行：

```bash
python check_token.py
python check_sources.py 13159100
```

預期結果：

- `check_token.py` 能讀到 token 並顯示有效期限。
- `check_sources.py` 能檢查公開資料與 EAP 連線狀態。
- 前端首頁可載入案件總覽。

## 環境變數

`backend/.env.example` 是可提交版本；`backend/.env` 會被 `.gitignore` 排除，請不要上傳真實 token。

| 變數 | 預設 | 說明 |
|---|---|---|
| `EAP_API_BASE` | `https://cloud.geminidata.com/api/v1` | EAP API 位址 |
| `EAP_TOKEN` | 空 | EAP 存取權杖，有效期通常較短 |
| `EAP_PROJECT_ID` | 空 | EAP 專案識別碼 |
| `EAP_TENANT` | 空 | 留空時由 token 自動解析 |
| `EAP_DEBUG` | `false` | 是否印出 EAP 原始回應 |
| `MOCK_MODE` | `false` | 全離線示範模式 |
| `FALLBACK_ON_ERROR` | `true` | EAP 或外部資料失敗時是否降級 |
| `OPEN_DATA` | `true` | 是否啟用政府公開資料查詢 |
| `TIPO_API_KEY` | 空 | TIPO GPSS API 驗證碼；未填時只提供檢索連結 |
| `GOOGLE_PATENTS_LIVE` | `true` | 是否嘗試 Google Patents 即時查詢 |
| `ALLOW_ORIGINS` | `http://localhost:5173` | CORS 白名單 |
| `CACHE_MODE` | `record` | `off`、`record`、`replay` 三種快取模式 |

## 評分設計

Credit-Lens 的核心原則是：**分數由程式規則控制，AI 負責判斷、引用與敘述**。

| 分數 | 來源 | 設計 |
|---|---|---|
| 財務分 | EAP 財報欄位 | 90 分起算，依現金流、借款依存、流動比率、負債比率等規則扣分 |
| 技術分 | 技術情報與外部情資 | 技術門檻、定價能力、產品線動能、產業景氣四構面加總 |
| 裁決分 | 風險 Agent | 財務分 `* 0.6` + 技術分 `* 0.4`，再依交叉質詢調整 |
| 覆評分 | 拜訪後紀錄 | 依面談結果與補件承諾增減分，形成評分瀑布 |

### 防幻覺機制

1. **JSON 修復**：移除 markdown 圍欄並修補常見格式錯誤。
2. **來源檢查**：每筆發現需附 `cite`，無來源發現會被剔除。
3. **瀑布驗算**：基礎分、增減項與最終分必須一致。
4. **資料契約**：Pydantic 驗證欄位型別與範圍。

## 主要 API

### AI 分析

| Endpoint | 說明 |
|---|---|
| `POST /api/review/finance` | 財務體質分析 |
| `POST /api/review/tech` | 技術護城河與外部情資評估 |
| `POST /api/review/judge` | 財務與技術交叉質詢後裁決 |
| `POST /api/pre/brief` | 拜訪前五維雷達與提問單 |
| `POST /api/interview/assess` | 面談回答即時判定 |
| `POST /api/postvisit/extract` | 會議紀錄結構化萃取 |
| `POST /api/postvisit/score` | 拜訪後覆評與評分瀑布 |
| `POST /api/market/eap_read` | 市場指標與 EAP 交叉解讀 |
| `POST /api/eap/chat` | EAP 知識問答 |

### 查詢與管理

| Endpoint | 說明 |
|---|---|
| `POST /api/intel/lookup` | 多源情資查詢 |
| `POST /api/company/search` | 公司查詢 |
| `POST /api/market/signal` | 單一公司市場訊號 |
| `POST /api/market/universe` | 市場訊號公司清單 |
| `POST /api/report` | 產出授信報告 |
| `POST /api/reports/list` | 報告清單 |
| `POST /api/cache/coverage` | 快取素材覆蓋率 |
| `POST /api/eap/status` | EAP 連線狀態 |

## 專案結構

```text
Credit-Lens/
  backend/
    main.py              FastAPI 主程式與 API 端點
    eap.py               EAP 平台封裝與 JSON 修復
    cache_store.py       SQLite 成功結果快取
    models.py            Pydantic 資料契約
    opendata.py          商工登記、TWSE 月營收、代號對照
    tfda.py              食藥署藥品許可證查詢
    patents.py           TIPO / Google Patents 檢索輔助
    market.py            市場訊號讀取
    prompts/             AI Agent 與評分 Prompt
    data/                本地公開資料與展示素材
  frontend/
    src/
      pages/             頁面：案件、情資、問答、報告、評分說明
      components/        案件頁籤、雷達圖、瀑布圖等元件
      api.js             前端 API 呼叫層
      store.js           跨頁籤共用狀態
```

## 常用腳本

在 `backend/` 目錄執行：

| 指令 | 用途 |
|---|---|
| `python check_token.py` | 檢查 EAP token 格式與到期時間 |
| `python check_sources.py 統編` | 檢查公開資料與 EAP 連通性 |
| `python prefetch.py` | 建立統編與證券代號對照 |
| `python warmup.py --list` | 盤點各公司素材缺口 |
| `python warmup.py --all` | 批次累積成功結果快取 |
| `python curate_demo.py --dry` | 預覽展示資料品質 |
| `python repair_cache.py --dry` | 檢查快取中可修復資料 |
| `python build_market_signal.py --dry` | 由 TEJ 股價資料重建市場訊號 |

## 疑難排解

| 症狀 | 原因 | 處理方式 |
|---|---|---|
| `Could not import module "main"` | 後端啟動目錄錯誤 | 先 `cd backend` 再執行 uvicorn |
| 前端顯示無法連線後端 | FastAPI 未啟動或 port 不符 | 確認 `http://localhost:8000` 可開 |
| EAP 回應 401 | Token 失效或專案 ID 錯誤 | 更新 `backend/.env` 的 `EAP_TOKEN` 與 `EAP_PROJECT_ID` |
| 查不到公司 | `OPEN_DATA=false` 或代號/統編不符 | 確認 `.env` 與 `prefetch.py` 對照資料 |
| 市場訊號 `COMPANY_NOT_FOUND` | 缺少市場訊號資料 | 放入 TEJ 股價資料後執行 `build_market_signal.py` |
| 報告 PDF 字型異常 | 找不到中文字型 | 確認 `backend/fonts/` 內有可用中文字型 |
| 現場 Demo 怕外部服務不穩 | EAP 或公開資料可能逾時 | 事前跑 `warmup.py`，展示時將 `CACHE_MODE` 改成 `replay` |

## GitHub 上傳注意事項

請確認下列檔案不要推上公開 repo：

- `backend/.env`
- `frontend/node_modules/`
- `backend/data/*.db`
- `backend/reports/`
- `backend/data/eap_exports/`
- Office 文件匯出檔，例如 `.docx`、`.xlsx`、`.pptx`

目前根目錄 `.gitignore` 已排除上述常見敏感檔與產物。

## 團隊與來源

本專案為精誠 SEI 競賽作品。  
資料來源包含 TEJ 財金資料庫、工研院產科國際所、公司法說會、衛福部食藥署、經濟部商工登記、TWSE 與 GDELT 等。

## 聲明

Credit-Lens 是授信決策輔助工具，AI 輸出僅供授信人員參考。最終授信決策仍應由具權責人員依內部規範、完整文件與實際徵審流程判斷。
