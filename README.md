# AI Learning — Phase 1 Design Document

> Agentic RAG workflow that turns AI-trend information anxiety into running code.
> Daily fetch → semantic chunking → RAG → Agent team generates runnable Terminal code + stress-test reports.

---

## 1. Model Selection (verified April 2026)

As of April 2026, Google restructured the Gemini free tier: **Gemini 2.5 Pro is paywalled** for free users; only **Flash** and **Flash-Lite** remain free. "Gemini 3.1" is not a real product — the current generation is Gemini 2.5. This document uses verified model names.

| Role | Model | Why | Free Tier Limits |
|---|---|---|---|
| Browser / Cleaner | `gemini-2.5-flash-lite` | Highest RPM, cheapest reasoning, good enough to strip HTML noise and tag content | 15 RPM · 1,000 RPD · 1M context |
| Planner | `gemini-2.5-flash` | Stronger reasoning for blueprint decomposition; 1M context consumes long RAG chunks | 10 RPM · 250 RPD · 1M context |
| Programmer | `gemini-2.5-flash` | Same as Planner — consistent model avoids style drift between plan & code | shared pool |
| Tester | `gemini-2.5-flash` | Edge-case reasoning for stability tests | shared pool |
| Search Agent | `gemini-2.5-flash-lite` → escalate to `flash` | Routing: lite answers short queries, flash handles synthesis | both |
| Embedding | `text-embedding-004` | Free, native Gemini compatibility, 768-dim | generous |

All free tiers share a 250k TPM ceiling and the full 1M-token context window.

### Model Routing Rule (`src/models/router.py`)
```
simple task (clean HTML, short Q&A, tag)    → flash-lite
complex task (plan, code, test, synthesize) → flash
fallback on 429                             → exponential backoff + downgrade to lite
```

---

## 2. Architecture (Three Pillars)

```
┌──────────────────────────────────────────────────────────┐
│  Streamlit UI  (sidebar: Settings / Search / Project /   │
│                 Raw Source / News)                       │
└───────────────┬──────────────────────────────────────────┘
                │
    ┌───────────┴───────────┬──────────────────────┐
    ▼                       ▼                      ▼
┌─────────────┐    ┌──────────────────┐    ┌──────────────┐
│ Browser &   │    │ Code Team        │    │ Search Agent │
│ RAG Agent   │───▶│ (Plan→Prog→Test) │◀───│              │
└──────┬──────┘    └──────────────────┘    └──────┬───────┘
       │                                          │
       ▼                                          ▼
┌──────────────────────────────────────────────────────────┐
│  ChromaDB (Parent-Document Retrieval) + data/raw/*.json  │
└──────────────────────────────────────────────────────────┘
       │
       ▼  LangSmith traces everything
```

### A. Browser & RAG Agent
- **Sources (Twitter alternatives):** arXiv cs.AI RSS, Hacker News front-page, Papers With Code, Hugging Face daily papers, The Batch, Simon Willison's blog, Latent Space RSS.
- **Flow:** fetch → persist raw JSON under `data/raw/YYYY-MM-DD/` → Flash-Lite cleaner strips boilerplate → **semantic chunking** (embedding-based breakpoint) → **Parent-Document Retrieval** (child = small chunk indexed, parent = full section returned).
- **Keyword management:** stored in `config/keywords.json`, editable from the Settings page; same store reused by Search page.

### B. Code Team (Sequential LangGraph)
```
START → planner → [INTERRUPT: human approves blueprint.json] → programmer → tester → report → END
```
- **Planner** outputs strict `blueprint.json` (validated with Pydantic).
- **Programmer** generates a single-file `main.py` targeting the blueprint.
- **Tester** runs stability checks: empty input, oversized input, None, API failure mock, timeout. Produces `stability_report.md`.

### C. Search Agent
Consults: RAG store + generated projects (`README.md`, `blueprint.json`, stability reports). LLM re-writes results into learning material. Surfaced via the Search page.

---

## 3. Data Contracts

### `blueprint.json` (Planner output)
```json
{
  "project_id": "string",
  "title": "string",
  "topic": "string",
  "objective": "string",
  "tech_stack": ["python", "..."],
  "modules": [
    { "name": "fetcher", "responsibility": "...", "inputs": [], "outputs": [] }
  ],
  "entrypoint": "main.py",
  "cli_args": [{"name": "--topic", "type": "str", "required": true}],
  "edge_cases": ["empty input", "network 500"],
  "success_criteria": ["runs without traceback", "handles None"]
}
```

### `error_log.json` (append-only)
```json
{
  "timestamp": "2026-04-14T12:00:00+08:00",
  "code": "LLM_JSON_ERROR | RETRIEVAL_MISS | RUNTIME_FAIL",
  "module": "planner",
  "message": "string",
  "context": { "input_preview": "...", "model": "gemini-2.5-flash" },
  "recovery_suggestion": "string  (auto-generated by Gemini)"
}
```

---

## 4. Observability & Cost Control
- **LangSmith:** `LANGCHAIN_TRACING_V2=true` + project name `ai-learning-phase1`.
- **Model Router** logs every call with `(task, model, tokens_in, tokens_out, latency)`.
- **Human-in-the-loop:** LangGraph `interrupt_before=["programmer"]` — the Project page renders the blueprint for the user to edit & approve before code is generated.

---

## 5. UI Pages

| Page | Purpose |
|---|---|
| Settings | API keys (masked input), keyword manager, model-routing toggles |
| Search | Chat window over RAG + generated projects |
| Project | Click a topic → run Code Team pipeline → view code/report |
| Raw Source | Browse/search everything under `data/raw/` |
| News | Daily top-3 (auto-curated by Browser Agent), plus archive search |

---

## 6. Tech Stack

