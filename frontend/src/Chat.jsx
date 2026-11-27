import React, { useEffect, useRef, useState } from "react";
import { api, examples, offline, request, streamTurn } from "./api.js";

const names = [
  "目的与范围",
  "检测方法对比",
  "普查周期",
  "现场适用条件",
  "声纳与检查井",
  "检测方案分析",
  "RI–K 曲线",
  "修复指数追问",
  "综合评估",
];
function Slots({ data, send, disabled }) {
  const [values, set] = useState({ ...data.confirmed });
  const fields = [
    ...Object.keys(data.confirmed || {})
      .filter((key) => !data.fields.some((f) => f.name === key))
      .map((name) => ({ name })),
    ...data.fields,
  ];
  return (
    <form
      className="slots"
      onSubmit={(e) => {
        e.preventDefault();
        send(fields.map((f) => f.name + "=" + values[f.name]).join(" "));
      }}
    >
      <h4>确认计算参数</h4>
      {fields.map((f) => (
        <label key={f.name}>
          {f.label_zh || f.name} {f.unit}
          <input
            required
            value={values[f.name] ?? ""}
            onChange={(e) => set({ ...values, [f.name]: e.target.value })}
          />
          <small>
            {f.description} {(f.evidence_refs || []).join("、")}
          </small>
        </label>
      ))}
      <button disabled={disabled}>确认并继续</button>
    </form>
  );
}
const toolNames = {
  search_clauses: "检索条款",
  get_calculation_schema: "读取计算规则",
  calculate_index: "计算指数",
  plot_curve: "绘制曲线",
  lookup_defect_score: "查缺陷分值",
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
  const status = data.status === "succeeded" ? "完成" : data.status === "failed" ? "失败" : "进行中";
  return name + query + (data.summary ? " · " + data.summary : " · " + status);
}

