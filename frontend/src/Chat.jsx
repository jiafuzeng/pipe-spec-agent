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
function Turn({ turn, send, disabled }) {
  const evidence = turn.events
    .filter((e) => e.type === "evidence")
    .map((e) => e.data);
  const trace = turn.events.filter((e) =>
    ["tool_call", "plan_step"].includes(e.type),
  );
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
    <article className="panel turn">
      <h3>{turn.question}</h3>
      {trace.length > 0 && (
        <div className="timeline">
          <h4>执行记录</h4>
          {trace.map(({ type, data }, i) => (
            <details key={i}>
              <summary>
                {data.text || data.tool}{" "}
                <small>
                  {data.status}
                  {data.elapsed_ms != null
                    ? " · " + data.elapsed_ms + " ms"
                    : ""}
                </small>
              </summary>
              <pre>{JSON.stringify(data, null, 2)}</pre>
            </details>
          ))}
        </div>
      )}
      {turn.events.map(({ type, data }, i) => {
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
          const [axis, metric] = (
            data.csv?.split(/\r?\n/)[0] || "自变量,指数"
          ).split(",");
          const pointCall = trace.find(
            (e) => e.data.output?.result_id === data.result_ids?.[0],
          )?.data;
          return (
            <figure key={i}>
              <img
                src={"data:image/png;base64," + data.png_base64}
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
                  {data.points.map(([x, y], j) => (
                    <tr key={j}>
                      <td>{x}</td>
                      <td>{y}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <a
                download="curve.png"
                href={"data:image/png;base64," + data.png_base64}
              >
                下载 PNG
              </a>
              　
              <a
                download="curve.csv"
                href={
                  "data:text/csv;charset=utf-8," + encodeURIComponent(data.csv)
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
    [busy, setBusy] = useState(false);
  const editor = useRef(null),
    sending = useRef(false);
  useEffect(() => {
    try {
      sessionStorage.setItem("pipe.chat", JSON.stringify(chat));
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
    if (!message || sending.current || offline) return;
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
      turns: [...prev.turns, { id, question: message, events: [] }],
    }));
    setInput("");
    try {
      for (let i = 0; i < 2; i++) {
        if (!session) {
          session = (await request("/api/v1/sessions", { method: "POST" }))
            .session_id;
          setChat((prev) => ({ ...prev, session }));
        }
        if (await streamTurn(session, message, event)) return;
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
  return (
    <>
      <div className="pagehead">
        <div>
          <div className="crumb">工作台 / 规程问答</div>
          <h1>规程问答</h1>
        </div>
        <button
          disabled={busy}
          onClick={() => {
            setChat({ session: null, turns: [] });
            setInput("");
            editor.current.focus();
          }}
        >
          ＋ 新建会话
        </button>
      </div>
      <div className="hero">
        <div>
          <span className="standard">CJJ 181—2012</span>
          <h2>
            城镇排水管道
            <br />
            检测与评估技术规程
          </h2>
        </div>
        <div className="pipe-art" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
      </div>
      <div className="chatgrid">
        <div>
          <form
            className="panel composer"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <h3>向规程提问</h3>
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
              placeholder="输入检测条件、条款号或 RI / MI 计算问题…"
              maxLength={4000}
            />
            <div className="actions">
              <small>{input.length} / 4000</small>
              <button
                className="primary"
                disabled={busy || offline || !input.trim()}
              >
                {busy ? "处理中…" : "发送问题 ↗"}
              </button>
            </div>
          </form>
          <div aria-live="polite">
            {[...chat.turns].reverse().map((t, i) => (
              <Turn
                key={t.id}
                turn={t}
                send={send}
                disabled={busy || offline || i > 0}
              />
            ))}
          </div>
        </div>
        <aside className="panel examples">
          <h3>示例题库</h3>
          {names.map((name, i) => (
            <button onClick={() => choose(i)} key={name}>
              <span>{name}</span>
              <b>↗</b>
            </button>
          ))}
        </aside>
      </div>
    </>
  );
}
