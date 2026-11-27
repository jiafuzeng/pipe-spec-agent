import React from "react";

const W = 148;
const H = 52;

function box(cx, cy, title, name, note = "", terminal = false) {
  return { cx, cy, x: cx - W / 2, y: cy - H / 2, title, name, note, terminal };
}

const nodes = [
  box(420, 40, "开始", "START", "", true),
  box(420, 132, "规划", "plan"),
  box(176, 248, "检索", "retrieve"),
  box(664, 248, "规则", "schema", "可结束"),
  box(176, 356, "核对", "verify", "可结束"),
  box(664, 356, "收参", "collect", "可结束"),
  box(176, 464, "回答", "answer", "可结束"),
  box(664, 464, "计算", "calculate", "可结束"),
  box(664, 572, "绘图", "plot"),
  box(420, 572, "结束", "END", "", true),
];

const solid = [
  "M 420 66 L 420 106",
  "M 390 158 C 300 190, 220 200, 176 222",
  "M 450 158 C 540 190, 620 200, 664 222",
  "M 176 274 L 176 330",
  "M 176 382 L 176 438",
  "M 664 274 L 664 330",
  "M 664 382 L 664 438",
  "M 664 490 L 664 546",
  "M 590 572 L 494 572",
  "M 176 490 C 176 540, 300 572, 346 572",
];

export function Graph() {
  return (
    <figure className="graph">
      <figcaption>
        LangGraph 对话流程。标了「可结束」的节点可以直接进入结束。回答之后若还要计算，会回到规则。中断后从检查点回到当时的节点。
      </figcaption>
      <svg viewBox="0 0 840 630" role="img" aria-label="LangGraph 对话流程">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1.2 L 8 5 L 0 8.8 z" fill="#176954" />
          </marker>
        </defs>
        {solid.map((d) => <path key={d} d={d} className="edge" markerEnd="url(#arrow)" />)}
        <path d="M 250 464 C 360 464, 480 248, 590 248" className="edge" markerEnd="url(#arrow)" />
        <text className="label" x="250" y="196" textAnchor="middle">问答</text>
        <text className="label" x="590" y="196" textAnchor="middle">计算</text>
        <text className="label" x="420" y="360" textAnchor="middle">继续计算</text>
        {nodes.map((node) => (
          <g key={node.name}>
            <rect x={node.x} y={node.y} width={W} height={H} rx="8" className={node.terminal ? "terminal" : "step"} />
            <text x={node.cx} y={node.cy - 2} textAnchor="middle">{node.title}</text>
            <text className="sub" x={node.cx} y={node.cy + 16} textAnchor="middle">{node.note ? node.name + " · " + node.note : node.name}</text>
          </g>
        ))}
      </svg>
    </figure>
  );
}
