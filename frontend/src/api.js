export const examples = [
  "CJJ 181—2012 的编制目的与适用范围是什么？",
  "CCTV、QV、声纳三种检测方式的官方术语定义分别是什么？各自的适用条件有何差异？",
  "管道结构性缺陷与功能性缺陷的普查周期分别是多久？哪些情形下应缩短检测周期？",
  "从适用管径与水位条件、可识别缺陷类型、检测效率与安全风险、对现场配合的要求四个维度，列表对比 CCTV、QV、声纳、人工下井、潜水五种检测方式，并给出选择结论。",
  "声纳检测为何不能单独作为结构性缺陷的判定依据？检查井检测应安排在管道检测之前还是之后？检查井的核心检查项目有哪些？",
  "场景分析与方案规划：某 DN800 混凝土污水管，埋深约 4.5 m，管内水位约 60%，积泥较厚，位于城市次干道，现场不具备停水降水条件。请 Agent 自主规划检测方案：先判断信息是否充分并追问缺失条件，再给出推荐的检测方式与设备组合、检测顺序、安全措施及选择理由，均标注规程依据。",
];
export const api = "/api/v1/knowledge";
export const offline = location.protocol === "file:";
export function listSessions() {
  return request("/api/v1/sessions");
}
export function renameSession(id, title) {
  return request("/api/v1/sessions/" + id, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}
export async function deleteSession(id) {
  const response = await fetch("/api/v1/sessions/" + id, { method: "DELETE" });
  if (!response.ok) throw new Error("删除失败（" + response.status + "）");
}
export async function request(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : "请求失败（" + response.status + "）",
    );
  }
  return response.json();
}
export async function streamTurn(session, message, onEvent, subject = "default") {
  const res = await fetch("/api/v1/sessions/" + session + "/turns", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, subject_id: subject }),
  });
  if (res.status === 404) return false;
  if (!res.ok) throw new Error("问答请求失败（" + res.status + "）");
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    buffer += (value || "").replaceAll("\r", "");
    let end;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const lines = buffer.slice(0, end).split("\n");
      buffer = buffer.slice(end + 2);
      const type = lines.find((line) => line.startsWith("event: "));
      const data = lines.find((line) => line.startsWith("data: "));
      if (type && data) {
        const event = { type: type.slice(7), data: JSON.parse(data.slice(6)) };
        onEvent(event);
        // Let React paint partial answers instead of batching a whole burst.
        if (event.type === "answer" && event.data?.partial === true) {
          await new Promise((resolve) => requestAnimationFrame(resolve));
        }
      }
    }
    if (done) return true;
  }
}
export const states = {
  queued: "排队中",
  parsing: "解析中",
  chunking: "切片中",
  embedding: "向量化中",
  built_pending_review: "待审核",
  active_approved: "已发布",
  superseded: "历史版本",
  failed: "失败",
  deleted: "已删除",
};
