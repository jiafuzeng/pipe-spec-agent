import React, { useEffect, useState } from "react";
import { request } from "./api.js";

export function AgentEval() {
  const [report, setReport] = useState(null), [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    request("/api/v1/evaluations/agent", {signal:controller.signal})
      .then(setReport).catch((e) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, []);
  return <section><h1>Agent 评测</h1>{error && <p role="alert">{error}</p>}
    {report && <div className="panel"><h3>通过 {report.summary.passed} / {report.summary.total}</h3>
      <p>检索模式 {report.retrieval_mode} · 工具模式 {report.mode}</p>
      {report.results.map((row) => <details key={row.id}><summary>{row.id} · {row.skipped ? "已跳过" : row.passed ? "通过" : "失败"}</summary>
        {row.reason && <p>{row.reason}</p>}
        {row.turns?.map((turn) => <p key={turn.index}>第 {turn.index + 1} 轮 · {turn.action} · {turn.rule_mode} {turn.rule_versions?.join("、")} {turn.failures.join("、")}</p>)}
      </details>)}</div>}
  </section>;
}
