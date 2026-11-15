"use client";

import React, { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";

export function TreemapChart({
  treemapHierarchy,
  onSelectCluster,
  height = 420,
}: {
  treemapHierarchy: any[];
  onSelectCluster: (cluster: any) => void;
  height?: number;
}) {
  const treemapRef = useRef<HTMLDivElement | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted || !treemapRef.current) return;
    const chart = echarts.init(treemapRef.current);

    const treeData = (treemapHierarchy || []).map((macro) => ({
      name: `${macro.macro_category} (${macro.total_projects_blocked})`,
      value: Math.max(1, macro.total_projects_blocked),
      children: (macro.clusters || []).map((cl: any) => ({
        name: `${cl.cluster_label}\n[${cl.affected_projects_count} theses]`,
        value: Math.max(1, cl.affected_projects_count),
        clusterData: cl,
      })),
    }));

    chart.setOption({
      backgroundColor: "transparent",
      tooltip: {
        formatter: (info: any) => {
          const cl = info.data?.clusterData;
          if (!cl) return `<div style="font-size:12px"><b>${info.name}</b></div>`;
          return `<div style="font-size:12px;max-width:320px;white-space:normal;">
            <b>${cl.cluster_label}</b><br/>
            Macro: ${cl.macro_category}<br/>
            Blocked Theses: <b>${cl.affected_projects_count}</b> across <b>${cl.affected_departments_count}</b> depts<br/>
            <span style="color:#34d399">${cl.estimated_unlock_roi}</span>
          </div>`;
        },
      },
      series: [
        {
          type: "treemap",
          roam: false,
          nodeClick: false,
          breadcrumb: { show: true, itemStyle: { color: "#1e293b" } },
          label: { show: true, formatter: "{b}", fontSize: 11 },
          upperLabel: { show: true, height: 24, color: "#fff", backgroundColor: "#0f172a" },
          itemStyle: { borderColor: "#0f172a", borderWidth: 2, gapWidth: 2 },
          data: treeData,
        },
      ],
    });

    chart.on("click", (params: any) => {
      if (params.data?.clusterData) {
        onSelectCluster(params.data.clusterData);
      }
    });

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(treemapRef.current);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
  }, [mounted, treemapHierarchy]);

  return <div ref={treemapRef} style={{ width: "100%", height }} />;
}

export function GoldenBubbleChart({
  goldenReserveMatrix,
  onSelectProjectBubble,
  height = 420,
}: {
  goldenReserveMatrix: any[];
  onSelectProjectBubble: (projectId: string) => void;
  height?: number;
}) {
  const bubbleRef = useRef<HTMLDivElement | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted || !bubbleRef.current) return;
    const chart = echarts.init(bubbleRef.current);

    const unclaimedHighPotential: any[] = [];
    const goldStandardDonors: any[] = [];
    const activeFollowed: any[] = [];

    (goldenReserveMatrix || []).forEach((pt) => {
      const item = [pt.asset_value_x, pt.horizon_score_y, pt.final_handover_score, pt.title, pt.department, pt.project_id];
      if (pt.is_pure_supply_donor) {
        goldStandardDonors.push(item);
      } else if (pt.has_active_followers) {
        activeFollowed.push(item);
      } else {
        unclaimedHighPotential.push(item);
      }
    });

    chart.setOption({
      backgroundColor: "transparent",
      grid: { top: 35, right: 25, bottom: 40, left: 45 },
      legend: {
        top: 4,
        textStyle: { color: "#cbd5e1", fontSize: 11 },
        data: ["Unclaimed High-Potential (Red Alert)", "TRL 6-7 Gold Donors", "Active Relay"],
      },
      tooltip: {
        formatter: (param: any) => {
          const d = param.data;
          return `<div style="font-size:12px;max-width:280px;white-space:normal;">
            <b>${d[3]}</b><br/>
            ${d[4]}<br/>
            Asset Value (X): <b>${d[0]}/50</b> | Horizon (Y): <b>${d[1]}/30</b><br/>
            Handover Score: <b>${d[2]}/100</b>
          </div>`;
        },
      },
      xAxis: {
        name: "Saved Asset Value (Code+Data*Decay)",
        nameLocation: "middle",
        nameGap: 25,
        min: 0,
        max: 52,
        axisLabel: { color: "#94a3b8" },
        splitLine: { lineStyle: { color: "#1e293b" } },
      },
      yAxis: {
        name: "Roadmap / Maturity (0-30)",
        min: 0,
        max: 32,
        axisLabel: { color: "#94a3b8" },
        splitLine: { lineStyle: { color: "#1e293b" } },
      },
      series: [
        {
          name: "Unclaimed High-Potential (Red Alert)",
          type: "scatter",
          symbolSize: (data: any) => Math.max(10, (data[2] || 50) / 4.2),
          itemStyle: { color: "#f43f5e", opacity: 0.85 },
          data: unclaimedHighPotential,
        },
        {
          name: "TRL 6-7 Gold Donors",
          type: "scatter",
          symbolSize: (data: any) => Math.max(12, (data[2] || 80) / 3.8),
          itemStyle: { color: "#eab308", opacity: 0.95 },
          data: goldStandardDonors,
        },
        {
          name: "Active Relay",
          type: "scatter",
          symbolSize: (data: any) => Math.max(10, (data[2] || 60) / 4.2),
          itemStyle: { color: "#10b981", opacity: 0.85 },
          data: activeFollowed,
        },
      ],
    });

    chart.on("click", (params: any) => {
      const pid = params.data?.[5];
      if (pid) onSelectProjectBubble(pid);
    });

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(bubbleRef.current);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
  }, [mounted, goldenReserveMatrix]);

  return <div ref={bubbleRef} style={{ width: "100%", height }} />;
}
