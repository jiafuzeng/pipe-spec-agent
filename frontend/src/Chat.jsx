import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, deleteSession, examples, listSessions, offline, renameSession, request, streamTurn } from "./api.js";
import { renderMarkdown } from "./markdown.js";

const names = [
  "目的与范围",
  "检测方法对比",
  "普查周期",
  "现场适用条件",
  "声纳与检查井",
  "检测方案分析",
];
const toolNames = {
  search_clauses: "检索条款",
};

function thinkLine(event) {
  const data = event.data;
  if (event.type === "plan_step") {
    const questions = data.questions?.filter(Boolean);
    return data.text + (questions?.length ? "：" + questions.join("、") : "");
  }
  if (event.type !== "tool_call") return "";
  const name = toolNames[data.tool] || data.tool;
  const query = data.inputs?.query ? "「" + data.inputs.query + "」" : "";
  const outcome = data.outcome || data.status;
  const status =
    outcome === "succeeded" ? "完成" : outcome === "failed" ? "失败" : "进行中";
  return name + query + (data.summary ? " · " + data.summary : " · " + status);
}

function Think({ lines, live }) {
  const [open, setOpen] = useState(live);
  const [typed, setTyped] = useState("");
  const [lineIndex, setLineIndex] = useState(0);
  const body = useRef(null);
  const cursor = useRef({ index: -1, text: "" });
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  useEffect(() => {
    setOpen(live);
  }, [live]);
  useEffect(() => {
    if (!live || reduceMotion) {
      const last = Math.max(0, lines.length - 1);
      cursor.current = { index: last, text: lines[last] || "" };
      setLineIndex(last);
      setTyped(cursor.current.text);
      return;
    }
    if (!lines.length) {
      cursor.current = { index: -1, text: "" };
      setLineIndex(0);
      setTyped("");
      return;
    }
    const target = lines.length - 1;
    const text = lines[target] || "";
    const chars = [...text];
    let count = 0;
    if (cursor.current.index === target && text.startsWith(cursor.current.text)) {
      count = [...cursor.current.text].length;
    } else {
      cursor.current = { index: target, text: "" };
      setTyped("");
    }
    setLineIndex(target);
    if (count >= chars.length) {
      cursor.current = { index: target, text };
      setTyped(text);
      return;
    }
    const timer = window.setInterval(() => {
      count += 1;
      const next = chars.slice(0, count).join("");
      cursor.current = { index: target, text: next };
      setTyped(next);
      if (count >= chars.length) window.clearInterval(timer);
    }, 28);
    return () => window.clearInterval(timer);
  }, [live, lines, reduceMotion]);
  useEffect(() => {
    if (!live || !body.current) return;
    body.current.scrollTop = body.current.scrollHeight;
  }, [live, typed, lineIndex, lines]);
  const shown = !live
    ? lines
    : lines.length === 0
      ? []
      : lines.slice(0, lineIndex).concat([typed]);
  return (
    <div className={(open ? "think open" : "think done") + (live ? " live" : "")}>
      <button
        type="button"
        className="think-label"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        think
      </button>
      {open && (
        <ol className="think-body" ref={body} aria-live={live ? "polite" : undefined}>
          {shown.map((line, i) => (
            <li key={i}>
              {line}
              {live && i === shown.length - 1 && <i className="caret" />}
            </li>
          ))}
          {live && shown.length === 0 && (
            <li>
              <i className="caret" />
            </li>
          )}
        </ol>
      )}
    </div>
  );
}

function evidenceOf(turn) {
  return (turn?.events || []).filter((e) => e.type === "evidence").map((e) => e.data);
}

const chunkCache = new Map();
const nameCache = new Map();

async function documentName(item) {
  if (item.document_name) return item.document_name;
  if (!item.job_id) return "";
  if (!nameCache.has(item.job_id)) {
    nameCache.set(
      item.job_id,
      fetch(api + "/imports/" + item.job_id)
        .then((response) => (response.ok ? response.json() : null))
        .then((job) => job?.config?.original_filename || job?.config?.title || "")
        .catch(() => ""),
    );
  }
  return nameCache.get(item.job_id);
}

