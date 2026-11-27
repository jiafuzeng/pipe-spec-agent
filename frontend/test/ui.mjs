import { Window } from "happy-dom";
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
const window = new Window({
  url: "http://localhost",
  settings: { enableJavaScriptEvaluation: true },
});
const html = readFileSync("dist/index.html", "utf8");
window.document.body.innerHTML = '<div id="root"></div>';
let messages = [];
let documents = [];
let approved = false;
let modelAvailable = false;
const chunks = [
  {
    text: "测试条款",
    metadata: {
      clause_no: "1.0.1",
      page_pdf: 2,
      original_filename: "test.pdf",
      edition: "CJJ 181-2012",
      section_path: "总则",
      content_type: "normative_text",
      source_hash: "abc123",
      docmind_layout_ids: "layout-1",
    },
  },
];
window.fetch = async (url, opts = {}) => {
  if (url.endsWith("/evaluations/rag?mode=hybrid")) return Response.json({detail:"暂无混合报告"}, {status:404});
  if (url.endsWith("/evaluations/rag?mode=bm25")) return Response.json(JSON.parse(readFileSync("../ragEval/bm25_scores.json", "utf8")));
  if (url.endsWith("/limits"))
    return Response.json({
      chunk_strategies: [
        "按版面结构",
        "按句子",
        "按 Token",
        "按 Markdown 标题",
        "句子窗口",
        "层次",
        "语义",
        "语义双合并",
      ].map((label, i) => ({
        id: ["structure", "sentence", "token", "markdown", "sentence_window", "hierarchical", "semantic", "semantic_merge"][i],
        label,
      })),
    });
  if (url.endsWith("embedding-profiles"))
    return Response.json([
      { profile_id: "ollama:bge-m3", available: modelAvailable, dimension: 1024, health_status: "请检查 Ollama 服务" },
    ]);
  if (url === "/api/v1/sessions") return Response.json({ session_id: "trial" });
  if (url === "/api/v1/sessions/trial") return Response.json({subjects: {}, messages: []});
  if (url.endsWith("/turns")) {
    const body = JSON.parse(opts.body);
    assert.equal(body.subject_id, "default");
    messages.push(body.message);
    return new Response(
      'event: plan_step\ndata: {"text":"检索条款"}\n\nevent: answer\ndata: {"text":"测试回答"}\n\n',
    );
  }
  if (opts.method === "DELETE" && url.includes("/documents/")) {
    documents.forEach((row) => {
      row.state = "deleted";
    });
    return Response.json({ status: "deleted" });
  }
  if (url.endsWith("/documents")) return Response.json(documents);
  if (url.endsWith("/imports/preview"))
    return Response.json({ total: chunks.length, chunks });
  if (url.endsWith("/imports")) {
    documents = [
      {
        id: "job1",
        source: "sha",
        created: "test",
        state: "built_pending_review",
        count: 1,
        config: {
          original_filename: "test.pdf",
          edition: "CJJ 181-2012",
          index_version: "v1",
          chunk_strategy: "structure",
          chunk_size: 512,
          chunk_overlap: 64,
        },
      },
    ];
    return Response.json({ job_id: "job1" });
  }
  if (url.includes("/chunks?")) return Response.json(chunks);
  if (url.includes("/approve?")) {
    assert.equal(new URL(url, "http://localhost").searchParams.get("actor"), "test-reviewer");
    assert.ok(url.includes("confirmed=true"));
    approved = true;
    documents[0].state = "active_approved";
    return Response.json({ status: "active_approved" });
  }
  throw Error("unexpected " + url);
};
window.TextDecoderStream = TextDecoderStream;
const entry = html.match(/<script[^>]+src="(\/assets\/[^"]+)"/)[1];
window.eval(readFileSync("dist" + entry, "utf8"));
const tick = () => new Promise((r) => setTimeout(r, 30));
await tick();
const doc = window.document;
assert.equal(doc.querySelectorAll(".examples button").length, 9);
doc.querySelectorAll(".examples button")[7].click();
await tick();
assert.match(doc.querySelector("textarea").value, /修复指数/);
assert.equal(messages.length, 0);
doc.querySelector(".composer .primary").click();
await tick();
assert.equal(messages.length, 1);
assert.match(doc.querySelector(".reply").textContent, /测试回答/);
window.location.hash = "import";
window.dispatchEvent(new window.Event("hashchange"));
await tick();
assert.equal(doc.querySelector("[name=source_file]").closest("[hidden]"), null);
assert.equal(doc.querySelector("[name=docmind_json]"), null);
assert.equal(doc.querySelector("[name=docmind_markdown]"), null);
assert.equal(doc.querySelector("a[href='#tasks']"), null);
assert.equal([...doc.querySelectorAll("nav a")].some((a) => a.textContent.includes("文档与审核")), false);
window.location.hash = "import";
window.dispatchEvent(new window.Event("hashchange"));
await tick();
const form = doc.querySelector("input[name=source_file]").form;
const file = new window.File(["test"], "test.pdf", { type: "application/pdf" });
const transfer = new window.DataTransfer();
transfer.items.add(file);
form.elements.source_file.files = transfer.files;
form.elements.source_file.dispatchEvent(
  new window.Event("change", { bubbles: true }),
);
await tick();
assert.equal(
  form.querySelector("[name='chunking.strategy']").options.length,
  8,
);
assert.equal(form.querySelector("[value=build]").disabled, true);
form.requestSubmit(form.querySelector("[value=preview]"));
await tick();
assert.match(doc.querySelector(".chunks").textContent, /1.0.1/);
assert.match(doc.querySelector(".chunks").textContent, /原文第 2 页/);
assert.match(doc.querySelector("main").textContent, /共 1 条/);
assert.doesNotMatch(
  doc.querySelector(".chunks").textContent,
  /SHA-256|uniqueId|文档标题|版次|印刷页|pageNum/,
);
assert.match(doc.querySelector(".chunks").textContent, /原文文件/);
assert.match(doc.querySelector(".chunks").textContent, /章节/);
assert.match(doc.querySelector(".chunks").textContent, /原文页码/);
assert.match(doc.querySelector(".chunks").textContent, /条款/);
assert.match(doc.querySelector(".chunks").textContent, /内容类型/);
assert.match(doc.querySelector(".chunks").textContent, /正文/);
assert.match(doc.querySelector(".chunks").textContent, /test\.pdf/);
assert.equal(form.querySelector("[value=build]").disabled, true);
assert.match(form.querySelector('[role=status]').textContent, /请检查 Ollama 服务/);
modelAvailable = true;
form.querySelector(".actions button[type=button]").click();
await tick();
assert.equal(form.querySelector("[value=build]").disabled, false);
form.requestSubmit(form.querySelector("[value=build]"));
await tick();
assert.match(doc.querySelector("main").textContent, /导入任务已提交/);
assert.match(doc.querySelector("main").textContent, /job1/);
await tick();
assert.match(doc.querySelector(".indexed").textContent, /test\.pdf/);
window.confirm = () => true;
const review = doc.querySelector(".indexed details");
review.querySelector("button").click();
await tick();
assert.match(review.querySelector(".chunks").textContent, /测试条款/);
const actor = review.querySelector("input");
const inputSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
inputSetter.call(actor, "test-reviewer");
actor.dispatchEvent(new window.Event("input", { bubbles:true }));
await tick();
[...review.querySelectorAll("button")].find((b) => b.textContent.includes("确认审核")).click();
await tick();
assert.equal(approved, true);
doc.querySelector(".indexed .danger").click();
await tick();
assert.match(doc.querySelector("main").textContent, /还没有可删除的向量/);
assert.equal(documents[0].state, "deleted");
assert.equal(doc.querySelector(".review"), null);
console.log(
  "PASS: React navigation, nine questions, SSE, import preview and task creation",
);
window.location.hash = "ragEval";
window.dispatchEvent(new window.Event("hashchange"));
await tick();
assert.match(doc.querySelector(".eval-page").textContent, /暂无混合报告/);
const mode = doc.querySelector(".eval-page select");
mode.value = "bm25";
mode.dispatchEvent(new window.Event("change", { bubbles: true }));
await tick();
assert.equal(doc.querySelectorAll(".eval-case").length, 30);
assert.match(doc.querySelector(".eval-case").textContent, /正文 100 分 · 引用 100 分/);
const filter = doc.querySelector("[aria-label=筛选评测题目]");
filter.value = "outside";
filter.dispatchEvent(new window.Event("change", { bubbles: true }));
await tick();
assert.equal(doc.querySelectorAll(".eval-case").length, 2);
assert.match(doc.querySelector(".eval-case").textContent, /库外题 · 不计分/);
await window.happyDOM.abort();
await window.close();
