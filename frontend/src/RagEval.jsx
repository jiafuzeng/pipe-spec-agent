import React, { useEffect, useState } from "react";
import { api, request } from "./api.js";

function CaseResult({ row }) {
  return (
    <details className="eval-case">
      <summary>
        <small>{row.id}</small>
        <strong>{row.query}</strong>
        <span>{row.score == null ? "库外题 · 不计分" :
          "正文 " + row.evidence_score + " 分 · 引用 " + row.score + " 分"}</span>
      </summary>
      <div className="eval-detail">
        <h3>标注证据</h3>
        {row.matches.length === 0 && <p>验证集未标注支持该问题的规程依据。</p>}
        {row.matches.map((m, i) => (
          <section key={i}>
            <strong>{m.clause} · PDF 第 {m.page_pdf} 页</strong>
            <p>正文 {m.rank ? "第 " + m.rank + " 名" : "未命中"} · 引用 {m.citation_rank ? "第 " + m.citation_rank + " 名" : "未命中"}</p>
            <blockquote>{m.quote}</blockquote>
          </section>
        ))}
        <h3>实际检索结果（Top 5）</h3>
        {row.top5.length === 0 && <p>未返回候选。</p>}
        {row.top5.map((hit, i) => (
          <details key={hit.id}>
            <summary>第 {i + 1} 名 · {hit.clause || "条款未知"} · {hit.page == null ? "页码未知" : "PDF 第 " + hit.page + " 页"}</summary>
            {hit.retrieval_sources && <p>召回来源 {hit.retrieval_sources.join("、")}{hit.reranker_score != null && " · 重排分 " + hit.reranker_score.toFixed(3)}</p>}
            {hit.citation_spans?.length ? hit.citation_spans.map((span, k) => (
              <blockquote key={k}><strong>{span.clause} · PDF 第 {span.page ?? "未知"} 页</strong><br />{span.quote}</blockquote>
            )) : <blockquote>{hit.quote || hit.id}</blockquote>}
          </details>
        ))}
      </div>
    </details>
  );
}

export function RagEval() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [filter, setFilter] = useState("all");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setReport(null);
    setError("");
    request(api + "/rag-eval?mode=" + mode, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setReport(data); })
      .catch((e) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [revision, mode]);

  const rows = report?.results.filter((row) =>
    filter === "all" || (filter === "outside" ? row.score == null :
      row.score != null && row.score < 100)) || [];
  const summary = report?.summary;
  return (
    <div className="eval-page">
      <div className="crumb">知识库 / RAG 评测</div>
      <div className="pagehead"><h1>RAG 检索评测</h1>
        <button onClick={() => setRevision(n => n + 1)}>刷新报告</button>
      </div>
      <label>检索方式 <select value={mode} onChange={e => setMode(e.target.value)}>
        <option value="hybrid">多路召回 + 相关性重排</option>
        <option value="bm25">BM25 基线</option>
      </select></label>
      {error && <p className="warning" role="alert">{error}</p>}
      {!report && !error && <p role="status">正在读取评测报告…</p>}
      {report && <>
        <p>{report.mode === "offline_bm25" ? "离线 BM25" : report.mode === "offline_hybrid" ? "指定索引混合检索" : "已发布索引混合检索"}{report.reranker_model && " · " + report.reranker_model} · {report.dataset} · 共 {report.results.length} 题</p>
        <div className="eval-metrics">
          {[
            ["正文全部命中", summary.all_evidence_at_5 + " / " + summary.answerable],
            ["引用全部正确", summary.all_citations_at_5 + " / " + summary.answerable],
            ["首个命中倒数排名 MRR@5", summary.mrr_at_5?.toFixed(3) ?? "—"],
            ["返回候选的库外题", summary.negative_queries_with_candidates + " / " + (report.results.length - summary.answerable)],
          ].map(([label, value]) => <div key={label}><small>{label}</small><strong>{value}</strong></div>)}
        </div>
        <section className="panel">
          <div className="pagehead"><h2>逐题结果</h2>
            <select aria-label="筛选评测题目" value={filter} onChange={e => setFilter(e.target.value)}>
              <option value="all">全部题目</option><option value="incomplete">引用未满分</option><option value="outside">库外题</option>
            </select>
          </div>
          <p>正文得分按前五条结果覆盖的标注引文计算。引用得分还要求同一结果的条款和 PDF 页序正确。</p>
          {rows.map(row => <CaseResult key={row.id} row={row} />)}
          {!rows.length && <p>当前筛选下没有题目。</p>}
        </section>
      </>}
    </div>
  );
}