async function chunkText(item) {
  if (item.chunk) return item.chunk;
  if (!item.job_id || !item.source_hash) return item.quote || "";
  if (!chunkCache.has(item.job_id)) {
    chunkCache.set(
      item.job_id,
      (async () => {
        const rows = [];
        for (let offset = 0; offset < 500; offset += 100) {
          const response = await fetch(
            api +
              "/documents/" +
              item.source_hash +
              "/chunks?job_id=" +
              item.job_id +
              "&offset=" +
              offset +
              "&limit=100",
          );
          const part = response.ok ? await response.json() : [];
          if (!Array.isArray(part) || !part.length) break;
          rows.push(...part);
          if (part.length < 100) break;
        }
        return rows;
      })().catch(() => []),
    );
  }
  const rows = await chunkCache.get(item.job_id);
  const needle = (item.quote || "").replace(/\s+/g, "").slice(0, 48);
  const hit = rows.find(
    (row) => needle && (row.text || "").replace(/\s+/g, "").includes(needle),
  );
  return hit?.text || item.quote || "";
}

const SOURCE_KEY = "pipe.source";
function savedSourceWidth() {
  const saved = Number(localStorage.getItem(SOURCE_KEY));
  return saved >= 280 && saved <= 720 ? saved : 380;
}
function clampSource(value) {
  return Math.min(720, Math.max(280, value));
}
function SourcePane({ item, items, index, onPick, onClose, width, onResize, onNudge }) {
  const [name, setName] = useState(item.document_name || "");
  const [chunk, setChunk] = useState(item.chunk || "");
  useEffect(() => {
    let live = true;
    setName(item.document_name || "");
    setChunk(item.chunk || "");
    documentName(item).then((value) => {
      if (live && value) setName(value);
    });
    chunkText(item).then((value) => {
      if (live) setChunk(value || item.quote || "");
    });
    return () => {
      live = false;
    };
  }, [item]);
  const page =
    item.page_pdf == null ? "页码未知" : "PDF 第 " + item.page_pdf + " 页";
  return (
    <aside className="source-pane" aria-label="检索原文">
      <button
        type="button"
        className="source-grip"
        role="separator"
        aria-orientation="vertical"
        aria-label="调整原文栏宽度"
        aria-valuemin={280}
        aria-valuemax={720}
        aria-valuenow={width}
        onPointerDown={onResize}
        onKeyDown={(event) => {
          const step = event.key === "ArrowLeft" ? 16 : event.key === "ArrowRight" ? -16 : 0;
          if (!step) return;
          event.preventDefault();
          onNudge(step);
        }}
      />
      <div className="source-body">
      <header>
        <div>
          <p className="source-kicker">检索原文</p>
          <strong>条款 {item.clause_no}</strong>
        </div>
        <button type="button" className="icon-btn" aria-label="关闭" onClick={onClose}>
          ×
        </button>
      </header>
      {items.length > 1 && (
        <div className="source-switch">
          {items.map((row, i) => (
            <button
              type="button"
              key={row.evidence_id || i}
              aria-current={i === index ? "true" : undefined}
              onClick={() => onPick(i)}
            >
              {row.clause_no}
            </button>
          ))}
        </div>
      )}
      <p className="source-meta">
        <span>{name || "未记录文档名"}</span>
        <span>{page}</span>
      </p>
      <div className="source-chunk">{(chunk || item.quote || "没有检索文本").trim()}</div>
      </div>
    </aside>
  );
}

