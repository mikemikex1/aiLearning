# AI Learning Phase 1 — 交接文件

> 給接手的 Claude Code / VS Code Agent  
> 日期：2026-04-15  
> 專案路徑：`C:\Users\Daming\Documents\AILearning`  
> GitHub：`git@github.com:mikemikex1/aiLearning.git`

---

## 1. 專案概要

這是一個「AI 趨勢自動學習系統」，三大支柱：

| 支柱 | 功能 | 核心模組 |
|------|------|----------|
| A — Browser & RAG Agent | 每日自動抓取 AI 相關文章，以 Parent-Document Retrieval 存入 ChromaDB | `src/agents/browser_rag.py`, `src/sources/collectors.py`, `src/rag/parent_retriever.py` |
| B — Code Team (LangGraph) | Planner → Programmer → Tester 流水線，有 HITL interrupt 等人工審核藍圖 | `src/agents/code_team.py` |
| C — Search Agent | RAG-backed Q&A，附帶結構化引用來源 | `src/agents/search_agent.py` |

**UI**：Streamlit 多頁面 app（`app.py` + `pages/`）  
**API**：FastAPI headless 層（`api/main.py`）  
**排程**：Cowork 每天 08:00 local time 自動執行 ingest

---

## 2. 技術棧

```
Python 3.13
Streamlit          — UI
FastAPI + Uvicorn  — REST API
LangGraph          — 狀態機 / HITL
LangChain          — LLM 抽象層
ChromaDB           — 向量資料庫（local persistent）
Google Gemini      — LLM（免費層）
feedparser / httpx — RSS 抓取
LangSmith          — (已設欄位，尚未接線)
```

---

## 3. 目錄結構

```
AILearning/
├── app.py                         # Streamlit 主進入點
├── run_api.py                     # uvicorn 啟動器
├── smoke_test.py                  # 離線 smoke test（stub 所有重外部依賴）
├── requirements.txt
├── git_sync.ps1                   # 本機一鍵 git commit + push
├── .env / .env.example
│
├── config/
│   ├── settings.py                # 全域設定、MODEL_LITE/FLASH 常數、所有 load/save 函式
│   ├── keywords.json              # 全域過濾關鍵字
│   └── user_settings.json         # routing + feeds + per-source 關鍵字覆寫
│
├── pages/
│   ├── 1_Settings.py              # API keys、關鍵字、Model routing、Source feeds 開關
│   ├── 2_Search.py                # RAG Q&A 對話 + 引用來源
│   ├── 3_Project.py               # Plan → Approve → Build，CLI 執行，ZIP 下載
│   ├── 4_Raw_Source.py            # 手動觸發 ingest，查看 collected.json
│   └── 5_News.py                  # 快取 Top-3 + Atom feed 下載 + 關鍵字搜尋
│
├── api/
│   └── main.py                    # FastAPI endpoints（見第 7 節）
│
├── src/
│   ├── agents/
│   │   ├── browser_rag.py         # run_daily_ingest()
│   │   ├── code_team.py           # LangGraph 圖，build_graph() / build_graph_headless()
│   │   ├── news_curator.py        # pick_top3(), load_top3(), list_all_top3()
│   │   ├── news_feed.py           # export_atom()
│   │   └── search_agent.py        # answer(query, history, k) → {answer, sources}
│   ├── models/
│   │   └── router.py              # pick_model(), call_with_fallback()
│   ├── rag/
│   │   ├── parent_retriever.py    # ingest(), retrieve()
│   │   └── project_indexer.py     # index_project(project_dir)
│   ├── schemas/
│   │   ├── blueprint.py           # Blueprint pydantic model
│   │   └── error_log.py           # ErrorEntry, log_error(), read_errors()
│   ├── sources/
│   │   └── collectors.py          # collect_all(keywords), fetch_rss(), fetch_hn()
│   └── utils/
│       ├── error_handler.py       # record() — 統一寫入 error_log.json
│       ├── runner.py              # run_project() → RunResult
│       └── zipper.py              # zip_project() → bytes
│
└── data/                          # runtime 資料（.gitignore 中）
    ├── chroma/                    # ChromaDB persistent store
    ├── logs/error_log.json
    ├── projects/<project_id>/     # 產生的程式碼專案
    └── raw/<YYYY-MM-DD>/
        ├── collected_<timestampZ>.json   # 抓取快照（含 timestampz）
        ├── collected.json                # 最新抓取的指標檔
        └── top3.json                     # LLM 選出的每日 Top-3 快取
```

---

## 4. 環境變數

`.env` 放在專案根目錄：

```dotenv
GOOGLE_API_KEY=你的金鑰
LANGCHAIN_API_KEY=你的金鑰（LangSmith，選填）
LANGCHAIN_TRACING_V2=true          # 開啟後 LangSmith 自動追蹤
LANGCHAIN_PROJECT=ailearning-phase1
```

