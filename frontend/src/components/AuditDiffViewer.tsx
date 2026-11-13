"use client";

import React from "react";

interface AuditDiffViewerProps {
  passport: any;
}

export default function AuditDiffViewer({ passport }: AuditDiffViewerProps) {
  if (!passport) return null;

  const audit = passport.deep_harvest_audit || {};
  const gap = audit.reality_vs_conclusion_gap || {};
  const linterItems: any[] = audit.future_work_linter_items || [];
  const discarded: any[] = audit.discarded_approaches || [];
  const demandHorizon = passport.demand_horizon || {};
  const fluffList: string[] = demandHorizon.filtered_fluff_items || [];
  const demandItems: any[] = demandHorizon.atomic_demand_items || [];

  const severityColor =
    gap.gap_severity === "HIGH"
      ? "border-rose-500/60 bg-rose-950/30 text-rose-300"
      : gap.gap_severity === "MEDIUM"
      ? "border-amber-500/60 bg-amber-950/30 text-amber-300"
      : "border-emerald-500/60 bg-emerald-950/30 text-emerald-300";

  return (
    <div className="space-y-6">
      {/* 1. Reality vs. Conclusion Gap Detector */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200">
              Forensic Omission Detector: Conclusion Claims vs. Middle-Chapter Reality
            </h3>
            <p className="text-xs text-slate-400">
              Cross-checking polished final page claims against raw experimental tables & stubs in Chapters 2–3
            </p>
          </div>
          <span className={`px-2.5 py-1 rounded text-xs font-mono font-bold border ${severityColor}`}>
            GAP SEVERITY: {gap.gap_severity || "LOW"} (Page {gap.source_page || 45})
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="rounded-lg border border-sky-500/30 bg-sky-950/20 p-4">
            <div className="text-xs font-mono uppercase text-sky-400 mb-1">
              🔵 Author Claim in Conclusion (Last Pages)
            </div>
            <p className="text-sm text-slate-200 leading-relaxed">
              “{gap.conclusion_claim || "No explicit claim extracted."}”
            </p>
          </div>

          <div className="rounded-lg border border-amber-500/40 bg-amber-950/20 p-4">
            <div className="text-xs font-mono uppercase text-amber-400 mb-1">
              🟢 Forensic Reality in Middle Chapters (Page {gap.source_page || 51})
            </div>
            <p className="text-sm text-slate-200 leading-relaxed font-medium">
              {gap.middle_chapter_reality || "All stated metrics verified in middle chapters."}
            </p>
          </div>
        </div>
      </div>

      {/* 2. Split-View Diff Linter for Future Work */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
        <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200 mb-1">
          “Future Work” Static Diff Linter (Fluff Filtering vs. Actionable R&D Demand)
        </h3>
        <p className="text-xs text-slate-400 mb-4">
          Automatically strips generic UI/product filler and extracts concrete mathematical/engineering tasks for the next generation
        </p>

        <div className="space-y-2.5 font-mono text-xs">
          {linterItems.map((item, idx) => {
            const isFluff = item.verdict === "FLUFF";
            const isWeak = item.verdict === "WEAK_SPECIFICITY";
            return (
              <div
                key={idx}
                className={`p-3 rounded-lg border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                  isFluff
                    ? "border-rose-500/40 bg-rose-950/25 text-rose-200"
                    : isWeak
                    ? "border-amber-500/40 bg-amber-950/25 text-amber-200"
                    : "border-emerald-500/40 bg-emerald-950/25 text-emerald-200"
                }`}
              >
                <span className={isFluff ? "line-through opacity-75" : ""}>
                  {isFluff ? "🔴 " : isWeak ? "🟡 " : "🟢 "}
                  {item.original_sentence}
                </span>
                <span className="shrink-0 px-2 py-1 rounded bg-slate-950/80 border border-slate-700 text-[11px]">
                  [{item.reason_badge}]
                </span>
              </div>
            );
          })}

          {linterItems.length === 0 &&
            fluffList.map((fluff, i) => (
              <div
                key={`fluff-${i}`}
                className="p-3 rounded-lg border border-rose-500/40 bg-rose-950/25 text-rose-200 flex items-center justify-between gap-3"
              >
                <span className="line-through opacity-75">🔴 {fluff}</span>
                <span className="px-2 py-1 rounded bg-slate-950 text-[11px] border border-rose-800">
                  [REJECTED: Marketing/UI Fluff — 0 pts]
                </span>
              </div>
            ))}

          {linterItems.length === 0 &&
            demandItems.map((d, i) => (
              <div
                key={`dem-${i}`}
                className="p-3 rounded-lg border border-emerald-500/40 bg-emerald-950/25 text-emerald-200 flex items-center justify-between gap-3"
              >
                <span>🟢 {d.task_description}</span>
                <span className="px-2 py-1 rounded bg-slate-950 text-[11px] border border-emerald-800">
                  [EXTRACTED TO DEMAND: +30 pts]
                </span>
              </div>
            ))}
        </div>
      </div>

      {/* 3. Implicit Dead-End Shield (Discarded Approaches) */}
      {discarded.length > 0 && (
        <div className="rounded-xl border border-rose-500/50 bg-rose-950/20 p-5">
          <div className="text-xs font-mono font-bold uppercase text-rose-400 mb-2">
            ⚠️ Implicit Dead-End Shield — DO NOT REPEAT IN NEXT GENERATION!
          </div>
          <div className="space-y-2">
            {discarded.map((d, i) => (
              <div key={i} className="text-xs text-slate-200 bg-slate-950/60 p-3 rounded border border-rose-900/50">
                <span className="font-bold text-rose-300">{d.method}</span>{" "}
                <span className="text-slate-400">({d.source_location}):</span> {d.failure_reason}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

