"""Offline smoke test — stubs external libs, verifies wiring.

Run: python smoke_test.py
Exits 0 on success. Does NOT need real API keys or network.
"""
import sys, types, json, importlib, pathlib

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ---------- 1. Stub heavyweight external libs ----------
def _stub(name, attrs=None):
    m = types.ModuleType(name)
    for k, v in (attrs or {}).items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m

# pydantic: use real if possible, else minimal stub
try:
    import pydantic  # noqa
except ImportError:
    class _BM:
        def __init__(self, **kw):
            for k, v in kw.items(): setattr(self, k, v)
        def model_dump(self): return self.__dict__
        def model_dump_json(self): return json.dumps(self.__dict__, default=str)
    def Field(default=None, default_factory=None, **kw):
        return default_factory() if default_factory else default
    _stub("pydantic", {"BaseModel": _BM, "Field": Field})

# langchain_google_genai
class _FakeLLM:
    def __init__(self, **kw): self.kw = kw
    def invoke(self, prompt):
        r = types.SimpleNamespace()
        r.content = '{"project_id":"x1","title":"t","topic":"demo","objective":"o",' \
                    '"tech_stack":["python"],"modules":[{"name":"m","responsibility":"r",' \
                    '"inputs":[],"outputs":[]}],"entrypoint":"main.py","cli_args":[],' \
                    '"edge_cases":[],"success_criteria":[]}'
        return r
class _FakeEmb:
    def __init__(self, **kw): pass
    def embed_documents(self, texts): return [[0.0]*8 for _ in texts]
    def embed_query(self, q): return [0.0]*8
_stub("langchain_google_genai",
      {"ChatGoogleGenerativeAI": _FakeLLM,
       "GoogleGenerativeAIEmbeddings": _FakeEmb})

# chromadb
class _FakeCol:
    def __init__(self): self.items = []
    def add(self, **kw): self.items.append(kw)
    def query(self, **kw):
        return {"metadatas": [[{"parent_id": "pid1"}]], "documents": [["doc"]]}
    def get(self, ids=None):
        return {"documents": ["parent text"], "metadatas": [{"title": "T", "link": "L"}]}
class _FakeClient:
    def __init__(self, **kw): self.cols = {}
    def get_or_create_collection(self, name, **kw):
        return self.cols.setdefault(name, _FakeCol())
_stub("chromadb", {"PersistentClient": _FakeClient})

# feedparser, httpx, bs4, dotenv
_stub("feedparser", {"parse": lambda url: types.SimpleNamespace(entries=[])})
class _Resp:
    def raise_for_status(self): pass
    def json(self): return {"hits": []}
_stub("httpx", {"get": lambda *a, **kw: _Resp()})
_stub("dotenv", {"load_dotenv": lambda *a, **kw: None})

# fastapi (minimal stub — we test the view functions directly, not HTTP)
class _HTTPExc(Exception):
    def __init__(self, status_code=500, detail=""):
        self.status_code = status_code; self.detail = detail
        super().__init__(f"{status_code}: {detail}")
class _FastAPI:
    def __init__(self, **kw):
        self.version = kw.get("version", "0.0.0")
        self.routes = {}
    def _reg(self, method, path):
        def deco(fn):
            self.routes[(method, path)] = fn
            return fn
        return deco
    def get(self, path, **kw): return self._reg("GET", path)
    def post(self, path, **kw): return self._reg("POST", path)
class _Response:
    def __init__(self, content="", media_type="text/plain"):
        self.content = content
        self.media_type = media_type
class _BackgroundTasks:
    def __init__(self):
        self._tasks = []
    def add_task(self, fn, *args, **kwargs):
        from types import SimpleNamespace
        self._tasks.append(SimpleNamespace(func=fn, args=args, kwargs=kwargs))
_stub("fastapi", {"FastAPI": _FastAPI, "HTTPException": _HTTPExc,
                  "Response": _Response, "BackgroundTasks": _BackgroundTasks})

# langgraph (minimal graph runner)
START, END = "__start__", "__end__"
class _Graph:
    def __init__(self, state_schema): self.nodes = {}; self.edges = []
    def add_node(self, name, fn): self.nodes[name] = fn
    def add_edge(self, a, b): self.edges.append((a, b))
    def compile(self, **kw):
        nodes = self.nodes; edges = self.edges
        class _Compiled:
            def __init__(self):
                self._state = {}
                self._stopped_at = None
            def stream(self, input, config=None):
                if input is not None:
                    self._state.update(input)
                order = ["planner", "programmer", "tester"]
                start = 0
                if self._stopped_at:
                    start = order.index(self._stopped_at)
                    self._stopped_at = None
                for n in order[start:]:
                    if n == "programmer" and start == 0:  # interrupt
                        self._stopped_at = "programmer"
                        yield {n: "interrupted"}
                        return
                    out = nodes[n](self._state) or {}
                    self._state.update(out)
                    yield {n: out}
            def get_state(self, config):
                s = types.SimpleNamespace()
                s.values = dict(self._state)
                return s
            def update_state(self, config, values):
                self._state.update(values)
        return _Compiled()
