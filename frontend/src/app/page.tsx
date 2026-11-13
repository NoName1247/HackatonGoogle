"use client";

import React, { useEffect, useState } from "react";
import AuditDiffViewer from "@/components/AuditDiffViewer";
import {
  buildSampleDemoPdfFile,
  fetchAndSetProjectDetail,
  fetchProjectSynergy,
  fetchProjectsCatalog,
  generateHandoverPackageApi,
  uploadThesisAndSubscribeSSE,
} from "@/lib/api_and_sse";
import { useHorizonStore } from "@/lib/store";

export default function Mode1PreDefenseXRayPage() {
  const {
    activeRole,
    uploadPhase,
    progressPercent,
    progressTitle,
    progressHistory,
    uploadError,
    activeProjectDetail,
    activeSynergyGraph,
  } = useHorizonStore();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [repoUrl, setRepoUrl] = useState<string>("https://github.com/example/weld-xray-seg");
  const [thesisTitle, setThesisTitle] = useState<string>("");
  const [catalogProjects, setCatalogProjects] = useState<any[]>([]);
  const [packageModal, setPackageModal] = useState<any | null>(null);
  const [loadingPackage, setLoadingPackage] = useState(false);

  useEffect(() => {
    fetchProjectsCatalog({ limit: 15 }).then((items) => {
      setCatalogProjects(items);
      if (!useHorizonStore.getState().activeProjectDetail && items.length > 0) {
        const firstId = items[0].project_id;
        fetchAndSetProjectDetail(firstId);
        fetchProjectSynergy(firstId);
      }
    });
  }, []);

  const handleSelectProject = async (pid: string) => {
    await fetchAndSetProjectDetail(pid);
    await fetchProjectSynergy(pid);
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;
    await uploadThesisAndSubscribeSSE(selectedFile, repoUrl, thesisTitle);
    const updated = await fetchProjectsCatalog({ limit: 15 });
    setCatalogProjects(updated);
  };

  const handleRunLiveDemoPdf = async () => {
    const demoFile = buildSampleDemoPdfFile();
    setSelectedFile(demoFile);
    await uploadThesisAndSubscribeSSE(
      demoFile,
      "https://github.com/example/weld-xray-seg",
      "Automated Defect Segmentation in X-Ray Radiographs of Welded Joints"
    );
    const updated = await fetchProjectsCatalog({ limit: 15 });
    setCatalogProjects(updated);
  };

  const handleGeneratePackage = async () => {
    if (!activeProjectDetail?.project_id) return;
    setLoadingPackage(true);
    try {
      const pkg = await generateHandoverPackageApi(activeProjectDetail.project_id);
      setPackageModal(pkg);
    } catch (err: any) {
      alert(err?.message || "Failed to generate package");
    } finally {
      setLoadingPackage(false);
    }
  };

  const passport = activeProjectDetail?.passport;
  const scoring = passport?.scoring || {};
  const verif = passport?.artifact_verification || {};
  const audit = passport?.deep_harvest_audit || {};
  const meta = passport?.meta || {};
  const questions: string[] = audit?.commission_defense_questions || [];
  const priorArt: any[] = audit?.prior_art_radar?.similar_past_projects || [];
  const internalSynergy: any[] = activeSynergyGraph?.internal_matches || [];

  return (
    <div className="space-y-6">
      {/* Top Upload & Quick-Switch Bar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <form
          onSubmit={handleUploadSubmit}
          className="lg:col-span-2 rounded-xl border border-slate-800 bg-slate-900/80 p-5 space-y-4"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-base font-bold text-white">
                Pre-Defense Forensic PDF Harvester & Zero-Trust Repository Probe
              </h2>
              <p className="text-xs text-slate-400">
                Full 100% page scan (no middle-chapter truncation), SHA-256 chapter cache & live Redis Streams SSE
              </p>
            </div>
            <button
              type="button"
              onClick={handleRunLiveDemoPdf}
              disabled={uploadPhase === "UPLOADING" || uploadPhase === "STREAMING"}
              className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-xs font-semibold text-white shadow"
            >
              ⚡ Run 1-Click Live Demo PDF Audit
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">
                THESIS PDF FILE (&le; 25MB, %PDF-1.x)
              </label>
              <input
                type="file"
                accept=".pdf,application/pdf"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                className="w-full text-xs text-slate-300 file:mr-2 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-emerald-400 hover:file:bg-slate-700"
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1">
                REPOSITORY / DATASET URL (OPTIONAL)
              </label>
              <input
                type="text"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/owner/repo or Zenodo/OSF"
                className="w-full px-3 py-1.5 rounded bg-slate-950 border border-slate-800 text-xs text-slate-200"
              />
            </div>
            <div className="flex items-end">
              <button
                type="submit"
                disabled={!selectedFile || uploadPhase === "UPLOADING" || uploadPhase === "STREAMING"}
                className="w-full py-2 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-xs font-bold text-white transition"
              >
                {uploadPhase === "UPLOADING" || uploadPhase === "STREAMING"
                  ? `Auditing (${progressPercent}%)...`
                  : "🔍 Run Full Zero-Trust Audit"}
              </button>
            </div>
          </div>

          {/* Live SSE Progress Bar */}
          {uploadPhase !== "IDLE" && (
            <div className="rounded-lg bg-slate-950 border border-slate-800 p-3 space-y-2">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-emerald-400">{progressTitle || "Processing..."}</span>
                <span className="text-slate-300">{progressPercent}%</span>
              </div>
              <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                <div
                  className="h-full bg-emerald-500 transition-all duration-300"
                  style={{ width: `${Math.min(100, Math.max(5, progressPercent))}%` }}
                />
              </div>
              {uploadError && (
                <div className="text-xs text-rose-400 font-mono bg-rose-950/40 p-2 rounded border border-rose-800">
                  ⚠️ {uploadError}
                </div>
              )}
              {progressHistory.length > 0 && (
                <div className="max-h-24 overflow-y-auto space-y-1 pt-1 text-[11px] font-mono text-slate-400">
                  {progressHistory.map((ev, idx) => (
                    <div key={idx}>
                      ✓ [{ev.percent}%] {ev.title}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </form>

        {/* Quick Selector for Flagship Theses Across All 5 University Profiles */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-5 flex flex-col justify-between">
          <div>
            <h3 className="text-xs font-mono uppercase tracking-wider text-slate-400 mb-2">
              Switch Inspected Thesis (5 University Profiles)
            </h3>
            <select
              value={activeProjectDetail?.project_id || ""}
              onChange={(e) => handleSelectProject(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-xs text-slate-100 mb-3"
            >
              {catalogProjects.map((p) => (
                <option key={p.project_id} value={p.project_id}>
                  [{p.final_handover_score} pts | {p.domain_profile.split("_")[0]}] {p.title.slice(0, 62)}
                </option>
              ))}
            </select>
            {passport && (
              <div className="text-xs space-y-1 text-slate-300">
                <div>
                  <span className="text-slate-500">Department:</span> {meta.department}
                </div>
                <div>
                  <span className="text-slate-500">Author / Advisor:</span> {meta.author} / {meta.supervisor}
                </div>
                <div>
                  <span className="text-slate-500">Profile:</span>{" "}
                  <span className="font-mono text-emerald-400">{meta.domain_profile}</span>
                </div>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={handleGeneratePackage}
            disabled={loadingPackage || !passport}
            className="mt-4 w-full py-2 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold text-emerald-300 transition"
          >
            {loadingPackage
              ? "Generating Package..."
              : "📦 Auto-Generate HANDOVER_PASSPORT.md & CITATION.cff"}
          </button>
        </div>
      </div>

      {/* Security & Anti-Plagiarism Banner */}
      {(activeProjectDetail?.security_alert || activeProjectDetail?.plagiarism_alert) && (
        <div className="rounded-xl border-2 border-rose-500 bg-rose-950/40 p-4 text-xs font-mono text-rose-200 space-y-1">
          {activeProjectDetail.security_alert && (
            <div className="font-bold">
              🚨 SECURITY ALERT [{activeProjectDetail.security_alert}]: Hidden micro-font / white-on-white prompt injection attempt stripped by Math-Safe Visual Sanitizer!
            </div>
          )}
          {activeProjectDetail.plagiarism_alert && (
            <div className="font-bold">🚨 {activeProjectDetail.plagiarism_alert}</div>
          )}
        </div>
      )}

      {passport && (
        <>
          {/* Block 1: Handover Score Passport + Artifact Probe Checklist */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-mono uppercase text-slate-400">
                    Deterministic Handover Score
                  </span>
                  <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-emerald-950 text-emerald-300 border border-emerald-700">
                    {scoring.scoring_mode}
                  </span>
                </div>
                <div className="text-4xl font-extrabold text-white tracking-tight my-2">
                  {scoring.final_handover_score}{" "}
                  <span className="text-lg font-normal text-slate-400">/ 100</span>
                </div>
                <div className="text-xs text-emerald-400 font-medium mb-4">{scoring.status}</div>

                <div className="grid grid-cols-2 gap-2 text-xs font-mono bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <div>
                    Code / Method: <span className="text-white">{scoring.raw_code_score}/25</span>{" "}
                    <span className="text-slate-500">(×{scoring.time_decay_code})</span>
                  </div>
                  <div>
                    Data Assets: <span className="text-white">{scoring.raw_data_score}/25</span>{" "}
                    <span className="text-slate-500">(×{scoring.time_decay_data})</span>
                  </div>
                  <div>
                    Validity Audit: <span className="text-white">{scoring.validity_score}/20</span>
                  </div>
                  <div>
                    Horizon / Maturity:{" "}
                    <span className="text-white">{scoring.roadmap_or_maturity_score}/30</span>
                  </div>
                </div>
              </div>

              {scoring.improvement_recipes?.length > 0 && (
                <div className="mt-4 pt-3 border-t border-slate-800">
                  <div className="text-[11px] font-mono uppercase text-amber-400 mb-1.5">
                    Pre-Defense Score Booster Recipes:
                  </div>
                  <ul className="space-y-1 text-xs text-slate-300">
                    {scoring.improvement_recipes.map((r: string, i: number) => (
                      <li key={i}>• {r}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Automated Artifact Probe Verification */}
            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200">
                  Automated Artifact Probe (Module 2)
                </h3>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800 text-sky-300">
                  {verif.probe_status}
                </span>
              </div>
              <p className="text-xs text-slate-400 truncate mb-4">
                Source: {verif.repo_url || "In-Document Empirical Tables & Appendices"}
              </p>

              <div className="space-y-2 text-xs font-mono">
                {[
                  { label: "Repository Alive (>5 non-empty files)", ok: verif.repo_alive },
                  { label: "Environment Spec (requirements/Dockerfile >=15B)", ok: verif.has_dependencies },
                  { label: "Clean Relative Paths & Executed .ipynb Cells", ok: verif.has_clean_paths },
                  { label: "Verified Data / Weights (>250B, non-LFS pointer)", ok: verif.has_data_artifact },
                  { label: "Open Academic License / University Archive", ok: verif.has_license },
                ].map((flag, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between p-2 rounded bg-slate-950 border border-slate-800"
                  >
                    <span className="text-slate-300">{flag.label}</span>
                    <span className={flag.ok ? "text-emerald-400 font-bold" : "text-rose-400"}>
                      {flag.ok ? "✓ PASS" : "✗ MISS"}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* 3 Razor-Sharp Questions for Examination Board (ГАК) */}
            <div className="rounded-xl border border-indigo-500/40 bg-indigo-950/20 p-5">
              <div className="text-xs font-mono font-bold uppercase text-indigo-300 mb-1">
                {activeRole === "STUDENT"
                  ? "🛡️ Prepare for Defense: 3 Questions the Board Will Ask You"
                  : "🎯 3 Razor-Sharp Defense Questions for Examination Board (ГАК)"}
              </div>
              <p className="text-xs text-slate-400 mb-3">
                Generated from the exact gap between the author&apos;s Conclusion and Chapters 2–3 tables
              </p>
              <div className="space-y-2.5">
                {questions.map((q, idx) => (
                  <div
                    key={idx}
                    className="p-3 rounded-lg bg-slate-950/80 border border-indigo-900/60 text-xs text-slate-200 leading-relaxed"
                  >
                    <span className="font-bold text-indigo-400">Q{idx + 1}:</span> {q}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Block 2: Reality vs. Conclusion Gap + Future Work Diff Linter */}
          <AuditDiffViewer passport={passport} />

          {/* Block 3: Prior Art & Intra-University Solution Radar */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200 mb-1">
                🔄 University Prior Art & Novelty Radar (Past 5 Years)
              </h3>
              <p className="text-xs text-slate-400 mb-3">
                Detects overlapping theses defended across university departments to prevent reinventing the wheel
              </p>
              <div className="space-y-2.5">
                {priorArt.length === 0 ? (
                  <div className="text-xs text-slate-500 font-mono p-3 rounded bg-slate-950">
                    No direct prior-art collisions detected in the archive.
                  </div>
                ) : (
                  priorArt.map((pa, i) => (
                    <div key={i} className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs">
                      <div className="font-semibold text-white">
                        {pa.title} ({pa.year})
                      </div>
                      <div className="text-slate-400 text-[11px] mb-1">
                        {pa.department} | Author: {pa.author}
                      </div>
                      <div className="text-amber-300 font-mono text-[11px]">{pa.similarity_note}</div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
              <h3 className="text-sm font-bold uppercase tracking-wider text-emerald-400 mb-1">
                🎁 Ready-Made Intra-University Solutions for Your Bottlenecks
              </h3>
              <p className="text-xs text-slate-400 mb-3">
                Asymmetric TRIZ match: Supply assets from adjacent departments that solve this thesis&apos;s Demand
              </p>
              <div className="space-y-2.5">
                {internalSynergy.slice(0, 2).map((m, i) => (
                  <div
                    key={i}
                    className="p-3 rounded-lg bg-emerald-950/20 border border-emerald-500/40 text-xs space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-emerald-300">
                        {Math.round(m.formula.synergy_score * 100)}% SYNERGY MATCH
                      </span>
                      <span className="font-mono text-[11px] text-slate-400">{m.donor_department}</span>
                    </div>
                    <div className="font-semibold text-white">{m.donor_title}</div>
                    <div className="text-slate-300">
                      <span className="text-emerald-400 font-mono">Supply:</span> {m.donor_supply_text}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}

      {/* Modal for Auto-Generated HANDOVER_PASSPORT.md & CITATION.cff */}
      {packageModal && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-4xl w-full max-h-[85vh] flex flex-col overflow-hidden">
            <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
              <h3 className="font-bold text-sm text-white">
                Auto-Packaged Legacy Documentation (HANDOVER_PASSPORT.md & CITATION.cff)
              </h3>
              <button
                type="button"
                onClick={() => setPackageModal(null)}
                className="text-xs text-slate-400 hover:text-white px-2 py-1 rounded bg-slate-800"
              >
                ✕ Close
              </button>
            </div>
            <div className="p-5 overflow-y-auto grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
              <div>
                <div className="text-emerald-400 font-bold mb-2">1. HANDOVER_PASSPORT.md</div>
                <pre className="p-3 rounded bg-slate-950 border border-slate-800 whitespace-pre-wrap text-slate-200 max-h-96 overflow-y-auto">
                  {packageModal.handover_passport_md}
                </pre>
              </div>
              <div>
                <div className="text-sky-400 font-bold mb-2">
                  2. CITATION.cff (Academic Royalty Contract)
                </div>
                <pre className="p-3 rounded bg-slate-950 border border-slate-800 whitespace-pre-wrap text-slate-200 max-h-96 overflow-y-auto">
                  {packageModal.citation_cff}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

