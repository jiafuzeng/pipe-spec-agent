import React, { useCallback, useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import "@xyflow/react/dist/style.css";

const NODE_W = 168;
const NODE_H = 56;

/** Mirrors compile_graph() in app/agent/graph.py */
const GRAPH = {
  nodes: [
    { id: "START", title: "开始", kind: "terminal" },
    { id: "recognize", title: "意图识别", note: "四类分类" },
    { id: "rewrite", title: "问题改写", note: "检索查询", lane: "retrieve" },
    { id: "react", title: "create_agent", note: "检索+定稿", lane: "retrieve" },
    { id: "END", title: "结束", kind: "terminal" },
  ],
  edges: [
    ["START", "recognize"],
    ["recognize", "rewrite"],
    ["recognize", "END"],
    ["rewrite", "react"],
    ["react", "END"],
  ],
};

function layoutGraph(direction = "TB") {
  const g = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: direction,
    nodesep: 48,
    ranksep: 64,
    marginx: 24,
    marginy: 24,
  });

  const rawNodes = GRAPH.nodes.map((node) => ({
    id: node.id,
    type: "topology",
    data: {
      title: node.title,
      name: node.id,
      note: node.note || "",
      kind: node.kind || "step",
      lane: node.lane || "",
    },
    position: { x: 0, y: 0 },
    sourcePosition: direction === "LR" ? "right" : "bottom",
    targetPosition: direction === "LR" ? "left" : "top",
  }));
  const rawEdges = GRAPH.edges.map(([source, target], index) => ({
    id: `${source}->${target}-${index}`,
    source,
    target,
    type: "smoothstep",
    animated:
      source === "rewrite" && target === "react",
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18, color: "#176954" },
    style: { stroke: "#176954", strokeWidth: 1.6 },
  }));

  rawNodes.forEach((node) => g.setNode(node.id, { width: NODE_W, height: NODE_H }));
  rawEdges.forEach((edge) => g.setEdge(edge.source, edge.target));
  dagre.layout(g);

  const nodes = rawNodes.map((node) => {
    const pos = g.node(node.id);
    return {
      ...node,
      position: {
        x: pos.x - NODE_W / 2,
        y: pos.y - NODE_H / 2,
      },
    };
  });
  return { nodes, edges: rawEdges };
}

function TopologyNode({ data, sourcePosition, targetPosition }) {
  return (
    <div className={"topo-node" + (data.kind === "terminal" ? " terminal" : "") + (data.lane ? " " + data.lane : "")}>
      <Handle type="target" position={targetPosition || Position.Top} className="topo-handle" />
      <strong>{data.title}</strong>
      <small>{data.note ? data.name + " · " + data.note : data.name}</small>
      <Handle type="source" position={sourcePosition || Position.Bottom} className="topo-handle" />
    </div>
  );
}

const nodeTypes = { topology: TopologyNode };

function FlowCanvas() {
  const initial = useMemo(() => layoutGraph("TB"), []);
  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);

  const onLayout = useCallback(
    (direction) => {
      const next = layoutGraph(direction);
      setNodes(next.nodes);
      setEdges(next.edges);
    },
    [setNodes, setEdges],
  );

  return (
    <div className="topo-canvas">
      <div className="topo-toolbar">
        <button type="button" onClick={() => onLayout("TB")}>
          纵向排布
        </button>
        <button type="button" onClick={() => onLayout("LR")}>
          横向排布
        </button>
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        fitViewOptions={{ padding: 0.16 }}
        minZoom={0.35}
        maxZoom={1.6}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={18} color="#d7e4dc" />
        <MiniMap
          pannable
          zoomable
          nodeColor={(node) =>
            node.data?.kind === "terminal" ? "#176954" : "#ffffff"
          }
        />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

export function Graph() {
  return (
    <figure className="graph topology">
      <figcaption>
        使用 <code>@xyflow/react</code> + <code>dagre</code> 自动排版，边关系对齐
        <code>compile_graph()</code>。意图四类：条文检索、方法/方案对比、计算问数与可视化、闲聊；闲聊直接结束。
      </figcaption>
      <ReactFlowProvider>
        <FlowCanvas />
      </ReactFlowProvider>
    </figure>
  );
}
