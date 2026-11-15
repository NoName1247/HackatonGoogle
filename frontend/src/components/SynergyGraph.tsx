"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Background, Controls, Edge, Node, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

interface SynergyGraphProps {
  projectDetail: any;
  synergyGraph: any;
  viewMode: "SYNERGY" | "LINEAGE";
}

export default function SynergyGraph({
  projectDetail,
  synergyGraph,
  viewMode,
}: SynergyGraphProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const { nodes, edges } = useMemo(() => {
    const nList: Node[] = [];
    const eList: Edge[] = [];

    if (!projectDetail) return { nodes: nList, edges: eList };

    if (viewMode === "LINEAGE") {
      const lGraph = projectDetail.lineage_graph || { nodes: [], edges: [] };
      const rawNodes: any[] = lGraph.nodes || [];
      const rawEdges: any[] = lGraph.edges || [];

      rawNodes.forEach((nd, idx) => {
        const gen = nd.generation || idx + 1;
        nList.push({
          id: nd.project_id,
          position: { x: (gen - 1) * 320 + 40, y: 80 + (idx % 2) * 110 },
          data: {
            label: `[Gen ${gen} | ${nd.year}] ${nd.title.slice(0, 48)}... (${nd.author} — Score: ${nd.final_handover_score})`,
          },
          style: {
            background: nd.project_id === projectDetail.project_id ? "#064e3b" : "#0f172a",
            color: "#f8fafc",
            border:
              nd.project_id === projectDetail.project_id
                ? "2px solid #10b981"
                : "1px solid #334155",
            borderRadius: "10px",
            padding: "10px",
            width: 260,
            fontSize: "11px",
            fontFamily: "monospace",
          },
        });
      });

      rawEdges.forEach((ed, idx) => {
        eList.push({
          id: `lin-e-${idx}`,
          source: ed.parent_project_id,
          target: ed.child_project_id,
          animated: true,
          label: `FORKED (${ed.inherited_asset_type})`,
          style: { stroke: "#10b981", strokeWidth: 2 },
          labelStyle: { fill: "#a7f3d0", fontSize: 10 },
        });
      });

      return { nodes: nList, edges: eList };
    }

    // Default: ASYMMETRIC SYNERGY GRAPH (Demand A -> Supply B + External HF Fallbacks)
    const rootId = projectDetail.project_id;
    nList.push({
      id: rootId,
      position: { x: 30, y: 120 },
      data: {
        label: `🔴 CONSUMER (DEMAND): ${projectDetail.title.slice(0, 52)} (${projectDetail.department})`,
      },
      style: {
        background: "#3b0764",
        color: "#f8fafc",
        border: "2px solid #a855f7",
        borderRadius: "10px",
        padding: "10px",
        width: 260,
        fontSize: "11px",
        fontFamily: "monospace",
      },
    });

    const matches: any[] = synergyGraph?.internal_matches || [];
    matches.forEach((m, idx) => {
      const targetId = `donor-${m.bridge_id}-${idx}`;
      const scorePct = Math.round((m.formula?.synergy_score || 0.85) * 100);
      nList.push({
        id: targetId,
        position: { x: 420, y: 30 + idx * 115 },
        data: {
          label: `🟢 DONOR SUPPLY (${scorePct}% MATCH): ${m.donor_title.slice(0, 48)} [${m.donor_department}]`,
        },
        style: {
          background: "#064e3b",
          color: "#ecfdf5",
          border: "2px solid #10b981",
          borderRadius: "10px",
          padding: "10px",
          width: 290,
          fontSize: "11px",
          fontFamily: "monospace",
        },
      });

      eList.push({
        id: `syn-e-${idx}`,
        source: rootId,
        target: targetId,
        animated: true,
        label: `S = ${m.formula?.synergy_score} (Env=${m.formula?.m_envelope})`,
        style: { stroke: "#10b981", strokeWidth: 2 },
        labelStyle: { fill: "#6ee7b7", fontSize: 10 },
      });
    });

    const fallbacks: any[] = synergyGraph?.external_fallbacks || [];
    fallbacks.slice(0, 2).forEach((fb, idx) => {
      const fbId = `hf-${idx}`;
      nList.push({
        id: fbId,
        position: { x: 420, y: 30 + (matches.length + idx) * 115 },
        data: {
          label: `🤗 EXTERNAL FALLBACK (${fb.source_platform}): ${fb.title}`,
        },
        style: {
          background: "#1e293b",
          color: "#fde68a",
          border: "1px dashed #f59e0b",
          borderRadius: "10px",
          padding: "10px",
          width: 290,
          fontSize: "11px",
          fontFamily: "monospace",
        },
      });
      eList.push({
        id: `fb-e-${idx}`,
        source: rootId,
        target: fbId,
        label: "Cold-Start Fallback",
        style: { stroke: "#f59e0b", strokeDasharray: "4 4" },
      });
    });

    return { nodes: nList, edges: eList };
  }, [projectDetail, synergyGraph, viewMode]);

  if (!mounted) {
    return (
      <div
        className="xs mu mono"
        style={{ height: 420, width: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg)" }}
      >
        Initializing Interactive Graph Engine...
      </div>
    );
  }

  return (
    <div style={{ height: 420, width: "100%", background: "var(--bg)" }}>
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Background color="#1e293b" gap={18} />
        <Controls />
      </ReactFlow>
    </div>
  );
}

