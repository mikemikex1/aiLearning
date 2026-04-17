# A — Browser & RAG Agent 交接與驗證報告

更新日期：2026-04-16  
範圍：僅 A 功能（文章抓取 → 清洗 → Parent-Document Retrieval 入庫 → 檢索）

## 1) A 功能目標

每日自動抓取 AI 相關文章，清理內容後切分 parent/child chunks，寫入 ChromaDB，供 Search Agent 後續檢索。

---

## 2) 主要檔案與重要函式

- `src/agents/browser_rag.py`
  - `run_daily_ingest()`：A 流程主入口（載入關鍵字、抓資料、清洗、入庫）
  - `clean_text(raw)`：呼叫 LLM 做內容清洗（失敗時回退原文前 4000 字）

- `src/sources/collectors.py`
  - `collect_all(keywords)`：抓取所有已啟用來源，寫入 `data/raw/YYYY-MM-DD/collected_*.json`
  - `fetch_rss(name, url)`：RSS 拉取
  - `fetch_hn()`：Hacker News API 拉取
  - `_keyword_match()`：關鍵字過濾

- `src/rag/parent_retriever.py`
  - `ingest(docs)`：寫入 `parents` / `children` collections
  - `retrieve(query, k)`：向量查詢 child，再回 parent 內容
  - `_split_parent()` / `_split_child()`：chunk 切分

- `config/settings.py`
  - `EMBEDDING_MODEL`：目前設定 `text-embedding-004`
  - `load_keywords()` / `enabled_feeds()` / `feed_keywords()`：A 功能的重要設定入口

---

## 3) 本次驗證方式（2026-04-16）

### Step A-1：前置檢查
- 檢查 `.venv` 可用、`GOOGLE_API_KEY` 存在。
- 結果：`GOOGLE_API_KEY` 存在（長度 39）。

### Step A-2：來源可連線與抓取數量
- 實測 `fetch_rss` / `fetch_hn` 各來源筆數。
- 結果：
  - `arxiv_cs_ai`: 30
  - `simonw`: 30
  - `hn`: 20
  - `hf_papers`: 0（HTTP 401）

### Step A-3：raw 檔寫入驗證（collect_all）
- 不加 `PYTHONUTF8=1` 執行 `collect_all([])`。
- 結果：失敗，`UnicodeEncodeError: 'cp950' codec can't encode character ...`
- 加 `PYTHONUTF8=1` 再跑。
- 結果：成功，產出：
  - `data/raw/2026-04-16/collected_20260416T090902640426Z.json`
  - `item_count=80`，`source_count=3`（`hf_papers` 未提供資料）

### Step A-4：Cleaner 驗證
- 實測 `clean_text("This is <b>test</b> ...")`
- 結果：成功，輸出已去除 HTML 標記。

### Step A-5：RAG 入庫與檢索驗證
- 以 3 篇文章做小樣本 `ingest(docs)` 與 `retrieve(...)`。
- 結果：失敗，`GoogleGenerativeAIError`（404）
  - 訊息：`models/text-embedding-004 is not found for API version v1beta...`
- 同樣 `retrieve('RAG')` 直接驗證也失敗（同一錯誤）。

---

## 4) 可用 / 不可用 功能清單（A）

## 可用
- 來源抓取（arXiv / Simon Willison / HN）可成功取得資料。
- LLM 清洗 `clean_text()` 可運作。
- `collect_all()` 的資料結構正確（含 `description`, `fetched_at`, `items`）。

## 不可用（阻塞）
- Parent-Document Retrieval 入庫與查詢目前不可用。
  - 根因：`EMBEDDING_MODEL=text-embedding-004` 對目前 API 版本回 404。
  - 影響：`ingest()`、`retrieve()`、`search_agent.answer()` 的 RAG 路徑都會失敗。

- `collect_all()` 在 Windows cp950 環境可能直接失敗。
  - 根因：`write_text()` 未指定 `encoding='utf-8'`。
  - 影響：只要抓到不可編碼字元就無法落盤，排程中斷。

- `hf_papers` 來源目前抓不到資料。
  - 根因：RSS 回 401（來源端策略/URL 變動）。
  - 影響：此來源長期為 0 筆。

---

## 5) 維護與日常巡檢 SOP（A）

### 每日巡檢
1. 檢查 `data/raw/<today>/collected.json` 是否更新。
2. 檢查欄位：`item_count`、`source_count`、`fetched_at`。
3. 抽查 `items` 的 `title/link/source` 是否合理。
4. 執行一次 `retrieve("RAG", k=3)` 檢查檢索是否可用。
5. 若失敗，先看 embedding model 與 API 錯誤碼。

### 問題定位優先順序
1. 先修 `EMBEDDING_MODEL` 404（否則整個 RAG 不可用）。
2. 再修 `collect_all` UTF-8 寫檔（避免每日任務不穩定）。
3. 最後處理 `hf_papers` 來源替代或驗證新 URL。

---

## 6) 建議修復項（依優先級）

### P0（先做）
- `config/settings.py`：更新 `EMBEDDING_MODEL` 為目前 API 可用模型。
- `src/sources/collectors.py`：所有 `write_text(...)` 明確指定 `encoding='utf-8'`。

### P1
- `src/sources/collectors.py`：為每個 feed 記錄錯誤原因（目前 `fetch_hn()` 直接吞例外）。
- `hf_papers`：驗證新 RSS endpoint 或新增 fallback source。

---

## 7) 驗證指令（可直接重跑）

```powershell
# 1) 檢查 key
.\.venv\Scripts\python -c "from config.settings import get_api_key; k=get_api_key(); print(bool(k), len(k))"

# 2) 各來源抓取數
.\.venv\Scripts\python -c "from src.sources.collectors import fetch_rss, fetch_hn, FEEDS; print({k:len(fetch_rss(k,v)) for k,v in FEEDS.items()} | {'hn':len(fetch_hn())})"

# 3) collect_all (建議加 UTF-8)
$env:PYTHONUTF8='1'
.\.venv\Scripts\python -c "from src.sources.collectors import collect_all; p=collect_all([]); print(p)"

# 4) Cleaner
.\.venv\Scripts\python -c "from src.agents.browser_rag import clean_text; print(clean_text('This is <b>test</b> about RAG'))"

# 5) Retrieval 健康檢查
.\.venv\Scripts\python -c "from src.rag.parent_retriever import retrieve; print(retrieve('RAG',k=2))"
```

---

## 8) 修復紀錄（2026-04-16）

已完成修復：
- `config/settings.py`
  - `EMBEDDING_MODEL: text-embedding-004 -> gemini-embedding-001`
- `src/sources/collectors.py`
  - `write_text()` 全部改為 `encoding='utf-8'`
  - `description.sources` 改為只列出有抓到資料的來源
- `src/agents/browser_rag.py`
  - 讀 raw JSON 時改為 `read_text(encoding='utf-8')`

修復後驗證結果：
- `collect_all([])`：成功（不再出現 cp950 `UnicodeEncodeError`）
- 小樣本入庫：`ingested_parents = 2`
- 檢索：`retrieve_hits = 2`
- Search Agent：可回答且附來源（`sources = 2`）

`hf_papers` 修復：
- 原 `https://huggingface.co/papers/rss` 回 401，已改為 `https://huggingface.co/api/daily_papers`。
- 修復後驗證：`hf_papers = 30`，`collect_all` 來源恢復為 4 個（含 hf_papers）。