---

## 5. 啟動方式

```powershell
# 安裝依賴（.venv 已存在，直接啟用）
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Streamlit UI
streamlit run app.py

# FastAPI（另開 terminal）
python run_api.py
# 或
uvicorn api.main:app --reload --port 8000

# Smoke test（不需 API key）
python smoke_test.py
```

---

## 6. 模型路由（重要）

| 任務 | 模型 | 免費限額 |
|------|------|----------|
| simple（清理、短 Q&A） | `gemini-2.5-flash-lite` | 15 RPM / 1,000 RPD |
| complex（規劃、程式碼、測試） | `gemini-2.5-flash` | 10 RPM / 250 RPD |
| embedding | `text-embedding-004` | 1,500 RPM |

> **注意**：Gemini Pro 在 2026 年 4 月已改為付費。Flash / Flash-Lite 仍維持免費層。  
> 設定儲存在 `config/user_settings.json`，Settings 頁可即時修改，router.py 每次 call 都重新讀取，不需重啟。

`router.py` 邏輯：
- 遇 429 / quota exceeded → exponential backoff（最多 3 次）
- `downgrade_on_429=True` → 第 2 次重試自動降為 simple model

---

## 7. FastAPI Endpoints

| Method | Path | 說明 |
|--------|------|------|
| GET | `/health` | liveness + 目前模型設定 |
| POST | `/ingest` | 觸發 browser_rag ingest |
| POST | `/search` | `{query, k}` → `{answer, sources}` |
| POST | `/plan` | `{topic}` → `{blueprint}` |
| POST | `/build` | `{topic, blueprint?}` → `{blueprint, project_dir, code_preview, ...}` |
| GET | `/news/top3?date=YYYY-MM-DD&force=bool` | 取得（或重新選）Top-3 |
| GET | `/news/atom?limit=30` | Atom 1.0 XML feed |
| GET | `/news/archive` | 所有日期的 Top-3 快取清單 |
| GET | `/errors?limit=50` | 結構化 error_log 尾部 |

---

## 8. 資料 Schema

### collected.json（`data/raw/<date>/collected_<timestampZ>.json`）

```json
{
  "description": "AILearning daily fetch — fetched_at=2026-04-15T05:00:00Z sources=[arxiv_cs_ai, hn, ...]",
  "items": [
    {
      "source": "arxiv_cs_ai",
      "title": "...",
      "summary": "...",
      "link": "...",
      "published": "...",
      "fetched_at": "2026-04-15T05:00:00Z"
    }
  ]
}
```

> `fetched_at` 在每個 item 和 description header 都有記錄（timestampz 規則）。

### top3.json（`data/raw/<date>/top3.json`）

```json
{
  "date": "2026-04-15",
  "picked_at": "2026-04-15T06:00:00Z",
  "model": "complex",
  "picks": [
    {"rank": 1, "title": "...", "link": "...", "justification": "一句話說明"},
    {"rank": 2, "title": "...", "link": "...", "justification": "..."},
    {"rank": 3, "title": "...", "link": "...", "justification": "..."}
  ]
}
```

### error_log.json（`data/logs/error_log.json`）

JSONL 格式，每行一筆：

```json
{"code": "LLM_JSON_ERROR", "module": "news_curator.pick_top3", "message": "...", "context": {}, "ts": "2026-04-15T05:00:00Z", "recovery_suggestion": ""}
```

> `recovery_suggestion` 欄位預留，目前為空（見第 10 節待辦）。

### blueprint.json（`data/projects/<id>/blueprint.json`）

```json
{
  "project_id": "uuid",
  "title": "...",
  "topic": "...",
  "objective": "...",
  "tech_stack": ["python"],
  "modules": [{"name": "...", "responsibility": "...", "inputs": [], "outputs": []}],
  "entrypoint": "main.py",
  "cli_args": [],
  "edge_cases": [],
  "success_criteria": []
}
```

---

## 9. LangGraph Code Team 架構

```
[START] → planner_node → [interrupt_before=programmer] → programmer_node → tester_node → [END]
```

- `build_graph()` — 有 interrupt，Streamlit 用（UI 需展示藍圖讓使用者批准）
- `build_graph_headless()` — 無 interrupt，API `/build` 用
- `run_planner_only(topic)` — 只跑 planner，回傳 blueprint dict
- `run_pipeline(topic, approved_blueprint=None)` — 完整流水線
- `tester_node` 產生 stability_report 後會自動呼叫 `index_project()` 把結果存入 ChromaDB，讓未來的 Search Agent 可以查到歷史專案

**State schema**（`TypedDict`）：
```python
{
  "topic": str,
  "blueprint": dict | None,
  "code": str | None,
  "stability_report": str | None,
  "project_dir": str | None,
}
```

