export const examples = [
  "编制目的和适用范围是什么？",
  "解释 CCTV、QV、声纳，并比较适用条件。",
  "结构性和功能性普查的周期是多少？哪些情况应缩短？",
  "比较 CCTV、QV、声纳、人员进入和潜水的现场条件、安全、效率及缺陷识别能力。",
  "声纳能否单独判定结构性缺陷？何时检查检查井，查哪些项目？",
  "DN800 污水管，埋深 4.5 m，水位 60%，积泥较厚，次干道且不能停水降水，应如何检测？",
  "说明 RI 与 K 的分档，固定其余参数，画出 K=0、3、6、10 的 RI 曲线。",
  "帮我算一下这条管道的修复指数 RI。",
  "DN1200，主干道 K=6，管龄 35 年，土质流砂，两处重度错口各 5 分，间距 1.2 m。计算 RI，并画 T=0、6、8、10 的曲线。",
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
      if (type && data)
        onEvent({ type: type.slice(7), data: JSON.parse(data.slice(6)) });
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
