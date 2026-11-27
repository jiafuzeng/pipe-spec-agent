import React, { useEffect, useState } from "react";
import { request } from "./api.js";

function listed(value) {
  if (value == null) return "";
  if (Array.isArray(value)) return value.map(listed).join("、");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Expect({ expect }) {
  if (!expect) return null;
  const rows = [
    ["动作", expect.action],
    ["工具次数", expect.tool_calls && listed(Object.entries(expect.tool_calls).map(([name, n]) => name + " × " + n))],
    ["引用其一", expect.citations_any_of && listed(expect.citations_any_of)],
    ["必须追问", expect.missing_parameters && listed(expect.missing_parameters)],
    ["追问分组", expect.missing_parameter_groups && expect.missing_parameter_groups.map((group) => group.id + "（" + listed(group.any_of) + "）").join("；")],
    ["计算值", expect.results && expect.results.map((row) => listed(row)).join("；")],
    ["曲线", expect.chart && expect.chart.points + " 个点"],
    ["拒答句", expect.refusal_text],
    ["事件", expect.events_include && listed(expect.events_include)],
  ].filter(([, value]) => value);
  return (
    <section>
      <h3>期望</h3>
      {rows.map(([label, value]) => <p key={label}><strong>{label}</strong> {value}</p>)}
    </section>
  );
}

function Turn({ turn }) {
  return (
    <article>
      <h3>第 {turn.index + 1} 轮 · {turn.passed ? "通过" : "失败"} · {turn.action}</h3>
      {turn.message && <p>{turn.message}</p>}
      <Expect expect={turn.expect} />
      <section>
        <h3>实际</h3>
        <p>规则 {turn.rule_mode}{turn.rule_versions?.length ? " · " + turn.rule_versions.join("、") : ""}</p>
        {turn.tools && Object.keys(turn.tools).length > 0 && <p>工具 {Object.entries(turn.tools).map(([name, n]) => name + " × " + n).join("、")}</p>}
        {turn.clarification && <p>追问 {listed(turn.clarification.fields)}{turn.clarification.groups?.length ? "；分组 " + turn.clarification.groups.map((group) => listed(group.any_of)).join("；") : ""}</p>}
        {turn.results?.map((row, i) => <p key={i}>计算结果 {row.type} = {row.value}{row.parameters ? " · " + listed(row.parameters) : ""}</p>)}
        {turn.charts?.map((chart, i) => <p key={i}>曲线 {chart.points} 个点</p>)}
        {turn.answer && <blockquote>{turn.answer}</blockquote>}
        {turn.citations?.map((item, i) => (
          <blockquote key={i}><strong>{item.clause}{item.page ? " · PDF 第 " + item.page + " 页" : ""}</strong><br />{item.quote}</blockquote>
        ))}
        {turn.failures?.map((fail) => <p key={fail} className="warning" role="alert">{fail}</p>)}
      </section>
    </article>
  );
}

export function AgentEval() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    request("/api/v1/evaluations/agent", { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setReport(data); })
      .catch((e) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, []);
  const summary = report?.summary;
  return (
    <div className="eval-page">
      <div className="crumb">评测 / Agent 评测</div>
      <div className="pagehead"><h1>Agent 评测</h1></div>
      {error && <p className="warning" role="alert">{error}</p>}
      {!report && !error && <p role="status">正在读取评测报告…</p>}
      {report && <>
        <p>{report.agent_entry} · 检索 {report.retrieval_mode} · 工具 {report.mode}</p>
        <div className="eval-metrics">
          {[
            ["通过", summary.passed + " / " + summary.total],
            ["动作", summary.action_pass_rate?.toFixed(3) ?? "—"],
            ["引用或拒答", summary.citation_pass_rate?.toFixed(3) ?? "—"],
            ["工具次数", summary.tool_constraint_pass_rate?.toFixed(3) ?? "—"],
          ].map(([label, value]) => <div key={label}><small>{label}</small><strong>{value}</strong></div>)}
        </div>
        <section className="panel">
          <h2>逐题结果</h2>
          <p>展开一题可核对题面、期望动作和工具、实际回答、引用、追问、计算值。检索是否找对原文不在这里判。</p>
          {report.results.map((row) => (
            <details key={row.id} className="eval-case">
              <summary>
                <small>{row.id}</small>
                <strong>{row.turns?.[0]?.message || row.reason || row.origin || ""}</strong>
                <span>{row.skipped ? "已跳过" : row.passed ? "通过" : "失败"}{row.origin ? " · " + row.origin : ""}</span>
              </summary>
              <div className="eval-detail">
                {row.reason && <p>{row.reason}</p>}
                {row.turns?.map((turn) => <Turn key={turn.index} turn={turn} />)}
              </div>
            </details>
          ))}
        </section>
      </>}
    </div>
  );
}
