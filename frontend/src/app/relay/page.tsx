"use client";

import React, { useEffect, useState } from "react";
import SynergyGraph from "@/components/SynergyGraph";
import {
  claimProjectBatonApi,
  fetchAndSetProjectDetail,
  fetchProjectSynergy,
  fetchProjectsCatalog,
  generateHandoverPackageApi,
} from "@/lib/api_and_sse";
import { useHorizonStore } from "@/lib/store";

export default function Mode2RelayMarketplacePage() {
  const {
    activeProjectDetail,
    activeSynergyGraph,
    filterProfile,
    filterModality,
    filterHasDataset,
    filterPureDonorOnly,
    filterSearchQuery,
    setFilter,
  } = useHorizonStore();

  const [projects, setProjects] = useState<any[]>([]);
  const [graphTab, setGraphTab] = useState<"SYNERGY" | "LINEAGE">("SYNERGY");
  const [bountyQuery, setBountyQuery] = useState<string>("");
  const [mergeSpecModal, setMergeSpecModal] = useState<string | null>(null);
  const [claimModalOpen, setClaimModalOpen] = useState(false);
  const [followerName, setFollowerName] = useState("Alex Rivera (Junior R&D Fellow)");
  const [supervisorName, setSupervisorName] = useState("Prof. Arthur Pendelton");
  const [claimResultMsg, setClaimResultMsg] = useState<string | null>(null);

  const loadMarketplace = async () => {
    const items = await fetchProjectsCatalog({
      domain_profile: filterProfile,
      modality: filterModality,
      has_dataset: filterHasDataset,
      archetype: filterPureDonorOnly ? "GOLD_STANDARD_COMPLETED" : undefined,
      q: filterSearchQuery,
      limit: 50,
    });
    setProjects(items);
    if (!activeProjectDetail && items.length > 0) {
      await fetchAndSetProjectDetail(items[0].project_id);
      await fetchProjectSynergy(items[0].project_id);
    }
  };

  useEffect(() => {
    loadMarketplace();
  }, [filterProfile, filterModality, filterHasDataset, filterPureDonorOnly]);

  const handleSelectCard = async (pid: string) => {
    await fetchAndSetProjectDetail(pid);
    await fetchProjectSynergy(pid);
    setClaimResultMsg(null);
  };

  const handleCorporateBountySearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeProjectDetail?.project_id) return;
    await fetchProjectSynergy(activeProjectDetail.project_id, bountyQuery);
  };

  const handleGenerateMergeSpec = async (match: any) => {
    if (!activeProjectDetail?.project_id) return;
    try {
      const pkg = await generateHandoverPackageApi(activeProjectDetail.project_id, {
        donor_project_id: match.donor_project_id,
        donor_supply_item_id: match.donor_supply_item_id,
        follower_student_name: followerName,
      });
      setMergeSpecModal(pkg.synergy_merge_spec_md || pkg.handover_passport_md);
    } catch (err: any) {
      alert(err?.message || "Failed to generate merge spec");
    }
  };

  const handleTakeBatonSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const demandItems: any[] = activeProjectDetail?.atomic_demand_items || [];
    const openDemand = demandItems.find((d) => d.claim_status === "OPEN") || demandItems[0];
    if (!openDemand || !activeProjectDetail?.project_id) {
      alert("No open Demand task available on this project.");
      return;
    }
    try {
      const firstMatch = activeSynergyGraph?.internal_matches?.[0];
      const res = await claimProjectBatonApi(activeProjectDetail.project_id, {
        demand_item_id: openDemand.id,
        donor_supply_item_id: firstMatch?.donor_supply_item_id,
        follower_student_name: followerName,
        approving_supervisor_name: supervisorName,
        accept_citation_contract: true,
      });
      setClaimModalOpen(false);
      setClaimResultMsg(
        `✅ Baton Claimed! Created Gen+1 slot (${res.child_project_id.slice(0, 8)}) with signed Academic Royalty Citation Contract.`
      );
      await fetchAndSetProjectDetail(activeProjectDetail.project_id);
    } catch (err: any) {
      alert(err?.message || "Claim conflict");
    }
  };

  const matches: any[] = activeSynergyGraph?.internal_matches || [];

  return (
    <div className="space-y-6">
      {/* Filters & Corporate Bounty Matching Bar */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <select
            value={filterProfile}
            onChange={(e) => setFilter("filterProfile", e.target.value)}
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200"
          >
            <option value="all">All 5 University Profiles</option>
            <option value="IT_AND_DATA_SCIENCE">IT, AI & Data Science</option>
            <option value="ENGINEERING_AND_HARDWARE">Engineering & Hardware</option>
            <option value="NATURAL_AND_BIOMEDICAL">Biomedical & Natural Sciences</option>
            <option value="ECONOMICS_AND_MANAGEMENT">Economics & Finance</option>
            <option value="HUMANITIES_SOCIAL_AND_LAW">Humanities, Social & Law</option>
          </select>

          <select
            value={filterModality}
            onChange={(e) => setFilter("filterModality", e.target.value)}
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200"
          >
            <option value="all">All Signal Modalities</option>
            <option value="image">2D/3D Image & Radiography</option>
            <option value="signal">Sensor & Acoustic Signal</option>
            <option value="tabular">Tabular & Econometric Panel</option>
            <option value="text">Text & NLP Corpus</option>
            <option value="legal_normative">Legal & Regulatory Framework</option>
          </select>

          <label className="flex items-center gap-2 text-xs text-slate-300 px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 cursor-pointer">
            <input
              type="checkbox"
              checked={filterHasDataset}
              onChange={(e) => setFilter("filterHasDataset", e.target.checked)}
            />
            <span>📦 Verified Dataset Only</span>
          </label>

          <label className="flex items-center gap-2 text-xs text-emerald-300 px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 cursor-pointer">
            <input
              type="checkbox"
              checked={filterPureDonorOnly}
              onChange={(e) => setFilter("filterPureDonorOnly", e.target.checked)}
            />
            <span>🟢 Pure Supply Donors (TRL 6-7)</span>
          </label>

          <div className="flex gap-1">
            <input
              type="text"
              value={filterSearchQuery}
              onChange={(e) => setFilter("filterSearchQuery", e.target.value)}
              placeholder="Search title / department..."
              className="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs"
            />
            <button
              type="button"
              onClick={loadMarketplace}
              className="px-3 py-1.5 rounded-lg bg-emerald-600 text-xs font-bold text-white"
            >
              Go
            </button>
          </div>
        </div>

        {/* Corporate Bounty Reverse Funnel (§6.4) */}
        <form onSubmit={handleCorporateBountySearch} className="flex flex-wrap gap-2 pt-2 border-t border-slate-800">
          <input
            type="text"
            value={bountyQuery}
            onChange={(e) => setBountyQuery(e.target.value)}
            placeholder="🏢 Corporate Bounty Funnel: Enter an industrial R&D problem (e.g., 'Suppression of coherent speckle noise on 2D matrices')..."
            className="flex-1 px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200"
          />
          <button
            type="submit"
            className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white"
          >
            Scan University Supply Assets
          </button>
        </form>
      </div>

      {claimResultMsg && (
        <div className="p-4 rounded-xl border border-emerald-500 bg-emerald-950/30 text-xs font-mono text-emerald-200">
          {claimResultMsg}
        </div>
      )}

      {/* Main Split View: Left = Project Cards, Right = Synergy Stitcher & Lineage Graph */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-5 space-y-3 max-h-[760px] overflow-y-auto pr-1">
          {projects.map((p) => {
            const isSelected = activeProjectDetail?.project_id === p.project_id;
            return (
              <div
                key={p.project_id}
                onClick={() => handleSelectCard(p.project_id)}
                className={`p-4 rounded-xl border transition cursor-pointer ${
                  isSelected
                    ? "border-emerald-500 bg-slate-900 shadow-lg"
                    : "border-slate-800 bg-slate-900/60 hover:border-slate-700"
                }`}
              >
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-950 text-slate-300 border border-slate-800">
                    {p.department} ({p.year})
                  </span>
                  <div className="flex items-center gap-1.5">
                    {p.is_pure_supply_donor && (
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-950 text-emerald-300 border border-emerald-700">
                        🟢 Pure Supply Donor
                      </span>
                    )}
                    <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-indigo-950 text-indigo-300 border border-indigo-700">
                      {p.final_handover_score} / 100
                    </span>
                  </div>
                </div>

                <h3 className="text-sm font-bold text-white mb-2">{p.title}</h3>

                <div className="space-y-1.5 text-xs">
                  <div className="p-2 rounded bg-slate-950/80 border border-slate-800/80">
                    <span className="text-emerald-400 font-mono font-semibold">📦 Verified Supply: </span>
                    <span className="text-slate-300">{p.supply_summary?.data_summary}</span>
                  </div>
                  {p.demand_summary?.tasks?.[0] && (
                    <div className="p-2 rounded bg-slate-950/80 border border-slate-800/80">
                      <span className="text-rose-400 font-mono font-semibold">🎯 Open Demand: </span>
                      <span className="text-slate-300">
                        {p.demand_summary.tasks[0].task_description}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Right Column: Interactive Graph + Synergy Bridge Cards + Take the Baton */}
        <div className="lg:col-span-7 space-y-5">
          <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setGraphTab("SYNERGY")}
                  className={`px-3 py-1.5 rounded text-xs font-semibold ${
                    graphTab === "SYNERGY"
                      ? "bg-emerald-600 text-white"
                      : "bg-slate-950 text-slate-400"
                  }`}
                >
                  🔗 Asymmetric Synergy Graph (Demand A → Supply B)
                </button>
                <button
                  type="button"
                  onClick={() => setGraphTab("LINEAGE")}
                  className={`px-3 py-1.5 rounded text-xs font-semibold ${
                    graphTab === "LINEAGE"
                      ? "bg-emerald-600 text-white"
                      : "bg-slate-950 text-slate-400"
                  }`}
                >
                  🌳 “Git for Science” Lineage Tree (Gen 1 → Gen 2 → Gen 3)
                </button>
              </div>

              <button
                type="button"
                onClick={() => setClaimModalOpen(true)}
                className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white shadow"
              >
                🤝 Take the Baton (Claim Topic & Sign Royalty Contract)
              </button>
            </div>

            <SynergyGraph
              projectDetail={activeProjectDetail}
              synergyGraph={activeSynergyGraph}
              viewMode={graphTab}
            />
          </div>

          {/* Synergy Bridge Cards (§4.2) */}
          <div className="space-y-3">
            <h3 className="text-xs font-mono uppercase tracking-wider text-slate-400">
              Cross-Departmental Synergy Bridge Cards (Calibrated Formula S_A&larr;B)
            </h3>

            {matches.map((m, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-emerald-500/40 bg-slate-900/90 p-4 space-y-3"
              >
                <div className="grid grid-cols-1 md:grid-cols-11 gap-3 items-center">
                  <div className="md:col-span-5 p-3 rounded-lg bg-rose-950/25 border border-rose-500/30 text-xs">
                    <div className="font-mono text-[11px] text-rose-400 uppercase mb-1">
                      🔴 PROJECT A BOTTLENECK (DEMAND)
                    </div>
                    <div className="font-bold text-white mb-1">{activeProjectDetail?.title}</div>
                    <div className="text-slate-300">{m.demand_task_description}</div>
                  </div>

                  <div className="md:col-span-1 flex flex-col items-center justify-center font-mono">
                    <span className="px-2 py-1 rounded bg-emerald-500/20 border border-emerald-400 text-emerald-300 font-bold text-xs">
                      {Math.round(m.formula.synergy_score * 100)}%
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1">MATCH</span>
                  </div>

                  <div className="md:col-span-5 p-3 rounded-lg bg-emerald-950/25 border border-emerald-500/30 text-xs">
                    <div className="font-mono text-[11px] text-emerald-400 uppercase mb-1">
                      🟢 PROJECT B VALIDATED ASSET (SUPPLY)
                    </div>
                    <div className="font-bold text-white mb-1">
                      {m.donor_title} ({m.donor_department}, {m.donor_year})
                    </div>
                    <div className="text-slate-300">{m.donor_supply_text}</div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-800 text-[11px] font-mono text-slate-400">
                  <span>
                    Formula: P_rerank={m.formula.p_rerank_calibrated} | CosSim={m.formula.cosine_similarity} | M_env=
                    {m.formula.m_envelope} | M_stack={m.formula.m_stack}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleGenerateMergeSpec(m)}
                    className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-emerald-300 border border-slate-700 font-sans font-semibold"
                  >
                    📄 Generate 1-Page Synergy Merge Spec & Thesis Brief
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Modal: 1-Page Synergy Merge Specification */}
      {mergeSpecModal && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-3xl w-full p-5 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <h3 className="font-bold text-sm text-white">
                1-Page Cross-Departmental Synergy Merge Specification
              </h3>
              <button
                type="button"
                onClick={() => setMergeSpecModal(null)}
                className="text-xs px-2 py-1 rounded bg-slate-800 text-slate-300"
              >
                ✕ Close
              </button>
            </div>
            <pre className="p-4 rounded bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200 whitespace-pre-wrap max-h-96 overflow-y-auto">
              {mergeSpecModal}
            </pre>
          </div>
        </div>
      )}

      {/* Modal: Take the Baton (FOR UPDATE NOWAIT Reservation) */}
      {claimModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <form
            onSubmit={handleTakeBatonSubmit}
            className="bg-slate-900 border border-slate-700 rounded-xl max-w-md w-full p-5 space-y-4"
          >
            <h3 className="font-bold text-sm text-white">
              🤝 Take the Baton — Reserve Thesis Topic & Sign Academic Royalty Contract
            </h3>
            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-400 mb-1">Incoming Student / R&D Fellow Name</label>
                <input
                  type="text"
                  required
                  value={followerName}
                  onChange={(e) => setFollowerName(e.target.value)}
                  className="w-full px-3 py-2 rounded bg-slate-950 border border-slate-800 text-white"
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Approving Faculty Advisor</label>
                <input
                  type="text"
                  required
                  value={supervisorName}
                  onChange={(e) => setSupervisorName(e.target.value)}
                  className="w-full px-3 py-2 rounded bg-slate-950 border border-slate-800 text-white"
                />
              </div>
              <div className="p-3 rounded bg-slate-950 border border-slate-800 text-slate-300">
                ✓ By claiming this mission, `CITATION.cff` automatically credits the predecessor author (
                {activeProjectDetail?.author}) and advisor ({activeProjectDetail?.supervisor}).
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setClaimModalOpen(false)}
                className="px-3 py-1.5 rounded bg-slate-800 text-xs text-slate-300"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 rounded bg-emerald-600 text-xs font-bold text-white"
              >
                Confirm & Lock Topic (FOR UPDATE NOWAIT)
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

