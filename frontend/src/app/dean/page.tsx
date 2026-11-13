"use client";

import React, { useEffect, useState } from "react";
import DeanCharts from "@/components/DeanCharts";
import { executeDeanActionApi, fetchDeanAnalyticsApi } from "@/lib/api_and_sse";
import { useHorizonStore } from "@/lib/store";

export default function Mode3DeanDashboardPage() {
  const { selectedTopicIds, toggleTopicSelection, setSelectedTopicIds } = useHorizonStore();
  const [analytics, setAnalytics] = useState<any | null>(null);
  const [selectedCluster, setSelectedCluster] = useState<any | null>(null);
  const [activeTab, setActiveTab] = useState<"TOPICS" | "TRL_SHOWCASE" | "DOMAINS">("TOPICS");
  const [exportModalDoc, setExportModalDoc] = useState<{ title: string; md: string } | null>(null);
  const [busyAction, setBusyAction] = useState(false);

  const loadAnalytics = async () => {
    const data = await fetchDeanAnalyticsApi();
    setAnalytics(data);
    if (data?.treemap_hierarchy?.[0]?.clusters?.[0] && !selectedCluster) {
      setSelectedCluster(data.treemap_hierarchy[0].clusters[0]);
    }
    if (data?.golden_reserve_matrix && selectedTopicIds.length === 0) {
      const topIds = data.golden_reserve_matrix
        .slice(0, 10)
        .map((x: any) => x.project_id);
      setSelectedTopicIds(topIds);
    }
  };

  useEffect(() => {
    loadAnalytics();
  }, []);

  const handleExportVkrBank = async () => {
    setBusyAction(true);
    try {
      const res = await executeDeanActionApi({
        action_type: "export_vkr_bank",
        project_ids: selectedTopicIds,
        academic_year_target: "2026/2027",
      });
      setExportModalDoc({ title: res.document_title, md: res.markdown_content });
    } finally {
      setBusyAction(false);
    }
  };

  const handleExportGrantMemo = async (clusterId: string) => {
    setBusyAction(true);
    try {
      const res = await executeDeanActionApi({
        action_type: "export_grant_justification",
        cluster_id: clusterId,
      });
      setExportModalDoc({ title: res.document_title, md: res.markdown_content });
    } finally {
      setBusyAction(false);
    }
  };

  const handleApproveDomain = async (domainId: string) => {
    setBusyAction(true);
    try {
      await executeDeanActionApi({
        action_type: "approve_domain",
        domain_id: domainId,
      });
      await loadAnalytics();
    } finally {
      setBusyAction(false);
    }
  };

  if (!analytics) {
    return (
      <div className="p-8 text-center text-xs font-mono text-slate-400">
        Loading Dean&apos;s R&D Resource Analytics & HDBSCAN Clusters...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/80">
          <div className="text-[11px] font-mono text-slate-400">AUDITED THESES IN CORPUS</div>
          <div className="text-2xl font-extrabold text-white mt-1">{analytics.total_projects}</div>
        </div>
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/80">
          <div className="text-[11px] font-mono text-emerald-400">HIGH-POTENTIAL RELAY POOL</div>
          <div className="text-2xl font-extrabold text-emerald-300 mt-1">
            {analytics.relay_candidates_count}
          </div>
        </div>
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/80">
          <div className="text-[11px] font-mono text-amber-400">🚀 TRL 6–7 READY FOR INDUSTRY</div>
          <div className="text-2xl font-extrabold text-amber-300 mt-1">
            {analytics.gold_standard_trl_count}
          </div>
        </div>
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/80">
          <div className="text-[11px] font-mono text-indigo-400">HDBSCAN BOTTLENECK CLUSTERS</div>
          <div className="text-2xl font-extrabold text-indigo-300 mt-1">
            {analytics.total_clusters_count}{" "}
            <span className="text-xs font-normal text-slate-400">
              (+{analytics.emerging_unclassified_count} emerging)
            </span>
          </div>
        </div>
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/80">
          <div className="text-[11px] font-mono text-sky-400">DAILY FINOPS LLM SPEND</div>
          <div className="text-2xl font-extrabold text-sky-300 mt-1">
            ${analytics.daily_finops_spend_usd.toFixed(4)}{" "}
            <span className="text-xs font-normal text-slate-400">
              / ${analytics.daily_finops_budget_usd}
            </span>
          </div>
        </div>
      </div>

      {/* Widgets 1 & 2: ECharts Treemap & Golden Reserve Bubble Chart */}
      <DeanCharts
        treemapHierarchy={analytics.treemap_hierarchy}
        goldenReserveMatrix={analytics.golden_reserve_matrix}
        onSelectCluster={(cl) => setSelectedCluster(cl)}
        onSelectProjectBubble={(pid) => toggleTopicSelection(pid)}
      />

      {/* Selected Bottleneck ROI Calculator Card */}
      {selectedCluster && (
        <div className="rounded-xl border border-indigo-500/50 bg-indigo-950/20 p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="text-xs font-mono uppercase text-indigo-300">
              🎯 Executive Bottleneck ROI Decision Card — [{selectedCluster.macro_category}]
            </div>
            <h3 className="text-base font-bold text-white">{selectedCluster.cluster_label}</h3>
            <p className="text-xs text-emerald-300 font-mono">{selectedCluster.estimated_unlock_roi}</p>
            <p className="text-xs text-slate-300">
              <span className="text-slate-400">Departments:</span>{" "}
              {selectedCluster.departments_list?.join(", ")} |{" "}
              <span className="text-slate-400">Advisors:</span>{" "}
              {selectedCluster.supervisors_list?.slice(0, 4).join(", ")}
            </p>
          </div>
          {!String(selectedCluster.cluster_id).startsWith("emerging_") && (
            <button
              type="button"
              disabled={busyAction}
              onClick={() => handleExportGrantMemo(selectedCluster.cluster_id)}
              className="shrink-0 px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-bold text-white shadow"
            >
              📋 Generate Targeted Procurement / Grant Application
            </button>
          )}
        </div>
      )}

      {/* Widgets 3 & 4: 1-Click Topic Export, TRL 6-7 Showcase & Domain Moderation */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setActiveTab("TOPICS")}
              className={`px-3 py-1.5 rounded text-xs font-semibold ${
                activeTab === "TOPICS" ? "bg-emerald-600 text-white" : "bg-slate-950 text-slate-400"
              }`}
            >
              Widget 3: 1-Click Thesis Topic Bank Converter ({selectedTopicIds.length} selected)
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("TRL_SHOWCASE")}
              className={`px-3 py-1.5 rounded text-xs font-semibold ${
                activeTab === "TRL_SHOWCASE"
                  ? "bg-amber-600 text-white"
                  : "bg-slate-950 text-slate-400"
              }`}
            >
              Widget 4: 🚀 TRL 6–7 Tech Transfer Showcase ({analytics.trl_showcase_projects?.length || 0})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("DOMAINS")}
              className={`px-3 py-1.5 rounded text-xs font-semibold ${
                activeTab === "DOMAINS" ? "bg-sky-600 text-white" : "bg-slate-950 text-slate-400"
              }`}
            >
              🔒 Department Domain Approval Queue ({analytics.pending_domains?.length || 0})
            </button>
          </div>

          {activeTab === "TOPICS" && (
            <button
              type="button"
              disabled={busyAction}
              onClick={handleExportVkrBank}
              className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white shadow"
            >
              📥 Export Approved Bank of Thesis Topics 2026/2027 ({selectedTopicIds.length})
            </button>
          )}
        </div>

        {activeTab === "TOPICS" && (
          <div className="max-h-80 overflow-y-auto border border-slate-800 rounded-lg">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950 text-slate-400 font-mono sticky top-0">
                <tr>
                  <th className="p-2.5">Select</th>
                  <th className="p-2.5">Score</th>
                  <th className="p-2.5">Thesis Title</th>
                  <th className="p-2.5">Department</th>
                  <th className="p-2.5">Advisor</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {(analytics.golden_reserve_matrix || []).slice(0, 30).map((item: any) => (
                  <tr key={item.project_id} className="hover:bg-slate-800/50">
                    <td className="p-2.5">
                      <input
                        type="checkbox"
                        checked={selectedTopicIds.includes(item.project_id)}
                        onChange={() => toggleTopicSelection(item.project_id)}
                      />
                    </td>
                    <td className="p-2.5 font-mono font-bold text-emerald-400">
                      {item.final_handover_score}
                    </td>
                    <td className="p-2.5 text-white font-medium">{item.title}</td>
                    <td className="p-2.5 text-slate-300">{item.department}</td>
                    <td className="p-2.5 text-slate-400">{item.supervisor}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === "TRL_SHOWCASE" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {(analytics.trl_showcase_projects || []).map((p: any) => (
              <div
                key={p.project_id}
                className="p-4 rounded-lg border border-amber-500/40 bg-amber-950/15 flex items-center justify-between gap-3 text-xs"
              >
                <div>
                  <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-mono text-[10px] font-bold">
                    🚀 TRL 6–7 READY FOR RID / PATENT & INDUSTRY
                  </span>
                  <div className="font-bold text-white mt-1">{p.title}</div>
                  <div className="text-slate-400">
                    {p.department} | Author: {p.author} | Advisor: {p.supervisor}
                  </div>
                </div>
                <div className="text-lg font-mono font-extrabold text-amber-300 shrink-0">
                  {p.final_handover_score}
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === "DOMAINS" && (
          <div className="space-y-2 text-xs">
            {(analytics.pending_domains || []).length === 0 ? (
              <div className="p-4 rounded bg-slate-950 text-slate-500 font-mono">
                No unknown external domains awaiting moderation.
              </div>
            ) : (
              analytics.pending_domains.map((d: any) => (
                <div
                  key={d.id}
                  className="p-3 rounded bg-slate-950 border border-slate-800 flex items-center justify-between"
                >
                  <div>
                    <span className="font-mono font-bold text-sky-400">{d.domain}</span> — Sample URL:{" "}
                    <span className="text-slate-400">{d.sample_url}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleApproveDomain(d.id)}
                    className="px-3 py-1 rounded bg-emerald-600 text-white font-semibold"
                  >
                    ✅ Approve Domain & Re-Probe
                  </button>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Modal for Exported Markdown Documents (VKR Topic Bank / Grant Justification) */}
      {exportModalDoc && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-4xl w-full p-5 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <h3 className="font-bold text-sm text-white">{exportModalDoc.title}</h3>
              <button
                type="button"
                onClick={() => setExportModalDoc(null)}
                className="text-xs px-2 py-1 rounded bg-slate-800 text-slate-300"
              >
                ✕ Close
              </button>
            </div>
            <pre className="p-4 rounded bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200 whitespace-pre-wrap max-h-[65vh] overflow-y-auto">
              {exportModalDoc.md}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

