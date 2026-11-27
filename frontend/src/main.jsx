import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Chat } from "./Chat.jsx";
import { ImportPage } from "./Knowledge.jsx";
import { RagEval } from "./RagEval.jsx";
import "./style.css";
const pages = { chat: "规程问答", import: "导入文档", ragEval: "RAG 评测" };
function activePage() {
  return Object.hasOwn(pages, location.hash.slice(1))
    ? location.hash.slice(1)
    : "chat";
}
function App() {
  const [page, setPage] = useState(activePage);
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
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <i aria-hidden="true" />
          管规工作台
        </div>
        <nav aria-label="主导航">
          <small>工作台</small>
          {nav("chat", "◉")}
          <small>知识库</small>
          {nav("import", "＋")}
          {nav("ragEval", "▤")}
        </nav>
        <footer>CJJ 181—2012</footer>
      </aside>
      <main>
        <div hidden={page !== "chat"}>
          <Chat />
        </div>
        <div hidden={page !== "import"}>
          <ImportPage />
        </div>
        {page === "ragEval" && <RagEval />}
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")).render(<App />);