function citeText(item) {
  let text = String(item.quote || "").replace(/\s+/g, " ").trim();
  const clause = String(item.clause_no || "");
  if (clause && text.startsWith(clause)) text = text.slice(clause.length).trim();
  return text;
}
function citeHead(text) {
  const chars = [...text];
  if (chars.length <= 8) return text;
  return chars.slice(0, 8).join("") + "…";
}
function CiteCard({ item, current, onOpen }) {
  const text = citeText(item);
  const preview = citeHead(text);
  const page = item.page_pdf == null ? "" : "第 " + item.page_pdf + " 页";
  return (
    <button
      type="button"
      className="citation"
      aria-current={current ? "true" : undefined}
      aria-label={"条款 " + item.clause_no + (text ? "，" + text : "")}
      onClick={(event) => {
        event.stopPropagation();
        onOpen();
      }}
    >
      <span className="cite-no">〔{item.clause_no}〕</span>
      {preview && <span className="cite-quote">{preview}</span>}
      {page && <span className="cite-page">{page}</span>}
    </button>
  );
}
function eventPayload(event) {
  return event?.data?.type ? event.data : event?.data || event || {};
}
function isPartialAnswer(event) {
  return event?.type === "answer" && eventPayload(event).partial === true;
}
function isFinalAnswer(event) {
  return event?.type === "answer" && eventPayload(event).partial !== true;
}
function turnFinished(events) {
  return events.some(
    (event) => event.type === "error" || isFinalAnswer(event),
  );
}
function Turn({ turn, live, cited, selected, onCite, onSelect }) {
  const evidence = turn.events
    .filter((e) => e.type === "evidence")
    .map((e) => e.data);
  const trace = turn.events.filter((e) =>
    ["tool_call", "plan_step"].includes(e.type),
  );
  const thoughts = trace.map(thinkLine).filter(Boolean);
  const answers = turn.events.filter((e) => e.type === "answer");
  const latestAnswer = answers[answers.length - 1];
  function answerDisplay(text) {
    return String(text).replace(/\s*〔[^〕]+〕/g, "").replace(/[ \t]{2,}/g, " ").trim();
  }
  function answerHtml(text) {
    return renderMarkdown(answerDisplay(text));
  }
  function citedIndexes(text, data) {
    const seen = new Set();
    const indexes = [];
    function push(index) {
      if (index < 0 || seen.has(index)) return;
      seen.add(index);
      indexes.push(index);
    }
    const wanted = Array.isArray(data?.citations)
      ? data.citations.filter(Boolean)
      : [];
    for (const id of wanted) {
      push(
        evidence.findIndex(
          (item) => item.evidence_id === id || item.clause_no === id,
        ),
      );
    }
    for (const match of String(text).matchAll(/〔([^〕]+)〕/g)) {
      push(evidence.findIndex((item) => item.clause_no === match[1]));
    }
    if (indexes.length) return indexes;
    const byClause = new Set();
    evidence.forEach((item, index) => {
      const key = item.clause_no || item.evidence_id || index;
      if (byClause.has(key)) return;
      byClause.add(key);
      push(index);
    });
    return indexes;
  }
  function citeButton(index) {
    const item = evidence[index];
    return (
      <CiteCard
        key={item.evidence_id || item.clause_no}
        item={item}
        current={cited === index}
        onOpen={() => onCite(index)}
      />
    );
  }
  function renderAnswer(data, key) {
    const raw =
      data.text ||
      data.message ||
      data.code ||
      JSON.stringify(data, null, 2);
    const partial = data.partial === true;
    const asMarkdown = data.format === "markdown" || /[*_`#\-]/.test(String(raw));
    const cites = citedIndexes(raw, data);
    return (
      <div className={"reply-block" + (partial ? " streaming" : "")} key={key}>
        <div
          className={"reply" + (selected ? " selected" : "") + (asMarkdown ? " markdown" : "")}
          onClick={() => evidence.length && onSelect(0)}
        >
          {asMarkdown ? (
            <div
              className="reply-md"
              dangerouslySetInnerHTML={{ __html: answerHtml(raw) }}
            />
          ) : (
            answerDisplay(raw)
          )}
          {partial && <i className="caret" />}
        </div>
        {cites.length > 0 && (
          <div className="reply-cites">
            <span className="cite-label">原文引用</span>
            {cites.map(citeButton)}
          </div>
        )}
      </div>
    );
  }
  return (
    <article className="turn">
      <h3>{turn.question}</h3>
      {(live || thoughts.length > 0) && <Think lines={thoughts} live={live} />}
      {latestAnswer && renderAnswer(eventPayload(latestAnswer), "answer")}
      {!live &&
        turn.events.map(({ type, data }, i) => {
          if (type !== "error") return null;
          const raw =
            data.text ||
            data.message ||
            data.code ||
            JSON.stringify(data, null, 2);
          return (
            <div className="reply-block" key={i}>
              <div className="warning">{answerDisplay(raw)}</div>
            </div>
          );
        })}
    </article>
  );
}
const LAST_SESSION = "pipe.session";
function savedSession() {
  try {
    return localStorage.getItem(LAST_SESSION) || sessionStorage.getItem(LAST_SESSION);
  } catch {
    return null;
  }
}
function rememberSession(session) {
  try {
    if (session) localStorage.setItem(LAST_SESSION, session);
    else localStorage.removeItem(LAST_SESSION);
    sessionStorage.removeItem(LAST_SESSION);
  } catch {
    /* 当次打开仍可继续聊 */
  }
}
function recentWhen(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const delta = Date.now() - date.getTime();
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (delta < hour) return Math.max(1, Math.round(delta / minute)) + "分钟前";
  if (delta < day) return Math.max(1, Math.round(delta / hour)) + "小时前";
  return date.getMonth() + 1 + "月" + date.getDate() + "日";
}
export function Chat() {
  const [chat, setChat] = useState({ session: null, turns: [] }),
    [sessions, setSessions] = useState([]),
    [input, setInput] = useState(""),
    [busy, setBusy] = useState(false),
    [status, setStatus] = useState(""),
    [editing, setEditing] = useState(null),
    [draft, setDraft] = useState(""),
    [pendingDelete, setPendingDelete] = useState(null),
    [menu, setMenu] = useState(null),
    [more, setMore] = useState(false),
    [source, setSource] = useState(null),
    [sourceWidth, setSourceWidth] = useState(savedSourceWidth);
  function resizeSource(event) {
    if (event.button !== 0) return;
    const grip = event.currentTarget;
    try {
      grip.setPointerCapture(event.pointerId);
    } catch {
      /* 指针已被释放时仍按移动距离计算 */
    }
    const startX = event.clientX;
    const start = sourceWidth;
    function move(nextEvent) {
      setSourceWidth(clampSource(start - (nextEvent.clientX - startX)));
    }
    function up(nextEvent) {
      const next = clampSource(start - (nextEvent.clientX - startX));
      setSourceWidth(next);
      localStorage.setItem(SOURCE_KEY, String(next));
      grip.removeEventListener("pointermove", move);
      grip.removeEventListener("pointerup", up);
    }
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", up);
  }
  function nudgeSource(step) {
    setSourceWidth((value) => {
      const next = clampSource(value + step);
      localStorage.setItem(SOURCE_KEY, String(next));
      return next;
    });
  }
  const subject = chat.subject || "default";
  const editor = useRef(null),
    sending = useRef(false),
    runGen = useRef(0);
  const openSession = useRef(async () => {});
  openSession.current = async (session) => {
    const snapshot = await request("/api/v1/sessions/" + session);
    rememberSession(session);
    setChat({ session, turns: [], subject: snapshot.subject_id || "default" });
    const messages = snapshot.messages || [];
    const cursors = new Map();
    const restored = messages.map((m) => ({
      id: m.turn_id,
      question: m.text,
      subject: m.subject_id,
      events: [],
    }));
    let running;
    do {
      running = false;
      for (const run of new Set(messages.map((m) => m.run_id))) {
        const info = await request("/api/v1/runs/" + run);
        const replay = await request(
          "/api/v1/runs/" + run + "/events?after_event_id=" + (cursors.get(run) ?? -1),
        );
        for (const e of replay.events) {
          restored.find((t) => t.id === e.turn_id)?.events.push({ type: e.type, data: e });
          cursors.set(run, e.event_id);
        }
        running ||= info.status === "running";
      }
      setChat((prev) =>
        prev.session === session
          ? {
              ...prev,
              subject: snapshot.subject_id || prev.subject,
              turns: restored.map((t) => ({ ...t, events: [...t.events] })),
            }
          : prev,
      );
      if (running) await new Promise((resolve) => setTimeout(resolve, 500));
    } while (running);
  };
  useEffect(() => {
    if (offline) return;
    let cancelled = false;
    setBusy(true);
    listSessions()
      .then(async (rows) => {
        if (cancelled) return;
        setSessions(rows);
        const saved = savedSession();
        if (saved && rows.some((row) => row.session_id === saved)) {
          try {
            await openSession.current(saved);
          } catch {
            if (!cancelled) {
              setStatus("暂时打不开");
              setChat({ session: null, turns: [] });
            }
          }
        }
      })
      .catch(() => {
        if (!cancelled) setStatus("暂时无法读取会话列表");
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  function choose(i) {
    setInput(examples[i]);
    editor.current?.focus();
  }
  function rememberListed(session, message) {
    const now = new Date().toISOString();
    setSessions((rows) => {
      const current = rows.find((row) => row.session_id === session);
      const next = {
        session_id: session,
        title: current?.title || null,
        last_message: message,
        last_activity_at: now,
      };
      return [next, ...rows.filter((row) => row.session_id !== session)];
    });
  }
  async function send(message) {
    message = message.trim();
    if (!message || busy || sending.current || offline) return;
    const myGen = ++runGen.current;
    sending.current = true;
    setBusy(true);
    const id = crypto.randomUUID();
    let session = chat.session;
    const event = (e) => {
      if (runGen.current !== myGen) return;
      setChat((prev) => ({
        ...prev,
        turns: prev.turns.map((t) => {
          if (t.id !== id) return t;
          if (isPartialAnswer(e)) {
            const events = [...t.events];
            const last = events[events.length - 1];
            if (isPartialAnswer(last)) events[events.length - 1] = e;
            else events.push(e);
            return { ...t, events };
          }
          return { ...t, events: [...t.events, e] };
        }),
      }));
    };
    setChat((prev) => ({
      ...prev,
      turns: [...prev.turns, { id, question: message, subject, events: [], fresh: true }],
    }));
    setInput("");
    try {
      for (let i = 0; i < 2; i++) {
        if (runGen.current !== myGen) return;
        if (!session) {
          session = (await request("/api/v1/sessions", { method: "POST" }))
            .session_id;
          if (runGen.current !== myGen) return;
          setChat((prev) => ({ ...prev, session }));
          rememberSession(session);
        }
        if (await streamTurn(session, message, event, subject)) {
          if (runGen.current !== myGen) return;
          rememberListed(session, message);
          try {
            setSessions(await listSessions());
            setStatus("");
          } catch {
            setStatus("暂时无法读取会话列表");
          }
          return;
        }
        if (runGen.current !== myGen) return;
        if (chat.session)
          event({
            type: "error",
            data: { text: "服务端会话已过期，本轮将在新会话中重新提交。" },
          });
        session = null;
      }
      throw Error("无法恢复会话");
    } catch (e) {
      event({ type: "error", data: { text: e.message } });
    } finally {
      if (runGen.current === myGen) {
        sending.current = false;
        setBusy(false);
      }
    }
  }
  function startNewSession() {
    runGen.current += 1;
    sending.current = false;
    showChat();
    setBusy(false);
    setChat({ session: null, turns: [] });
    rememberSession(null);
    setStatus("");
    setInput("");
    setSource(null);
    setMenu(null);
    setEditing(null);
    editor.current?.focus();
  }
  function sessionLabel(item) {
    return item.title || item.last_message;
  }
  function closeMenu() {
    setMenu(null);
    setPendingDelete(null);
  }
  function openMenu(event, sessionId) {
    event.preventDefault();
    if (busy) return;
    const width = 148;
    const height = sessionId ? 132 : 48;
    setPendingDelete(null);
    setMenu({
      x: Math.max(8, Math.min(event.clientX, window.innerWidth - width - 8)),
      y: Math.max(8, Math.min(event.clientY, window.innerHeight - height - 8)),
      sessionId,
    });
  }
  useEffect(() => {
    if (!menu) return;
    function close(event) {
      if (event.target.closest?.(".session-menu")) return;
      closeMenu();
    }
    function onKey(event) {
      if (event.key === "Escape") closeMenu();
    }
    window.addEventListener("pointerdown", close);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [menu]);
  async function saveTitle(event) {
    event.preventDefault();
    const title = draft.trim();
    if (!title || busy) return;
    const id = editing;
    try {
      const saved = await renameSession(id, title);
      setSessions((rows) =>
        rows.map((row) => (row.session_id === id ? { ...row, title: saved.title } : row)),
      );
      setEditing(null);
      setMenu(null);
      setStatus("");
    } catch {
      setStatus("暂时无法修改会话");
    }
  }
  async function removeSession(id) {
    if (busy) return;
    if (pendingDelete !== id) {
      setPendingDelete(id);
      return;
    }
    try {
      await deleteSession(id);
      setSessions((rows) => rows.filter((row) => row.session_id !== id));
      setPendingDelete(null);
      setEditing(null);
      setMenu(null);
      setStatus("");
      if (chat.session === id) startNewSession();
    } catch {
      setStatus("暂时无法删除会话");
    }
  }
  function showChat() {
    if (location.hash !== "" && location.hash !== "#chat") location.hash = "chat";
  }
  async function chooseSession(session) {
    showChat();
    setSource(null);
    if (busy || session === chat.session) return;
    setBusy(true);
    try {
      await openSession.current(session);
      setStatus("");
    } catch {
      setStatus("暂时打不开");
    } finally {
      setBusy(false);
    }
  }
  const prompts = [0, 1, 4];
  const shown = more ? sessions : sessions.slice(0, 5);
  const dock = document.getElementById("session-dock");
  const fresh = document.getElementById("new-session");
  const history = (
    <nav
      className="session-list"
      aria-label="历史会话"
      onContextMenu={(event) => {
        if (event.target.closest(".session-row, input, textarea")) return;
        openMenu(event, null);
      }}
    >
      <small>历史会话</small>
      {sessions.length === 0 && <p className="history-empty">还没有历史会话</p>}
      <div className="session-scroll">
      {shown.map((item) => (
        <div
          className="session-row"
          key={item.session_id}
          onContextMenu={(event) => openMenu(event, item.session_id)}
        >
          {editing === item.session_id ? (
            <form className="session-rename" onSubmit={saveTitle}>
              <input
                aria-label="会话名称"
                value={draft}
                maxLength={80}
                autoFocus
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") setEditing(null);
                }}
              />
              <button type="button" disabled={busy || !draft.trim()} onClick={saveTitle}>
                保存
              </button>
            </form>
          ) : (
            <button
              type="button"
              className="recent-item"
              aria-current={item.session_id === chat.session ? "true" : undefined}
              disabled={busy}
              onClick={() => chooseSession(item.session_id)}
            >
              <span className="session-title">{sessionLabel(item)}</span>
              <time dateTime={item.last_activity_at}>{recentWhen(item.last_activity_at)}</time>
            </button>
          )}
        </div>
      ))}
      </div>
      {sessions.length > 5 && (
        <button type="button" className="recent-more" onClick={() => setMore((open) => !open)}>
          {more ? "收起" : "查看更多 (" + (sessions.length - 5) + ")"}
        </button>
      )}
    </nav>
  );
  let active = null;
  if (source && source.turnId) {
    const turn = chat.turns.find((item) => item.id === source.turnId);
    const items = evidenceOf(turn);
    if (items[source.index]) active = { turn, items, index: source.index };
  }
  return (
    <div
      className={(chat.turns.length ? "ask talking" : "ask") + (active ? " has-source" : "")}
      style={active ? { "--source": sourceWidth + "px" } : undefined}
    >
      {fresh && createPortal(
        <button type="button" className="new-session" onClick={startNewSession}>
          <span aria-hidden="true">＋</span>
          新建会话
        </button>,
        fresh,
      )}
      {dock && createPortal(history, dock)}
      {menu && createPortal(
        <div className="session-menu" role="menu" style={{ left: menu.x, top: menu.y }}>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              closeMenu();
              startNewSession();
            }}
          >
            新建会话
          </button>
          {menu.sessionId && (
            <>
              <button
                type="button"
                role="menuitem"
                disabled={busy}
                onClick={() => {
                  const item = sessions.find((row) => row.session_id === menu.sessionId);
                  if (!item) return;
                  setEditing(menu.sessionId);
                  setDraft(sessionLabel(item));
                  closeMenu();
                }}
              >
                改名
              </button>
              <button
                type="button"
                role="menuitem"
                className="danger"
                disabled={busy}
                onClick={() => removeSession(menu.sessionId)}
              >
                {pendingDelete === menu.sessionId ? "确认删除" : "删除"}
              </button>
            </>
          )}
        </div>,
        document.body,
      )}
      <div className="ask-col">
        {!chat.turns.length && (
          <div className="ask-hello">
            <h1>我帮你查</h1>
            <div className="examples">
              {names.map((name, i) => (
                <button type="button" onClick={() => choose(i)} key={name}>
                  {name}
                </button>
              ))}
            </div>
          </div>
        )}
        {chat.turns.length > 0 && (
          <div className="thread" aria-live="polite">
            {chat.turns.map((t) => (
              <Turn
                key={t.id}
                turn={t}
                cited={active && active.turn.id === t.id ? active.index : -1}
                selected={Boolean(active && active.turn.id === t.id)}
                onCite={(index) => setSource({ turnId: t.id, index })}
                onSelect={(index) => setSource({ turnId: t.id, index })}
                live={busy && !turnFinished(t.events)}
              />
            ))}
          </div>
        )}
        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <textarea
            ref={editor}
            aria-label="问题"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (
                !e.nativeEvent.isComposing &&
                (e.metaKey || e.ctrlKey) &&
                e.key === "Enter"
              )
                send(input);
            }}
            placeholder="今天帮你查什么？输入检测条件或条款号"
            maxLength={4000}
          />
          <div className="composer-foot">
            {input.length > 0 && <small>{input.length} / 4000</small>}
            <button
              className="primary"
              aria-label={busy ? "处理中" : "发送问题"}
              disabled={busy || offline || !input.trim()}
            >
              {busy ? "…" : "↑"}
            </button>
          </div>
        </form>
        {status && (
          <div className="ask-meta">
            <span role="status">{status}</span>
          </div>
        )}
        {!chat.turns.length && (
          <div className="prompts">
            {prompts.map((i) => (
              <button type="button" onClick={() => choose(i)} key={examples[i]}>
                {examples[i]} <span aria-hidden="true">↗</span>
              </button>
            ))}
          </div>
        )}
      </div>
      {active && (
        <SourcePane
          item={active.items[active.index]}
          items={active.items}
          index={active.index}
          onPick={(index) => setSource({ turnId: active.turn.id, index })}
          onClose={() => setSource(null)}
          width={sourceWidth}
          onResize={resizeSource}
          onNudge={nudgeSource}
        />
      )}
    </div>
  );
}