class _CompiledHeadless:
    """Used by build_graph_headless (no interrupt)."""
    def __init__(self, nodes):
        self._nodes = nodes; self._state = {}
    def stream(self, input, config=None):
        if input is not None:
            self._state.update(input)
        for n in ("planner", "programmer", "tester"):
            if n == "planner" and "blueprint" in self._state:
                continue  # honor caller-supplied blueprint
            out = self._nodes[n](self._state) or {}
            self._state.update(out)
            yield {n: out}
    def get_state(self, config):
        s = types.SimpleNamespace(); s.values = dict(self._state); return s
    def update_state(self, config, values): self._state.update(values)

_orig_graph_compile = _Graph.compile
def _smart_compile(self, **kw):
    if kw.get("interrupt_before"):
        return _orig_graph_compile(self, **kw)
    return _CompiledHeadless(self.nodes)
_Graph.compile = _smart_compile

_stub("langgraph", {})
_stub("langgraph.graph", {"StateGraph": _Graph, "START": START, "END": END})
_stub("langgraph.checkpoint", {})
_stub("langgraph.checkpoint.memory", {"MemorySaver": lambda: None})

# ---------- 2. Import our modules ----------
print("== importing modules ==")
from config import settings
from src.schemas.blueprint import Blueprint
from src.schemas.error_log import ErrorEntry, log_error, read_errors
from src.models import router
from src.rag import parent_retriever
from src.agents import browser_rag, search_agent
print("  ok")

# ---------- 3. Exercise pure logic ----------
print("== router.pick_model (defaults) ==")
assert router.pick_model("simple") == settings.MODEL_LITE
assert router.pick_model("complex") == settings.MODEL_FLASH
print(f"  simple  -> {router.pick_model('simple')}")
print(f"  complex -> {router.pick_model('complex')}")

print("== user settings store round-trip ==")
us = settings.load_user_settings()
assert "routing" in us and "feeds" in us and "feed_keywords" in us
original = json.loads(json.dumps(us))  # deep copy
# Flip complex -> lite and disable arxiv, then verify router + collectors see it
us["routing"]["complex_model"] = settings.MODEL_LITE
us["feeds"]["arxiv_cs_ai"] = False
us["feed_keywords"]["simonw"] = ["llm"]
settings.save_user_settings(us)
assert router.pick_model("complex") == settings.MODEL_LITE
assert settings.enabled_feeds()["arxiv_cs_ai"] is False
assert settings.feed_keywords("simonw") == ["llm"]
print("  routing + feed + per-source overrides all applied")

print("== collectors honors feed toggles ==")
from src.sources import collectors as _col
# Monkeypatch fetch_rss + fetch_hn so we don't hit the network
_col.fetch_rss = lambda name, url: [{"source": name, "title": "LLM agents paper",
                                      "summary": "about llm", "link": "x",
                                      "published": "", "fetched_at": "t"}]
_col.fetch_hn = lambda: [{"source": "hn", "title": "RAG guide",
                          "summary": "rag things", "link": "x",
                          "published": "", "fetched_at": "t"}]
path = _col.collect_all(keywords=["rag"])
payload = json.loads(path.read_text())
srcs = {i["source"] for i in payload["items"]}
assert "arxiv_cs_ai" not in srcs, "disabled feed leaked through"
assert "simonw" in srcs, "override keyword 'llm' should have matched simonw"
print(f"  sources kept: {sorted(srcs)}")

# restore defaults so the rest of the test is deterministic
settings.save_user_settings(original)
print("  restored defaults")

print("== router.call_with_fallback ==")
out = router.call_with_fallback("complex", "hello")
assert "project_id" in out
print("  ok (fake LLM returned JSON)")

print("== Blueprint schema ==")
bp = Blueprint(
    project_id="x", title="t", topic="demo", objective="o",
    tech_stack=["python"],
    modules=[{"name": "m", "responsibility": "r", "inputs": [], "outputs": []}],
)
print(f"  blueprint.title = {bp.title}")

print("== error_log round trip ==")
log_error(ErrorEntry(code="RUNTIME_FAIL", module="smoke", message="test"))
errs = read_errors()
assert any(e["module"] == "smoke" for e in errs)
print(f"  {len(errs)} entries in error_log.json")

print("== parent_retriever ingest + retrieve (fake chroma) ==")
n = parent_retriever.ingest([{"text": "hello world " * 100,
                              "metadata": {"title": "t", "link": "l"}}])
print(f"  ingested parents: {n}")
hits = parent_retriever.retrieve("hello")
print(f"  retrieved: {len(hits)} parent chunk(s)")

print("== project runtime removed ==")
print("  code_team graph tests skipped by design")

