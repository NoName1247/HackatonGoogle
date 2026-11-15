"use client";

import React, { Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useHorizonStore } from "@/lib/store";
import { SegNav, MetaChipsRow, ScoreRing, AlertBanner } from "@/components/ui";
import { IconShield } from "@/components/icons";
import { archetypeChipClass, archetypeLabel, gapSeverityChipClass, gapSeverityLabel } from "@/lib/format";
import {
  LineageTab,
  PassportTab,
  PriorArtTab,
  QuestionsTab,
  RealityTab,
  SupplyDemandTab,
  VerificationTab,
} from "@/components/dossier-tabs";

const TABS = (q: { questions: number; reality: number; priorArt: number; supply: number; demand: number; verif: string }) => [
  { key: "passport", label: "Паспорт" },
  { key: "questions", label: "Вопросы комиссии", badge: q.questions },
  { key: "reality", label: "Reality vs Conclusion", badge: q.reality },
  { key: "prior-art", label: "Prior Art", badge: q.priorArt },
  { key: "supply-demand", label: "Supply / Demand", badge: `${q.supply} · ${q.demand}` },
  { key: "verification", label: "Верификация", badge: q.verif },
  { key: "lineage", label: "Lineage" },
];

export default function DossierPage() {
  return (
    <Suspense fallback={null}>
      <DossierPageInner />
    </Suspense>
  );
}

function DossierPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = searchParams.get("tab") || "passport";
  const { activeProjectDetail: detail, activeSynergyGraph, activeRole, setActiveRole } = useHorizonStore();

  const setTab = (key: string) => router.push(`/dossier?tab=${key}`);

  if (!detail) {
    return (
      <section className="screen">
        <main className="wrap">
          <div className="phead">
            <div>
              <div className="eyebrow">
                <IconShield size={14} />
                Комиссия · X-Ray
              </div>
              <h1 className="h1">Досье не выбрано</h1>
              <p className="sub">Загрузите диплом или выберите уже проверенную работу на главном экране.</p>
            </div>
          </div>
          <Link className="btn btn-p" href="/">
            К загрузке
          </Link>
        </main>
      </section>
    );
  }

  const passport = detail.passport || {};
  const audit = passport.deep_harvest_audit || {};
  const scoring = passport.scoring || detail.scoring || {};
  const verif = passport.artifact_verification || {};
  const demandItems: any[] = detail.atomic_demand_items || [];
  const supplyItems: any[] = detail.atomic_supply_items || [];
  const verifiedCount = [verif.repo_alive, verif.has_dependencies, verif.has_clean_paths, verif.has_data_artifact, verif.has_license].filter(
    Boolean
  ).length;

  const tabs = TABS({
    questions: (audit.commission_defense_questions || []).length,
    reality: (audit.future_work_linter_items || []).length,
    priorArt: (audit.prior_art_radar?.similar_past_projects || []).length,
    supply: supplyItems.length,
    demand: demandItems.length,
    verif: `${verifiedCount}/5`,
  });

  return (
    <section className="screen">
      <main className="wrap">
        <div className="phead">
          <div style={{ minWidth: 0, flex: "1 1 640px" }}>
            <div className="eyebrow">
              <IconShield size={14} />
              X-Ray досье · ревизия {detail.revision_number || 1}
            </div>
            <h1 className="h1">{detail.title}</h1>
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
          <Link className="btn btn-g" href="/">
            Новый аудит
          </Link>
        </div>

        {(detail.security_alert || detail.plagiarism_alert) && (
          <div style={{ marginBottom: 20 }}>
            <AlertBanner>
              {detail.security_alert && (
                <div style={{ fontWeight: 600 }}>🚨 {detail.security_alert}</div>
              )}
              {detail.plagiarism_alert && <div style={{ fontWeight: 600 }}>🚨 {detail.plagiarism_alert}</div>}
            </AlertBanner>
          </div>
        )}

        <section
          className="card"
          style={{ padding: "14px 20px", marginBottom: 20, display: "flex", alignItems: "center", gap: 28, flexWrap: "wrap" }}
        >
          <div className="row" style={{ gap: 14 }}>
            <ScoreRing score100={scoring.final_handover_score ?? detail.final_handover_score ?? 0} size={48} stroke={5} />
            <div>
              <div className="xs fa">Handover score</div>
              <div className="sm" style={{ fontWeight: 500 }}>{archetypeLabel(detail.lifecycle_archetype)}</div>
            </div>
          </div>
          <div style={{ width: 1, height: 32, background: "var(--ln)" }} />
          <div>
            <div className="xs fa">Разрывы</div>
            <div style={{ marginTop: 2 }}>
              <span className={`chip ${gapSeverityChipClass(audit.reality_vs_conclusion_gap?.gap_severity)}`}>
                <span className="d" />
                {gapSeverityLabel(audit.reality_vs_conclusion_gap?.gap_severity)}
              </span>
            </div>
          </div>
          <div>
            <div className="xs fa">Безопасность</div>
            <div className="sm" style={{ fontWeight: 500, marginTop: 4 }}>
              {detail.security_alert ? "угроза найдена" : "0 угроз"}
            </div>
          </div>
          <div>
            <div className="xs fa">Плагиат</div>
            <div className="sm" style={{ fontWeight: 500, marginTop: 4 }}>
              {detail.plagiarism_alert ? "совпадение найдено" : "0 совпадений"}
            </div>
          </div>
          <div className="row" style={{ marginLeft: "auto", gap: 8 }}>
            <span className="xs fa">Вы просматриваете как</span>
            <div className="row" style={{ gap: 4 }}>
              {(["COMMISSION", "STUDENT"] as const).map((r) => (
                <button
                  key={r}
                  type="button"
                  className={`lnk sm ${activeRole === r ? "tx" : "fa"}`}
                  style={{ fontWeight: activeRole === r ? 600 : 400 }}
                  onClick={() => setActiveRole(r)}
                >
                  {r === "COMMISSION" ? "Комиссия" : "Студент"}
                </button>
              ))}
            </div>
          </div>
        </section>

        <div style={{ marginBottom: 20 }}>
          <SegNav items={tabs} active={tab} onChange={setTab} ariaLabel="Разделы досье" />
        </div>

        {tab === "passport" && <PassportTab detail={detail} onNavigate={setTab} />}
        {tab === "questions" && <QuestionsTab detail={detail} activeRole={activeRole} />}
        {tab === "reality" && <RealityTab detail={detail} />}
        {tab === "prior-art" && <PriorArtTab detail={detail} />}
        {tab === "supply-demand" && <SupplyDemandTab detail={detail} synergyGraph={activeSynergyGraph} />}
        {tab === "verification" && <VerificationTab detail={detail} />}
        {tab === "lineage" && <LineageTab detail={detail} synergyGraph={activeSynergyGraph} />}
      </main>
    </section>
  );
}
