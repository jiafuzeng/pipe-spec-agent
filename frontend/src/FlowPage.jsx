import React from "react";
import { Graph } from "./Graph.jsx";

export function FlowPage() {
  return (
    <div className="eval-page flow-page">
      <div className="crumb">工作台 / 流程图拓扑</div>
      <div className="pagehead">
        <h1>流程图拓扑</h1>
      </div>
      <p className="flow-lead">
        用 React Flow + dagre 按 <code>compile_graph()</code> 自动排布；可拖拽节点、缩放画布，支持纵向 / 横向切换。
      </p>
      <Graph />
    </div>
  );
}
