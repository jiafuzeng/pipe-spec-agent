import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Chat } from "./Chat.jsx";
import { ImportPage } from "./Knowledge.jsx";
import { RagEval } from "./RagEval.jsx";
import { AgentEval } from "./AgentEval.jsx";
import { FlowPage } from "./FlowPage.jsx";
import "./style.css";
const pages = {
  chat: "规程问答",
  flow: "流程图拓扑",
  import: "导入文档",
  ragEval: "RAG 评测",
  agentEval: "Agent 评测",
};
const SIDE_KEY = "pipe.sidebar";
const SIDE_OPEN_KEY = "pipe.sidebar.open";
function sideWidth() {
  const saved = Number(localStorage.getItem(SIDE_KEY));
  return saved >= 200 && saved <= 480 ? saved : 248;
}
function sideOpen() {
  return localStorage.getItem(SIDE_OPEN_KEY) !== "0";
}
function SidebarIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M9 4.5v15" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}
function activePage() {
  return Object.hasOwn(pages, location.hash.slice(1))
    ? location.hash.slice(1)
    : "chat";
}
function App() {
  const [page, setPage] = useState(activePage);
  const [side, setSide] = useState(sideWidth);
  const [open, setOpen] = useState(sideOpen);
  function toggleSide() {
    setOpen((value) => {
      const next = !value;
      localStorage.setItem(SIDE_OPEN_KEY, next ? "1" : "0");
      return next;
    });
  }
  function resizeSide(event) {
    if (event.button !== 0) return;
    const grip = event.currentTarget;
    try {
      grip.setPointerCapture(event.pointerId);
    } catch {
      /* 指针已被释放时仍按移动距离计算 */
    }
    const startX = event.clientX;
    const start = side;
    const clamp = (value) => Math.min(480, Math.max(200, value));
    function move(nextEvent) {
      setSide(clamp(start + nextEvent.clientX - startX));
    }
    function up(nextEvent) {
      const next = clamp(start + nextEvent.clientX - startX);
      setSide(next);
      localStorage.setItem(SIDE_KEY, String(next));
      grip.removeEventListener("pointermove", move);
      grip.removeEventListener("pointerup", up);
    }
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", up);
  }
  useEffect(() => {
    const change = () => setPage(activePage());
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  function nav(key, icon) {
    return (
      <a href={"#" + key} aria-current={page === key ? "page" : undefined}>
        <span aria-hidden="true">{icon}</span>
        {pages[key]}
      </a>
    );
  }
  return (
    <div className={open ? "shell" : "shell side-closed"} style={{ "--side": open ? side + "px" : "0px" }}>
      {!open && (
        <button type="button" className="icon-btn side-reveal" aria-label="显示侧栏" aria-expanded="false" onClick={toggleSide}>
          <SidebarIcon />
        </button>
      )}
      <aside className="sidebar" id="app-sidebar" hidden={!open}>
        <div className="side-tools">
          <button type="button" className="icon-btn" aria-label="隐藏侧栏" aria-expanded="true" aria-controls="app-sidebar" onClick={toggleSide}>
            <SidebarIcon />
          </button>
        </div>
        <a className="brand" href="#chat" aria-current={page === "chat" ? "page" : undefined}>
          <i aria-hidden="true" />
          管规工作台
        </a>
        <nav aria-label="主导航">
          <small>工作台</small>
          <div id="new-session" />
          {nav("flow", "⧉")}
          <small>知识库</small>
          {nav("import", "＋")}
          <small>评测</small>
          {nav("ragEval", "▤")}
          {nav("agentEval", "▤")}
          <div id="session-dock" className="session-dock" />
        </nav>
        <footer>CJJ 181—2012</footer>
        <button
          type="button"
          className="sider-grip"
          role="separator"
          aria-orientation="vertical"
          aria-label="调整侧栏宽度"
          aria-valuemin={200}
          aria-valuemax={480}
          aria-valuenow={side}
          tabIndex={0}
          onPointerDown={resizeSide}
          onKeyDown={(event) => {
            const step = event.key === "ArrowLeft" ? -16 : event.key === "ArrowRight" ? 16 : 0;
            if (!step) return;
            event.preventDefault();
            const next = Math.min(480, Math.max(200, side + step));
            setSide(next);
            localStorage.setItem(SIDE_KEY, String(next));
          }}
        />
      </aside>
      <main>
        <div hidden={page !== "chat"}>
          <Chat />
        </div>
        <div hidden={page !== "import"}>
          <ImportPage />
        </div>
        {page === "flow" && <FlowPage />}
        {page === "ragEval" && <RagEval />}
        {page === "agentEval" && <AgentEval />}
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")).render(<App />);
