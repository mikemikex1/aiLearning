"""Product-level navigation skill shared by Search agent."""
from __future__ import annotations


def product_skill_text(locale: str) -> str:
    if locale == "zh-TW":
        return (
            "【AI Learning 系統導覽 Skill】\n"
            "1) Settings 頁面\n"
            "- 用途: 設定 GOOGLE_API_KEY / LANGCHAIN_API_KEY、關鍵字、模型路由、來源開關。\n"
            "- 需要設定 API Key 時，請引導使用者到 Settings。\n\n"
            "2) Raw Source 頁面\n"
            "- 用途: 手動觸發每日 ingest，並檢視抓取的原始文章。\n"
            "- 要確認資料有沒有抓到、抓到哪些來源時，請引導到 Raw Source。\n\n"
            "3) News 頁面\n"
            "- 用途: 以每日資料挑選 Top-3 重點，快速看最新摘要。\n"
            "- 要看最新重點資訊時，優先引導到 News。\n\n"
            "4) Search 頁面\n"
            "- 用途: 對已索引 RAG 內容進行問答，附來源。\n"
            "- 適合深入追問、比較、整理與引用來源。\n\n"
            "5) Project 頁面\n"
            "- 用途: Planner -> Programmer -> Tester 的專案生成流程。\n"
            "- 適合把技術主題轉成可執行專案與測試報告。\n"
        )
    return (
        "[AI Learning Product Navigation Skill]\n"
        "1) Settings\n"
        "- Purpose: configure GOOGLE_API_KEY / LANGCHAIN_API_KEY, keywords, model routing, feed switches.\n"
        "- If user asks where to set API keys, direct to Settings.\n\n"
        "2) Raw Source\n"
        "- Purpose: trigger daily ingest manually and inspect fetched raw articles.\n"
        "- For verifying collection status/sources, direct to Raw Source.\n\n"
        "3) News\n"
        "- Purpose: curate daily Top-3 highlights from collected data.\n"
        "- For latest high-level updates, direct to News first.\n\n"
        "4) Search\n"
        "- Purpose: question-answering over indexed RAG with citations.\n"
        "- Best for deep follow-up and source-grounded answers.\n\n"
        "5) Project\n"
        "- Purpose: Planner -> Programmer -> Tester project generation.\n"
        "- Best for turning topics into runnable code + stability report.\n"
    )


def local_app_navigation_answer(locale: str) -> str:
    if locale == "zh-TW":
        return (
            "你可以這樣用：\n"
            "1. 設定 API Key: 到 Settings 頁面。\n"
            "2. 看最新重點: 到 News 頁面（每日 Top-3）。\n"
            "3. 驗證原始抓取: 到 Raw Source 頁面。\n"
            "4. 針對內容提問: 到 Search 頁面。\n"
            "5. 生成專案與測試: 到 Project 頁面。"
        )
    return (
        "Use the app this way:\n"
        "1. Set API keys: Settings page.\n"
        "2. See latest highlights: News page (daily Top-3).\n"
        "3. Verify raw collection: Raw Source page.\n"
        "4. Ask grounded questions: Search page.\n"
        "5. Build runnable projects/tests: Project page."
    )


def is_app_navigation_query(query: str) -> bool:
    q = (query or "").lower()
    if not q:
        return False
    keywords = [
        "api key",
        "apikey",
        "settings",
        "最新",
        "news",
        "raw",
        "搜尋",
        "search",
        "project",
        "頁面",
        "去哪",
        "where",
    ]
    return any(k in q for k in keywords)
