import React, { useEffect, useState } from "react";
import { api, offline, request, states } from "./api.js";

const TRACE = [
  ["original_filename", "原文文件"],
  ["section_path", "章节"],
  ["page_pdf", "原文页码"],
  ["clause_no", "条款"],
  ["content_type", "内容类型"],
];
const CONTENT = {
  normative_text: "正文",
  table: "表格",
  formula: "公式",
  figure: "图",
  other: "其他",
};

function traceRows(metadata) {
  return TRACE.flatMap(([key, label]) => {
    const value = metadata[key];
    if (value == null || value === "") return [];
    if (key === "content_type")
      return [
        [
          label,
          String(value)
            .split(",")
            .map((item) => CONTENT[item] || item)
            .join("、"),
        ],
      ];
    return [[label, value]];
  });
}

function Chunks({ rows }) {
  return (
    <div className="chunks">
      {rows.map(({ text, metadata: m }, i) => (
        <article key={i}>
          <header>
            <strong>
              {i + 1}. {m.clause_no || m.section_path || "文档切片"}
            </strong>
            <small>
              {m.page_pdf ? "原文第 " + m.page_pdf + " 页 · " : ""}
              {text.length} 字符
            </small>
          </header>
          <div className="body">{text}</div>
          <dl>
            {traceRows(m).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </article>
      ))}
    </div>
  );
}
function filesFrom(rows) {
  const map = new Map();
  for (const row of rows) {
    if (row.state === "deleted") continue;
    const item = map.get(row.source) || {
      source: row.source,
      name: row.config.original_filename,
      count: 0,
      versions: [],
    };
    item.count += row.count || 0;
    item.versions.push(states[row.state] || row.state);
    map.set(row.source, item);
  }
  return [...map.values()];
}
function IndexedFiles({ revision }) {
  const [files, setFiles] = useState([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState("");
  useEffect(() => {
    if (offline) return;
    let stop = false;
    request(api + "/documents")
      .then((rows) => {
        if (!stop) setFiles(filesFrom(rows));
      })
      .catch((e) => {
        if (!stop) setError(e.message);
      });
    return () => {
      stop = true;
    };
  }, [revision]);
  async function remove(file) {
    if (!window.confirm("删除「" + file.name + "」的全部向量？")) return;
    setBusy(file.source);
    setError("");
    try {
      await request(api + "/documents/" + file.source, { method: "DELETE" });
      const rows = await request(api + "/documents");
      setFiles(filesFrom(rows));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }
  if (offline) return null;
  return (
    <section className="panel">
      <h3>已入库文件</h3>
      {error && <p className="warning">{error}</p>}
      {files.length ? (
        <ul className="indexed">
          {files.map((file) => (
            <li key={file.source}>
              <span>
                {file.name}
                <small>
                  {file.versions.join("、")} · {file.count} 条向量
                </small>
              </span>
              <button
                type="button"
                className="danger"
                disabled={busy === file.source}
                onClick={() => remove(file)}
              >
                删除向量
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p>还没有可删除的向量。</p>
      )}
    </section>
  );
}
export function ImportPage() {
  const [profiles, setProfiles] = useState([]),
    [profile, setProfile] = useState("ollama:bge-m3"),
    [strategies, setStrategies] = useState([
      { id: "structure", label: "按版面结构" },
      { id: "sentence", label: "按句子" },
      { id: "token", label: "按 Token" },
      { id: "markdown", label: "按 Markdown 标题" },
      { id: "sentence_window", label: "句子窗口" },
      { id: "hierarchical", label: "层次" },
      { id: "semantic", label: "语义" },
      { id: "semantic_merge", label: "语义双合并" },
    ]),
    [strategy, setStrategy] = useState("structure"),
    [size, setSize] = useState(512),
    [overlap, setOverlap] = useState(64);
  const [preview, setPreview] = useState(null),
    [created, setCreated] = useState(""),
    [revision, setRevision] = useState(0),
    [busy, setBusy] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    if (!offline)
      request(api + "/embedding-profiles")
        .then((items) => {
          setProfiles(items);
          setProfile((p) => items.find((x) => x.available)?.profile_id || p);
          setPreview(null);
        })
        .catch((e) => setError(e.message));
      request(api + "/limits")
        .then((limits) => {
          if (limits.chunk_strategies?.length) setStrategies(limits.chunk_strategies);
        })
        .catch((e) => setError(e.message));
  }, []);
  async function submit(e) {
    e.preventDefault();
    const mode = e.nativeEvent.submitter?.value || "preview";
    if (busy || offline) return;
    setBusy(mode);
    setError("");
    const form = new FormData(e.currentTarget);
    for (const [k, v] of [...form])
      if (v instanceof File && !v.name) form.delete(k);
    try {
      const r = await request(
        api + "/imports" + (mode === "preview" ? "/preview" : ""),
        { method: "POST", body: form },
      );
      if (mode === "preview") setPreview(r);
      else {
        setPreview(null);
        setCreated(r.job_id);
        setRevision((n) => n + 1);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }
  return (
    <>
      <div className="crumb">知识库 / 文档导入</div>
      <h1>导入文档</h1>
      <form
        onSubmit={submit}
        onChange={() => {
          setPreview(null);
          setCreated("");
        }}
      >
        <fieldset disabled={!!busy}>
          <section className="panel">
            <h3>原始文档</h3>
            <label className="upload">
              选择规程 PDF 或 Markdown
              <input required name="source_file" type="file" accept=".pdf,.md" />
            </label>
            <div className="fields">
              <label>
                文档标题
                <input
                  required
                  name="title"
                  defaultValue="城镇排水管道检测与评估技术规程"
                />
              </label>
              <label>
                规程版次
                <input required name="edition" defaultValue="CJJ 181-2012" />
              </label>
            </div>
          </section>
          <section className="panel">
            <h3>切片与向量模型</h3>
            <div className="fields">
              <label>
                切片策略
                <select
                  name="chunking.strategy"
                  value={strategy}
                  onChange={(e) => setStrategy(e.target.value)}
                >
                  {strategies.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
                {(strategy === "semantic" || strategy === "semantic_merge") && (
                  <small>这种切片会调用所选向量模型。</small>
                )}
              </label>
              <label>
                Embedding 模型
                <select
                  name="embedding_profile_id"
                  value={profile}
                  onChange={(e) => setProfile(e.target.value)}
                >
                  {profiles.length ? (
                    profiles.map((p) => (
                      <option key={p.profile_id} value={p.profile_id}>
                        {p.profile_id} ·{" "}
                        {p.available ? p.dimension + " 维" : p.health_status}
                      </option>
                    ))
                  ) : (
                    <option value={profile}>{profile}</option>
                  )}
                </select>
              </label>
              <label>
                切片长度（tokens）
                <select
                  name="chunking.chunk_size"
                  value={size}
                  onChange={(e) => {
                    const n = Number(e.target.value);
                    setSize(n);
                    if (overlap >= n / 2) setOverlap(64);
                  }}
                >
                  {[256, 512, 768, 1024].map((n) => (
                    <option key={n}>{n}</option>
                  ))}
                </select>
              </label>
              <label>
                重叠长度（tokens）
                <select
                  name="chunking.chunk_overlap"
                  value={overlap}
                  onChange={(e) => setOverlap(Number(e.target.value))}
                >
                  {[0, 32, 64, 128]
                    .filter((n) => n < size / 2)
                    .map((n) => (
                      <option key={n}>{n}</option>
                    ))}
                </select>
              </label>
            </div>
            <div className="actions">
              <small>预览不会写入向量库。</small>
              <button disabled={offline} value="preview">
                {busy === "preview" ? "正在预览…" : "预览切片"}
              </button>
              <button
                className="primary"
                disabled={
                  offline ||
                  !preview ||
                  !profiles.some((p) => p.profile_id === profile && p.available)
                }
                value="build"
              >
                {busy === "build" ? "正在提交…" : "创建导入任务"}
              </button>
            </div>
          </section>
        </fieldset>
      </form>
      {error && (
        <p className="warning" role="alert">
          {error}
        </p>
      )}
      <IndexedFiles revision={revision} />
      {created && (
        <section className="panel">
          <h3>导入任务已提交</h3>
          <p>任务号 {created}</p>
        </section>
      )}
      {preview && (
        <section className="panel">
          <h3>
            切片预览{" "}
            <small>
              共 {preview.chunks.length} 条
            </small>
          </h3>
          <Chunks rows={preview.chunks} />
        </section>
      )}
    </>
  );
}