- Python 3.10+
- `streamlit` (UI), `fastapi` (optional API layer for batch jobs)
- `langgraph`, `langchain`, `langchain-google-genai`
- `chromadb` (local vector store)
- `feedparser`, `httpx`, `beautifulsoup4` (source collectors)
- `pydantic` (schema validation)
- `langsmith` (tracing)

---

## 7. Phase-1 Build Order

1. ✅ Design doc (this file)
2. Project scaffold + config + schemas
3. Streamlit sidebar UI (5 pages)
4. Browser & RAG Agent (collectors → cleaner → chunker → parent retriever)
5. Code Team LangGraph pipeline with HITL interrupt
6. Search Agent wiring
7. End-to-end smoke test

---

## 8. FastAPI Batch Layer

Headless HTTP layer over the same LangGraph pipeline — use it from cron, curl, or any other client.

```bash
# from the project root
python run_api.py
# or:  uvicorn api.main:app --reload --port 8000
```

| Method | Path | Body | Purpose |
|---|---|---|---|
| GET | `/health` | — | Liveness + current model routing |
| POST | `/ingest` | — | Run the daily Browser/RAG ingest |
| POST | `/search` | `{"query": "...", "k": 4}` | RAG Q&A with citations |
| POST | `/plan` | `{"topic": "..."}` | Planner only → `blueprint.json` |
| POST | `/build` | `{"topic": "...", "blueprint": {...}?}` | Full Planner→Programmer→Tester run |
| GET | `/errors?limit=50` | — | Tail of `data/logs/error_log.json` |

Examples:
```bash
curl http://127.0.0.1:8000/health

curl -X POST http://127.0.0.1:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "what is parent-document retrieval?"}'

curl -X POST http://127.0.0.1:8000/plan \
  -H "Content-Type: application/json" \
  -d '{"topic": "LangGraph HITL interrupts"}'
```

The API uses a **non-interactive** variant of the Code Team graph (`build_graph_headless`); the Streamlit UI keeps the HITL-interrupted variant. Pass an `approved_blueprint` to `/build` to skip the planner.

---

Sources:
- [Gemini API Rate Limits (official)](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Gemini API Free Tier 2026 Guide](https://www.aifreeapi.com/en/posts/gemini-api-free-tier-rate-limits)
- [Gemini API Pricing April 2026](https://findskill.ai/blog/gemini-api-pricing-guide/)

---

## Maintenance Rule

For every code/config/behavior change, update documentation in the same commit:

1. Update `README.md`
2. Update handover document(s), at minimum:
   - `A_BROWSER_RAG_VALIDATION_HANDOVER.md`

## Search Suggestion Source Rule

Search quick suggestions must be generated from **indexed RAG content only**
(Chroma `parents` collection), not directly from raw files.

This prevents suggestion items from pointing to articles that were fetched into
`data/raw/` but failed to enter vector storage.

## Follow-up Query Handling

Short follow-up queries (for example: "想知道更多", "more", "continue")
are automatically expanded with recent user turns before retrieval.

If cloud generation returns an "insufficient context" style template while
retrieval has already returned chunks, the UI now falls back to a local
structured summary from retrieved context instead of a blank/blocked answer.

## Search UI Interaction Rule (2026-04-17)

Search page interaction now follows these constraints:

1. Suggestions are rendered inside the chat area, above the input box.
2. Suggestions are shown as three vertical buttons (title only, no prefix text).
3. When user clicks a suggestion or sends a message:
   - suggestion list hides immediately;
   - send and suggestion actions are disabled until reply is done.
4. After assistant reply finishes, system regenerates exactly three new suggestions.
5. Suggestion/answer language is resolved from recent user message first, then falls back to global locale setting.

## Git One-Command Script

Use `git_sync.ps1` to reduce repetitive git commands.

Examples:

```powershell
.\git_sync.ps1 -Action "search page ui update"
.\git_sync.ps1 -Action "docs sync" -Files README.md,A_BROWSER_RAG_VALIDATION_HANDOVER.md
.\git_sync.ps1 -Action "local check" -NoPush
```

Rules:
- If message has no prefix, script auto-converts to `refator: <action>`.
- Default staging excludes `data/`, `.venv/`, and `__pycache__/`.
- Use `-IncludeAll` if you really need full `git add -A`.

## Commit Type Convention Update (2026-04-17)

Commit messages no longer default to `refator:`.

Use:

`<type>: <Action>`

Common types:
- `debug` for bug fixes
- `add` for new features
- `edit` for modifying existing behavior
- `docs`, `chore`, `test`, `perf`, `refactor` for their respective scopes

`git_sync.ps1` now supports `-Type` and defaults to `edit`.

Examples:
```powershell
.\git_sync.ps1 -Type add -Action "search ui quick suggestions"
.\git_sync.ps1 -Type debug -Action "fix cloud retry fallback"
.\git_sync.ps1 -Type edit -Action "update handover wording"
```

## Search Language Auto-Detection + Product Skill (2026-04-17)

Search response language now follows user input language first:
- If user input is Chinese, answer in Traditional Chinese.
- If user input is English, answer in English.
- If ambiguous, fallback to current UI locale.

A product navigation skill is now injected into Search LLM prompts, so the assistant can reliably answer app usage questions such as:
- where to set API keys
- where to see latest updates
- where to inspect raw collected items
- where to ask RAG questions
- where to generate runnable projects

Skill source:
- `src/agents/product_skill.py`

Page mapping used by the skill:
1. Settings -> API keys / keywords / routing / feed toggles
2. News -> latest daily Top-3 highlights
3. Raw Source -> ingest + raw article verification
4. Search -> RAG Q&A with citations
5. Project -> Planner/Programmer/Tester pipeline