function reducedMotion() {
  return (
    typeof matchMedia === "function" &&
    matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function Think({ lines, live, animate, onDone }) {
  const text = lines.join("\n");
  const played = React.useRef(animate);
  const [n, setN] = React.useState(0);
  const typing = played.current && !reducedMotion() && (live || n < text.length);
  React.useEffect(() => {
    if (!played.current || reducedMotion()) {
      onDone(!live);
      return;
    }
    onDone(!live && n >= text.length);
  }, [live, n, text, onDone]);
  React.useEffect(() => {
    if (!played.current || reducedMotion() || n >= text.length) return;
    const step = text.length > 48 ? 2 : 1;
    const id = setTimeout(() => setN((v) => Math.min(text.length, v + step)), 24);
    return () => clearTimeout(id);
  }, [n, text]);
  if (!played.current) {
    return (
      <div className="think done">
        <p className="think-label">思考过程</p>
        {lines.map((line, i) => (
          <p key={i}>{line}</p>
        ))}
      </div>
    );
  }
  return (
    <div className={typing ? "think" : "think done"}>
      <p className="think-label" role="status">
        {typing ? "思考中" : "思考过程"}
      </p>
      <p className="think-body">
        {text.slice(0, reducedMotion() ? text.length : n)}
        {typing && <i className="caret" />}
      </p>
    </div>
  );
}

function Turn({ turn, send, disabled, live }) {
  const evidence = turn.events
    .filter((e) => e.type === "evidence")
    .map((e) => e.data);
  const trace = turn.events.filter((e) =>
    ["tool_call", "plan_step"].includes(e.type),
  );
  const thoughts = trace.map(thinkLine).filter(Boolean);
  const [shown, setShown] = useState(!turn.fresh);
  useEffect(() => {
    if (!live && thoughts.length === 0) setShown(true);
  }, [live, thoughts.length]);
  function linked(text) {
    return String(text)
      .split(/(〔[^〕]+〕)/)
      .map((part, i) => {
        const index = evidence.findIndex(
          (e) => "〔" + e.clause_no + "〕" === part,
        );
        return index < 0 ? (
          part
        ) : (
          <button
            className="citation"
            key={i}
            onClick={() => {
              const d = document.getElementById(turn.id + "-e" + index);
              if (d) {
                d.open = true;
                d.scrollIntoView({ block: "nearest" });
              }
            }}
          >
            {part}
          </button>
        );
      });
  }
  return (
    <article className="turn">
      <h3>{turn.question}</h3>
      {(live || thoughts.length > 0) && (
        <Think lines={thoughts} live={live} animate={Boolean(turn.fresh)} onDone={setShown} />
      )}
      {shown && !live && turn.events.map(({ type, data }, i) => {
        if (type === "clarification_required")
          return <Slots key={i} data={data} send={send} disabled={disabled} />;
        if (type === "answer" || type === "error")
          return (
            <div className={type === "error" ? "warning" : "reply"} key={i}>
              {linked(
                data.text ||
                  data.message ||
                  data.code ||
                  JSON.stringify(data, null, 2),
              )}
            </div>
          );
        if (type === "chart") {
          const metadata = trace.find((e) => e.data.tool === "plot_curve" && e.data.output?.resource_id === data.resource_id)?.data.output || data;
          const imageUrl = "/api/v1/artifacts/" + data.resource_id;
          const [axis, metric] = (
            metadata.csv?.split(/\r?\n/)[0] || "自变量,指数"
          ).split(",");
          const pointCall = trace.find(
            (e) => e.data.output?.result_id === metadata.result_ids?.[0],
          )?.data;
          return (
            <figure key={i}>
              <img
                src={imageUrl}
                alt={metric + " 随 " + axis + " 变化的曲线"}
              />
              <figcaption>
                {pointCall && (
                  <>
                    规则版本 {pointCall.inputs.rule_version} · 固定参数{" "}
                    {Object.entries(pointCall.inputs.parameters)
                      .filter(([k]) => k !== axis)
                      .map(([k, v]) => k + "=" + v)
                      .join("，")}
                  </>
                )}
              </figcaption>
              <table>
                <thead>
                  <tr>
                    <th>{axis}</th>
                    <th>{metric}</th>
                  </tr>
                </thead>
                <tbody>
                  {(metadata.points || []).map(([x, y], j) => (
                    <tr key={j}>
                      <td>{x}</td>
                      <td>{y}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <a
                download="curve.png"
                href={imageUrl}
              >
                下载 PNG
              </a>
              　
              <a
                download="curve.csv"
                href={
                  "data:text/csv;charset=utf-8," + encodeURIComponent(metadata.csv || "")
                }
              >
                下载 CSV
              </a>
            </figure>
          );
        }
        return null;
      })}
      {evidence.map((e, i) => (
        <details id={turn.id + "-e" + i} key={i}>
          <summary>
            条款 {e.clause_no} · PDF 第 {e.page_pdf} 页
          </summary>
          <p>{e.quote}</p>
          <small>
            {e.chapter} · {e.source_hash}
          </small>
          <a
            target="_blank"
            rel="noreferrer"
            href={
              api +
              "/documents/" +
              e.source_hash +
              "/original?job_id=" +
              e.job_id +
              "#page=" +
              e.page_pdf
            }
          >
            打开原文 ↗
          </a>
        </details>
      ))}
    </article>
  );
}
function restore() {
  try {
    return (
      JSON.parse(sessionStorage.getItem("pipe.chat")) || {
        session: null,
        turns: [],
      }
    );
  } catch {
    return { session: null, turns: [] };
  }
}
export function Chat() {
  const [chat, setChat] = useState(restore),
    [input, setInput] = useState(""),
    [busy, setBusy] = useState(false),
    [subjects, setSubjects] = useState({}),
    [status, setStatus] = useState("");
  const subject = chat.subject || "default";
  const initialSession = useRef(chat.session);
  useEffect(() => {
    const session = initialSession.current;
    if (!session || offline) return;
    let cancelled = false;
    async function recover() {
      const snapshot = await request("/api/v1/sessions/" + session);
      if (cancelled) return;
      setSubjects(snapshot.subjects);
      const messages = snapshot.messages || [];
      const cursors = new Map();
      const restored = messages.map((m) => ({ id: m.turn_id, question: m.text, subject: m.subject_id, events: [] }));
      let running;
      do {
        running = false;
        for (const run of new Set(messages.map((m) => m.run_id))) {
          const info = await request("/api/v1/runs/" + run);
          const replay = await request("/api/v1/runs/" + run + "/events?after_event_id=" + (cursors.get(run) ?? -1));
          for (const e of replay.events) {
            restored.find((t) => t.id === e.turn_id)?.events.push({ type: e.type, data: e });
            cursors.set(run, e.event_id);
          }
          running ||= info.status === "running";
        }
        if (cancelled) return;
        setChat((prev) => ({ ...prev, turns: restored.map((t) => ({...t, events: [...t.events]})) }));
        if (running) await new Promise((resolve) => setTimeout(resolve, 500));
      } while (running && !cancelled);
      if (!cancelled) setSubjects((await request("/api/v1/sessions/" + session)).subjects);
    }
    setBusy(true);
    recover().catch(() => { if (!cancelled) setStatus("暂时无法恢复服务端会话"); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, []);
  const editor = useRef(null),
    sending = useRef(false);
  useEffect(() => {
    try {
      sessionStorage.setItem(
        "pipe.chat",
        JSON.stringify({
          ...chat,
          turns: chat.turns.map(({ fresh, ...turn }) => turn),
        }),
      );
    } catch {
      sessionStorage.removeItem("pipe.chat");
    }
  }, [chat]);
  function choose(i) {
    setInput(examples[i]);
    editor.current.focus();
  }
  async function send(message) {
    message = message.trim();
    if (!message || busy || sending.current || offline) return;
    sending.current = true;
    setBusy(true);
    const id = crypto.randomUUID();
    let session = chat.session;
    const event = (e) =>
      setChat((prev) => ({
        ...prev,
        turns: prev.turns.map((t) =>
          t.id === id ? { ...t, events: [...t.events, e] } : t,
        ),
      }));
    setChat((prev) => ({
      ...prev,
      turns: [...prev.turns, { id, question: message, subject, events: [], fresh: true }],
    }));
    setInput("");
    try {
      for (let i = 0; i < 2; i++) {
        if (!session) {
          session = (await request("/api/v1/sessions", { method: "POST" }))
            .session_id;
          setChat((prev) => ({ ...prev, session }));
        }
        if (await streamTurn(session, message, event, subject)) {
          const snapshot = await request("/api/v1/sessions/" + session);
          setSubjects(snapshot.subjects);
          setStatus("");
          return;
        }
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
      sending.current = false;
      setBusy(false);
    }
  }
  function reset() {
    setChat({ session: null, turns: [] });
    setSubjects({});
    setStatus("");
    setInput("");
    editor.current.focus();
  }
  const confirmed = Object.entries(subjects[subject]?.confirmed || {});
  const prompts = [0, 1, 4, 7];
  return (
    <div className={chat.turns.length ? "ask talking" : "ask"}>
      <div className="ask-col">
        {!chat.turns.length && (
          <div className="ask-hello">
            <h1>规程问答，我帮你查</h1>
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
            <div className="thread-bar">
              <strong>规程问答</strong>
              <button type="button" disabled={busy} onClick={reset}>
                新会话
              </button>
            </div>
            {chat.turns.map((t) => (
              <Turn
                key={t.id}
                turn={t}
                send={send}
                live={busy && !t.events.some((e) => ["answer", "error", "clarification_required", "chart"].includes(e.type))}
                disabled={busy || offline || (t.subject || "default") !== subject || chat.turns.slice(chat.turns.indexOf(t) + 1).some((next) => (next.subject || "default") === subject)}
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
            placeholder="今天帮你查什么？输入检测条件、条款号或 RI / MI 计算问题"
            maxLength={4000}
          />
          <div className="composer-foot">
            <label>
              管段
              <input
                aria-label="当前管段"
                maxLength={128}
                disabled={busy}
                value={chat.subject ?? "default"}
                list="pipe-subjects"
                onChange={(e) =>
                  setChat((prev) => ({ ...prev, subject: e.target.value }))
                }
              />
            </label>
            <datalist id="pipe-subjects">
              {Object.keys(subjects).map((id) => (
                <option key={id} value={id} />
              ))}
            </datalist>
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
        {(confirmed.length > 0 || status) && (
          <div className="ask-meta">
            {confirmed.map(([kind, slots]) => (
              <span key={kind}>
                {kind} · {Object.entries(slots).map(([k, v]) => k + "=" + v).join("，")}
              </span>
            ))}
            {status && <span role="status">{status}</span>}
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
    </div>
  );
}
