"""Project page — Plan → HITL → Build → Test → Run → Download."""
import json
import sys
import uuid
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.agents.code_team import build_graph
from src.utils.runner import run_project
from src.utils.zipper import zip_project
from src.schemas.error_log import read_errors
from config.settings import ROOT

st.title("🛠️  Project — Plan, Build, Test, Run")

topic = st.text_input("Topic (concept or technique)",
                      placeholder="e.g., LangGraph interrupt for HITL")

if "graph" not in st.session_state:
    st.session_state.graph = build_graph()
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.blueprint = None
    st.session_state.run_result = None

cfg = {"configurable": {"thread_id": st.session_state.thread_id}}

col1, col2 = st.columns([1, 1])

# ---------------- Left: plan / approve / build ----------------
with col1:
    if st.button("1️⃣  Plan", disabled=not topic):
        with st.spinner("Planner running…"):
            for _ in st.session_state.graph.stream({"topic": topic}, config=cfg):
                pass
            state = st.session_state.graph.get_state(cfg).values
            st.session_state.blueprint = state.get("blueprint")
            st.session_state.run_result = None

    if st.session_state.blueprint:
        st.subheader("Blueprint (edit before build)")
        edited = st.text_area(
            "blueprint.json", value=json.dumps(st.session_state.blueprint, indent=2),
            height=350)
        if st.button("2️⃣  Approve & Build"):
            try:
                bp = json.loads(edited)
                st.session_state.graph.update_state(cfg, {"blueprint": bp})
                with st.spinner("Programmer + Tester running…"):
                    for _ in st.session_state.graph.stream(None, config=cfg):
                        pass
                st.success("Done. See right panel.")
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON: {e}")
            except Exception as e:  # noqa: BLE001
                st.error(f"Failed: {e}")

# ---------------- Right: code / report / run / download ----------------
with col2:
    state = (st.session_state.graph.get_state(cfg).values
             if st.session_state.blueprint else {})
    project_dir = state.get("project_dir")

    if state.get("code"):
        st.subheader("Generated main.py")
        st.code(state["code"], language="python")

    if state.get("stability_report"):
        with st.expander("📋 Stability Report", expanded=False):
            st.markdown(state["stability_report"])

    if project_dir:
        st.subheader("▶️  Run / Download")
        run_args = st.text_input("CLI args", value="",
                                 help="Space-separated, e.g. --topic demo")
        timeout = st.number_input("Timeout (s)", min_value=5, max_value=300, value=30)

        b1, b2 = st.columns(2)
        with b1:
            if st.button("▶️  Run generated code"):
                with st.spinner("Running…"):
                    st.session_state.run_result = run_project(
                        project_dir,
                        args=run_args.split() if run_args.strip() else None,
                        timeout=int(timeout),
                    )
        with b2:
            try:
                zip_bytes = zip_project(project_dir)
                st.download_button(
                    "⬇️  Download project.zip",
                    data=zip_bytes,
                    file_name=f"{Path(project_dir).name}.zip",
                    mime="application/zip",
                )
            except FileNotFoundError:
                st.info("Build a project first to enable download.")

        rr = st.session_state.run_result
        if rr is not None:
            status = ("⏱️  timed out" if rr.timed_out
                      else ("✅ exit 0" if rr.returncode == 0
                            else f"❌ exit {rr.returncode}"))
            st.caption(f"{status} · {rr.elapsed:.2f}s")
            if rr.stdout:
                with st.expander("stdout", expanded=True):
                    st.code(rr.stdout)
            if rr.stderr:
                with st.expander("stderr", expanded=bool(rr.returncode)):
                    st.code(rr.stderr)

st.divider()

# ---------------- Error log viewer ----------------
st.subheader("🚨 Recent Errors (error_log.json)")
errs = read_errors(limit=10)
if not errs:
    st.info("No errors logged yet.")
else:
    for e in reversed(errs):
        label = f"[{e.get('code','?')}] {e.get('module','?')} — {e.get('timestamp','')[:19]}"
        with st.expander(label):
            st.write(f"**Message:** {e.get('message','')}")
            if e.get("recovery_suggestion"):
                st.info(f"💡 {e['recovery_suggestion']}")
            if e.get("context"):
                st.json(e["context"])

st.divider()

# ---------------- Previous projects ----------------
st.subheader("📁 Previous Projects")
projects_dir = ROOT / "data" / "projects"
_project_dirs: list = []
if projects_dir.exists():
    _project_dirs = sorted(
        [p for p in projects_dir.iterdir() if p.is_dir()], reverse=True)
    for p in _project_dirs:
        with st.expander(p.name):
            bp_file = p / "blueprint.json"
            if bp_file.exists():
                st.json(json.loads(bp_file.read_text()))
            c1, c2 = st.columns(2)
            with c1:
                try:
                    st.download_button(
                        "⬇️  Download",
                        data=zip_project(p),
                        file_name=f"{p.name}.zip",
                        mime="application/zip",
                        key=f"dl_{p.name}",
                    )
                except Exception:  # noqa: BLE001
                    pass
            with c2:
                report = p / "stability_report.md"
                if report.exists():
                    st.caption("has stability_report.md")

# ---------------- Build comparison ----------------
if len(_project_dirs) >= 2:
    st.divider()
    st.subheader("🔀 Compare Builds")
    _names = [p.name for p in _project_dirs]
    cc1, cc2 = st.columns(2)
    with cc1:
        left_name = st.selectbox("Build A", _names, index=0, key="cmp_left")
    with cc2:
        right_name = st.selectbox("Build B", _names, index=1, key="cmp_right")

    if left_name != right_name:
        left_dir = projects_dir / left_name
        right_dir = projects_dir / right_name

        def _read(path: "Path", fname: str) -> str:
            f = path / fname
            return f.read_text(encoding="utf-8") if f.exists() else "(not found)"

        st.markdown("**main.py**")
        mc1, mc2 = st.columns(2)
        with mc1:
            st.caption(left_name)
            st.code(_read(left_dir, "main.py"), language="python")
        with mc2:
            st.caption(right_name)
            st.code(_read(right_dir, "main.py"), language="python")

        st.markdown("**Stability Report**")
        sc1, sc2 = st.columns(2)
        with sc1:
            st.caption(left_name)
            st.markdown(_read(left_dir, "stability_report.md"))
        with sc2:
            st.caption(right_name)
            st.markdown(_read(right_dir, "stability_report.md"))
