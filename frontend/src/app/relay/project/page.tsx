"use client";

import React, { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useHorizonStore } from "@/lib/store";
import { SegNav, MetaChipsRow, ScoreRing } from "@/components/ui";
import { IconArrowLeft } from "@/components/icons";
import { archetypeChipClass, archetypeLabel } from "@/lib/format";
import { fetchAndSetProjectDetail, generateHandoverPackageApi } from "@/lib/api_and_sse";
import {
  ClaimModal,
  DemandTab,
  LineageTab,
  MergeSpecModal,
  PackageTab,
  PassportTab,
  SupplyTab,
  SynergyTab,
} from "@/components/relay-tabs";

export default function RelayProjectPage() {
  return (
    <Suspense fallback={null}>
      <RelayProjectPageInner />
    </Suspense>
  );
}

function RelayProjectPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = searchParams.get("tab") || "passport";
  const { activeProjectDetail: detail, activeSynergyGraph } = useHorizonStore();

  const [claimTarget, setClaimTarget] = useState<any | null>(null);
  const [claimResultMsg, setClaimResultMsg] = useState<string | null>(null);
  const [mergeSpecModal, setMergeSpecModal] = useState<string | null>(null);

  const setTab = (key: string) => router.push(`/relay/project?tab=${key}`);

  if (!detail) {
    return (
      <section className="screen">
        <main className="wrap">
          <h1 className="h1">Проект не выбран</h1>
          <Link className="btn btn-p" href="/relay" style={{ marginTop: 16 }}>
            К маркетплейсу
          </Link>
        </main>
      </section>
    );
  }

  const supplyItems: any[] = detail.atomic_supply_items || [];
  const demandItems: any[] = detail.atomic_demand_items || [];
  const openCount = demandItems.filter((d) => d.claim_status === "OPEN").length;
  const matches: any[] = activeSynergyGraph?.internal_matches || [];

  const tabs = [
    { key: "passport", label: "Паспорт" },
    { key: "supply", label: "Supply", badge: supplyItems.length },
    { key: "demand", label: "Demand", badge: `${openCount} открыто` },
    { key: "synergy", label: "Synergy Bridge", badge: matches.length },
    { key: "lineage", label: "Lineage" },
    { key: "package", label: "Handover Package" },
  ];

  const refreshDetail = () => fetchAndSetProjectDetail(detail.project_id);

  return (
    <section className="screen">
      <main className="wrap">
        <Link className="lnk sm" href="/relay" style={{ marginBottom: 16, minHeight: 32 }}>
          <IconArrowLeft size={16} />
          Маркетплейс
        </Link>

        <div className="phead" style={{ marginBottom: 20 }}>
          <div style={{ minWidth: 0, flex: "1 1 640px" }}>
            <h1 className="h1" style={{ marginTop: 0 }}>{detail.title}</h1>
            <MetaChipsRow
              author={detail.author}
              supervisor={detail.supervisor}
              year={detail.year}
              department={detail.department}
              domainProfile={detail.domain_profile}
              modality={detail.modality}
              language={detail.primary_language}
              archetypeChip={
                <span className={`chip ${archetypeChipClass(detail.lifecycle_archetype)}`}>
                  <span className="d" />
                  {archetypeLabel(detail.lifecycle_archetype)}
                </span>
              }
            />
          </div>
          <div className="card" style={{ padding: "14px 18px", display: "flex", alignItems: "center", gap: 14 }}>
            <ScoreRing score100={detail.final_handover_score ?? 0} size={52} stroke={5} />
            <div>
              <div className="xs fa">Handover score</div>
              <div className="sm" style={{ fontWeight: 500 }}>
                {supplyItems.length} актива · {openCount} задач открыто
              </div>
            </div>
          </div>
        </div>

        <div style={{ marginBottom: 20 }}>
          <SegNav items={tabs} active={tab} onChange={setTab} ariaLabel="Разделы проекта" />
        </div>

        {claimResultMsg && (
          <div className="card xs" style={{ marginBottom: 20, color: "var(--ok)", borderColor: "rgba(74,222,128,.4)" }}>
            {claimResultMsg}
          </div>
        )}

        {tab === "passport" && <PassportTab detail={detail} onNavigate={setTab} />}
        {tab === "supply" && <SupplyTab detail={detail} />}
        {tab === "demand" && <DemandTab detail={detail} onClaim={setClaimTarget} />}
        {tab === "synergy" && (
          <SynergyTab
            detail={detail}
            synergyGraph={activeSynergyGraph}
            onGenerateMergeSpec={async (m) => {
              try {
                const pkg = await generateHandoverPackageApi(detail.project_id, {
                  donor_project_id: m.donor_project_id,
                  donor_supply_item_id: m.donor_supply_item_id,
                });
                setMergeSpecModal(pkg.synergy_merge_spec_md || pkg.handover_passport_md);
              } catch (err: any) {
                alert(err?.message || "Не удалось сформировать ТЗ на объединение");
              }
            }}
          />
        )}
        {tab === "lineage" && <LineageTab detail={detail} synergyGraph={activeSynergyGraph} />}
        {tab === "package" && <PackageTab detail={detail} />}
      </main>

      {claimTarget && (
        <ClaimModal
          detail={detail}
          demandItem={claimTarget}
          matches={matches}
          onClose={() => setClaimTarget(null)}
          onClaimed={async (msg) => {
            setClaimTarget(null);
            setClaimResultMsg(msg);
            await refreshDetail();
          }}
        />
      )}

      {mergeSpecModal && <MergeSpecModal content={mergeSpecModal} onClose={() => setMergeSpecModal(null)} />}
    </section>
  );
}