---

## 10. 尚未完成的功能（Phase 1 收尾）

### 10.1 LangSmith 追蹤整合 ⚡ 建議優先
- 狀態：`.env` 有設欄位，但 `router.py` 還沒加 `with_config({"callbacks": [...]})`  
- 做法：只需在 `router.py` 的 `make_llm()` 加上 LangSmith callback，Settings 頁有 `LANGCHAIN_API_KEY` 輸入框  
- 參考：`langchain.callbacks.LangChainTracer`

### 10.2 Gemini 自動錯誤恢復建議 ⚡ 建議優先
- 狀態：`error_log.py` 的 `ErrorEntry` 有 `recovery_suggestion: str = ""` 欄位，但從未填入  
- 做法：在 `error_handler.record()` 之後，呼叫 Flash-Lite 產生一句建議，寫回 JSON  
- 注意：避免無限遞迴（錯誤建議本身失敗不能再觸發）

### 10.3 `/ingest` 背景化
- 狀態：目前 POST /ingest 是同步阻塞，ingest 通常 10–30 秒，HTTP timeout 風險  
- 做法：改用 FastAPI `BackgroundTasks`，回傳 `{"job_id": "..."}`, 新增 `GET /ingest/status/{job_id}`

### 10.4 Search 頁引用來源展開
- 狀態：sources panel 顯示 snippet，沒辦法展開完整 parent chunk  
- 做法：在 `search_agent.answer()` 回傳值加 `"parent_text"` 欄位，Search 頁加 expander

### 10.5 Project 頁多版本比對
- 狀態：同一 topic 多次 build 只保留最新  
- 做法：`project_dir` 命名加時間戳，Project 頁加 selectbox 比對兩次產物

---

## 11. 長期規則（Standing Instructions）

1. **每次任務完成後 git commit + push**  
   在使用者的 Windows 機器上執行：
   ```powershell
   .\git_sync.ps1 "feat: <描述>"
   ```
   （sandbox 無法執行 git，因為 Windows mount 的 .git/config 有 Windows 換行問題）

2. **Raw source 檔案必須在 description 記錄 timestampz**  
   `collected.json` 的 `description` 欄位格式：
   ```
   AILearning daily fetch — fetched_at=<RFC3339 with Z suffix> sources=[...]
   ```
   每個 item 也有 `fetched_at` 欄位。

3. **時間戳格式統一用 UTC + Z suffix**  
   `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")`

---

## 12. 已知限制

| 問題 | 說明 |
|------|------|
| pip install 受阻 | Sandbox 的 pypi proxy 返回 403；改法是在使用者本機跑 pip |
| git 無法從 sandbox 推送 | Windows mount 的 .git/config 有 line ending 問題 + 沒 SSH key |
| Gemini 免費層 RPD 限制 | Flash 250 RPD，Code Team 建議白天少用，留給 ingest + news |
| ChromaDB 是 local file | 多 process 同時寫入會衝突；Streamlit + API 同時跑時避免同時 ingest |

---

## 13. Smoke Test

```powershell
python smoke_test.py
```

全部 stub 外部依賴（pydantic、langchain_google_genai、chromadb、feedparser、httpx、fastapi、langgraph）。  
涵蓋：router、settings round-trip、collectors、Blueprint schema、error_log、parent_retriever、code_team graph、runner（含 timeout）、search agent、project indexer、FastAPI 所有 endpoint、**news curator + atom feed**。

預期最後一行：`✅ SMOKE TEST PASSED`

---

## 14. Source Feeds 說明

| ID | 來源 | 抓取方式 |
|----|------|----------|
| `arxiv_cs_ai` | arXiv cs.AI RSS | `feedparser` |
| `simonw` | Simon Willison's blog | `feedparser` |
| `hf_papers` | Hugging Face daily papers | `feedparser` |
| `hn` | Hacker News front page | httpx → HN Algolia API |

> Twitter/X 已刪除（scraping 違反 ToS）。  
> 新增來源：在 `config/settings.py` 的 `FEED_CATALOG` 加 id，在 `collectors.py` 加對應抓取邏輯。

---

## 15. 快速驗證清單（接手後第一步）

- [ ] `.env` 填入真實 `GOOGLE_API_KEY`
- [ ] `python smoke_test.py` → `✅ SMOKE TEST PASSED`
- [ ] `streamlit run app.py` 啟動，確認 5 個頁面都可打開
- [ ] Settings 頁存一次設定（確認 `config/user_settings.json` 寫入）
- [ ] Raw Source 頁手動跑一次 ingest（需要 API key）
- [ ] News 頁選今天日期，點 "Pick top 3"（需要 API key + ingest 資料）
- [ ] `python run_api.py` + `curl http://localhost:8000/health`

---

*文件由 Claude (Cowork) 自動產生 · 2026-04-15*
