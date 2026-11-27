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
      jobs: [],
    };
    item.count += row.count || 0;
    item.jobs.push(row);
    item.versions.push(states[row.state] || row.state);
    map.set(row.source, item);
  }
  return [...map.values()];
}
function Review({ job, refresh }) {
  const [actor, setActor] = useState(""), [rows, setRows] = useState(null),
    [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const base = api + "/documents/" + job.source;
  async function more() {
    setBusy(true);
    try {
      const page = await request(base + "/chunks?job_id=" + job.id + "&offset=" + (rows?.length || 0) + "&limit=10");
      setRows([...(rows || []), ...page]);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function approve() {
    if (!window.confirm("确认已逐项对照原文，发布这个索引版本？")) return;
    setBusy(true);
    try {
      const params = new URLSearchParams({job_id:job.id, actor, confirmed:"true"});
      await request(base + "/approve?" + params, {method:"POST"});
      await refresh();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <details><summary>审核版本 {job.id.slice(0,8)}</summary>
    <a href={base + "/original?job_id=" + job.id} target="_blank" rel="noreferrer">打开原始文件</a>
    {rows && <Chunks rows={rows} />}
    {(!rows || rows.length < job.count) && <button onClick={more} disabled={busy}>查看切片</button>}
    <label>审核人<input value={actor} onChange={(e) => setActor(e.target.value)} /></label>
    <button disabled={busy || !actor.trim() || !rows?.length} onClick={approve}>确认审核并发布</button>
    {error && <p role="alert">{error}</p>}
  </details>;
}
function IndexedFiles({ revision }) {
  const [files, setFiles] = useState([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState("");
  useEffect(() => {
    if (offline) return;
    let stop = false, timer;
    async function load() {
      try {
        const rows = await request(api + "/documents");
        if (stop) return;
        setFiles(filesFrom(rows));
        if (rows.some((row) => ["queued","parsing","chunking","embedding"].includes(row.state))) {
          timer = setTimeout(load, 1000);
        }
      } catch (e) { if (!stop) setError(e.message); }
    }
    load();
    return () => { stop = true; clearTimeout(timer); };
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
              {file.jobs.filter((j) => j.state === "failed").map((j) => <small key={j.id} role="alert">{j.error || "构建失败，请重新提交原始文件。"}</small>)}
              {file.jobs.filter((j) => j.state === "built_pending_review" && j.config.original_filename.toLowerCase().endsWith(".pdf")).map((j) =>
                <Review key={j.id} job={j} refresh={async () => setFiles(filesFrom(await request(api + "/documents")))} />)}
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
  const [isPdf, setIsPdf] = useState(false);
  const [preview, setPreview] = useState(null),
    [created, setCreated] = useState(""),
    [revision, setRevision] = useState(0),
    [busy, setBusy] = useState(""),
    [error, setError] = useState("");
  const [checking, setChecking] = useState(false);
  const [profileError, setProfileError] = useState("");
  const selected = profiles.find((p) => p.profile_id === profile);
  async function checkProfiles() {
    setChecking(true);
    setProfileError("");
    try {
      const items = await request(api + "/embedding-profiles");
      setProfiles(items);
      if (!items.some((p) => p.profile_id === profile && p.available)) {
        const available = items.find((p) => p.available);
        if (available && available.profile_id !== profile) {
          setProfile(available.profile_id);
          setPreview(null);
        }
      }
    } catch (e) {
      setProfiles([]);
      setProfileError("无法获取模型状态，请检查后端连接。" + e.message);
    } finally {
      setChecking(false);
    }
  }
  useEffect(() => {
    if (offline) return;
    checkProfiles();
    request(api + "/limits")
      .then((limits) => {
        if (limits.chunk_strategies?.length) setStrategies(limits.chunk_strategies);
      })
      .catch((e) => setError(e.message));
  }, []);
  const modelHint = checking
    ? "正在检查向量模型连接…"
    : profileError || (!selected?.available && (selected?.health_status || "没有可用的向量模型。"));
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
              <input required name="source_file" type="file" accept=".pdf,.md"
                onChange={(e) => setIsPdf(/\.pdf$/i.test(e.target.files[0]?.name || ""))} />
            </label>
            {isPdf && <details><summary>关联已有 DocMind 解析文件</summary>
              <label>版面 JSON<input type="file" name="docmind_json" accept=".json" /></label>
              <label>解析 Markdown<input type="file" name="docmind_markdown" accept=".md" /></label>
            </details>}
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
              <small role="status">
                {offline ? "请通过前端服务打开此页面。" :
                  [!preview && "请先预览切片。", modelHint].filter(Boolean).join(" ") || "切片已预览，可以创建导入任务。"}
              </small>
              {!offline && modelHint && (
                <button type="button" disabled={checking} onClick={checkProfiles}>重新检测模型</button>
              )}
              <button disabled={offline} value="preview">
                {busy === "preview" ? "正在预览…" : "预览切片"}
              </button>
              <button
                className="primary"
                disabled={
                  offline ||
                  !preview ||
                  checking || !selected?.available
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