print("== runner util (real subprocess) ==")
import tempfile, os
from src.utils.runner import run_project
from src.utils.zipper import zip_project
with tempfile.TemporaryDirectory() as td:
    (pathlib.Path(td) / "main.py").write_text(
        "import sys\nprint('hello from generated code')\nprint('args=', sys.argv[1:])\n"
    )
    rr = run_project(td, args=["--demo"], timeout=10)
    assert rr.returncode == 0, f"expected 0, got {rr.returncode}: {rr.stderr}"
    assert "hello from generated code" in rr.stdout
    print(f"  run_project -> exit={rr.returncode} elapsed={rr.elapsed:.2f}s")

    zb = zip_project(td)
    assert zb.startswith(b"PK"), "not a zip"
    print(f"  zip_project -> {len(zb)} bytes")

print("== runner timeout path ==")
with tempfile.TemporaryDirectory() as td:
    (pathlib.Path(td) / "main.py").write_text("import time\ntime.sleep(5)\n")
    rr = run_project(td, timeout=1)
    assert rr.timed_out, "expected timeout"
    print(f"  timeout correctly detected ({rr.stderr})")

print("== search agent with history + citations ==")
from src.agents.search_agent import answer as search_answer
res = search_answer("what is parent-document retrieval?",
                    history=[("user", "hi"), ("assistant", "hello")])
assert "answer" in res and "sources" in res
assert res["sources"], "expected at least one citation"
c0 = res["sources"][0]
assert "source_type" in c0 and "snippet" in c0
print(f"  answer len={len(res['answer'])} sources={len(res['sources'])}")
print(f"  first citation source_type={c0['source_type']} title={c0.get('title')}")

print("== project indexer ==")
import tempfile as _tf, json as _json
from src.rag.project_indexer import index_project
with _tf.TemporaryDirectory() as td:
    pd = pathlib.Path(td)
    (pd / "blueprint.json").write_text(_json.dumps(
        {"project_id": "p1", "title": "demo", "topic": "t"}))
    (pd / "main.py").write_text("print('hi')\n")
    (pd / "stability_report.md").write_text("# ok\nall pass\n")
    n = index_project(pd)
    assert n >= 1, f"expected >=1 parent chunks, got {n}"
    print(f"  indexed {n} parent chunks from fake project")

print("== FastAPI batch layer ==")
from api.main import app, health, ingest, ingest_status, search, errors
from api.main import SearchReq
from fastapi import BackgroundTasks as _BT  # resolves to smoke-test stub

h = health()
assert h["status"] == "ok" and "models" in h
print(f"  /health -> {h['status']}, models={list(h['models'].values())}")

bt = _BT()
ij = ingest(bt)
assert ij["status"] == "running" and "job_id" in ij
bt._tasks[0].func(*bt._tasks[0].args)  # run background task synchronously
is_ = ingest_status(ij["job_id"])
assert is_["status"] in ("done", "failed")
print(f"  /ingest -> job_id={ij['job_id'][:8]}... status after run={is_['status']}")

e = errors(limit=5)
print(f"  /errors -> {len(e['entries'])} recent entries")

print("== news curator + atom feed ==")
# Seed a fake collected.json so pick_top3 has data
from config.settings import RAW_DIR
_date = "2026-04-15"
_dir = RAW_DIR / _date
_dir.mkdir(parents=True, exist_ok=True)
(_dir / "collected.json").write_text(json.dumps({
    "description": "test",
    "items": [
        {"title": "LangGraph interrupts", "link": "https://ex.com/1"},
        {"title": "Parent-doc retrieval", "link": "https://ex.com/2"},
        {"title": "Gemini Flash tricks", "link": "https://ex.com/3"},
    ],
}))
from src.agents.news_curator import pick_top3, load_top3, list_all_top3
# Fake LLM returns a blueprint-shaped JSON, but _extract_json just needs
# a {...} — curator will accept picks=[] if missing. Patch the router
# for deterministic output.
from src.models import router as _router
_router.call_with_fallback = lambda task, prompt, **kw: (
    '{"picks":[{"rank":1,"title":"A","link":"https://a","justification":"j1"},'
    '{"rank":2,"title":"B","link":"https://b","justification":"j2"},'
    '{"rank":3,"title":"C","link":"https://c","justification":"j3"}]}'
)
# Curator imports at module-load time, so patch there too
from src.agents import news_curator as _nc
_nc.call_with_fallback = _router.call_with_fallback

payload = pick_top3(_date, force=True)
assert len(payload["picks"]) == 3, payload
assert load_top3(_date) is not None
archive = list_all_top3()
assert any(p.get("date") == _date for p in archive)
print(f"  picked {len(payload['picks'])} items, archive has {len(archive)} day(s)")

from src.agents.news_feed import export_atom
xml = export_atom(limit=10)
assert xml.startswith('<?xml') and "<feed" in xml and "<entry>" in xml
print(f"  atom feed len={len(xml)} bytes")

from api.main import news_top3, news_atom, news_archive
nt = news_top3(date=_date)
assert nt.get("picks"), nt
na = news_atom(limit=5)
assert "<feed" in na.content
nar = news_archive()
assert "payloads" in nar
print(f"  /news/top3 + /news/atom + /news/archive ok")

print("\n[OK] SMOKE TEST PASSED")
