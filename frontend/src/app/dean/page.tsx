"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { executeDeanActionApi, fetchDeanAnalyticsApi } from "@/lib/api_and_sse";
import { useHorizonStore } from "@/lib/store";
import { SegNav, Modal } from "@/components/ui";
import { IconAnalytics, IconRefresh } from "@/components/icons";
import {
  ExportTab,
  FinOpsTab,
  GoldenTab,
  ModerationTab,
  TRLTab,
  TreemapTab,
} from "@/components/dean-tabs";

const CURRENT_YEAR = new Date().getFullYear();

export default function DeanAnalyticsPage() {
  return (
    <Suspense fallback={null}>
      <DeanAnalyticsPageInner />
    </Suspense>
  );
}

function DeanAnalyticsPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = searchParams.get("tab") || "treemap";
  const { selectedTopicIds, toggleTopicSelection, setSelectedTopicIds } = useHorizonStore();

  const [year, setYear] = useState<string>("all");
  const [department, setDepartment] = useState("");
  const [analytics, setAnalytics] = useState<any | null>(null);
  const [selectedCluster, setSelectedCluster] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);
  const [exportDoc, setExportDoc] = useState<{ title: string; md: string } | null>(null);

  const setTab = (key: string) => router.push(`/dean?tab=${key}`);

  const load = async () => {
    const data = await fetchDeanAnalyticsApi(year === "all" ? undefined : Number(year), department || undefined);
    setAnalytics(data);
    if (data?.golden_reserve_matrix && selectedTopicIds.length === 0) {
      setSelectedTopicIds(data.golden_reserve_matrix.slice(0, 10).map((x: any) => x.project_id));
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, department]);

  const handleRecluster = async () => {
    setBusy(true);
    try {
      await executeDeanActionApi({ action_type: "trigger_reclustering" });
      await load();
    } finally {
      setBusy(false);
    }
  };

  const handleExportVkrBank = async () => {
    setBusy(true);
    try {
      const res = await executeDeanActionApi({
        action_type: "export_vkr_bank",
        project_ids: selectedTopicIds,
        academic_year_target: `${CURRENT_YEAR}/${CURRENT_YEAR + 1}`,
      });
      setExportDoc({ title: res.document_title, md: res.markdown_content });
    } finally {
      setBusy(false);
    }
  };

  const handleExportGrantMemo = async (clusterId: string) => {
    setBusy(true);
    try {
      const res = await executeDeanActionApi({ action_type: "export_grant_justification", cluster_id: clusterId });
      setExportDoc({ title: res.document_title, md: res.markdown_content });
    } finally {
      setBusy(false);
    }
  };

  const handleApproveDomain = async (domainId: string) => {
    setBusy(true);
    try {
      await executeDeanActionApi({ action_type: "approve_domain", domain_id: domainId });
      await load();
    } finally {
      setBusy(false);
    }
  };

  if (!analytics) {
    return (
      <section className="screen">
        <main className="wrap">
          <p className="xs mu mono">Загрузка аналитики R&D-ресурсов деканата…</p>
        </main>
      </section>
    );
  }

  const tabs = [
    { key: "treemap", label: "Узкие места" },
    { key: "golden", label: "Золотой резерв" },
    { key: "trl", label: "TRL 6–7", badge: analytics.trl_showcase_projects?.length || 0 },
    { key: "export", label: "Экспорт тем" },
    { key: "moderation", label: "Модерация доменов", badge: analytics.pending_domains?.length || 0 },
    { key: "finops", label: "FinOps" },
  ];

  return (
    <section className="screen">
      <main className="wrap">
        <div className="phead">
          <div>
            <div className="eyebrow">
              <IconAnalytics size={14} />
              Деканат · Analytics
            </div>
            <h1 className="h1">Аналитика кафедр</h1>
          </div>
          <div className="row" style={{ gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
            <div className="field" style={{ minWidth: 140 }}>
              <label htmlFor="d-yr">Год</label>
              <div className="sel">
                <select id="d-yr" className="inp" value={year} onChange={(e) => setYear(e.target.value)}>
                  <option value="all">Все годы</option>
                  <option value={CURRENT_YEAR}>{CURRENT_YEAR}</option>
                  <option value={CURRENT_YEAR - 1}>{CURRENT_YEAR - 1}</option>
                  <option value={CURRENT_YEAR - 2}>{CURRENT_YEAR - 2}</option>
                </select>
              </div>
            </div>
            <div className="field" style={{ minWidth: 220 }}>
              <label htmlFor="d-dp">Кафедра</label>
              <input
                id="d-dp"
                className="inp"
                placeholder="Все кафедры"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && load()}
              />
            </div>
            <button type="button" className="btn" disabled={busy} onClick={handleRecluster}>
              <IconRefresh size={16} />
              Пересчитать кластеры
            </button>
          </div>
        </div>

        <div className="bento" style={{ marginBottom: 20 }}>
          <section className="card" style={{ gridColumn: "span 3", padding: 20 }}>
            <div className="lbl">Проектов обработано</div>
            <div className="num" style={{ fontSize: 34, marginTop: 6 }}>{analytics.total_projects}</div>
          </section>
          <section className="card" style={{ gridColumn: "span 3", padding: 20 }}>
            <div className="lbl" style={{ color: "var(--ok)" }}>Пул для эстафеты</div>
            <div className="num" style={{ fontSize: 34, marginTop: 6, color: "var(--ok)" }}>{analytics.relay_candidates_count}</div>
          </section>
          <section className="card" style={{ gridColumn: "span 3", padding: 20 }}>
            <div className="lbl" style={{ color: "var(--wa)" }}>🚀 TRL 6–7 готовы к индустрии</div>
            <div className="num" style={{ fontSize: 34, marginTop: 6, color: "var(--wa)" }}>{analytics.gold_standard_trl_count}</div>
          </section>
          <section className="card" style={{ gridColumn: "span 3", padding: 20 }}>
            <div className="between">
              <span className="lbl">Бюджет LLM</span>
              <span className="xs fa">{((analytics.daily_finops_spend_usd / analytics.daily_finops_budget_usd) * 100 || 0).toFixed(1)}%</span>
            </div>
            <div className="row" style={{ gap: 8, marginTop: 6, alignItems: "baseline" }}>
              <span className="num" style={{ fontSize: 28 }}>${analytics.daily_finops_spend_usd.toFixed(2)}</span>
              <span className="mu">из ${analytics.daily_finops_budget_usd.toFixed(2)}</span>
            </div>
            <div className="bar" style={{ height: 6, marginTop: 10 }}>
              <i style={{ width: `${Math.min(100, (analytics.daily_finops_spend_usd / analytics.daily_finops_budget_usd) * 100 || 0)}%`, background: "var(--ac)" }} />
            </div>
          </section>
        </div>

        <div style={{ marginBottom: 20 }}>
          <SegNav items={tabs} active={tab} onChange={setTab} ariaLabel="Разделы аналитики" />
        </div>

        {tab === "treemap" && (
          <TreemapTab
            treemapHierarchy={analytics.treemap_hierarchy}
            selectedCluster={selectedCluster}
            onSelectCluster={setSelectedCluster}
            onExportGrant={handleExportGrantMemo}
            busy={busy}
          />
        )}
        {tab === "golden" && (
          <GoldenTab goldenReserveMatrix={analytics.golden_reserve_matrix} selectedTopicIds={selectedTopicIds} onToggle={toggleTopicSelection} />
        )}
        {tab === "trl" && <TRLTab projects={analytics.trl_showcase_projects || []} />}
        {tab === "export" && (
          <ExportTab
            items={analytics.golden_reserve_matrix || []}
            selectedTopicIds={selectedTopicIds}
            onToggle={toggleTopicSelection}
            onSelectAll={(ids) => setSelectedTopicIds(ids)}
            onExport={handleExportVkrBank}
            busy={busy}
            previewDoc={exportDoc}
          />
        )}
        {tab === "moderation" && (
          <ModerationTab domains={analytics.pending_domains || []} onApprove={handleApproveDomain} busy={busy} />
        )}
        {tab === "finops" && (
          <FinOpsTab
            dailySpend={analytics.daily_finops_spend_usd}
            dailyBudget={analytics.daily_finops_budget_usd}
            totalProjects={analytics.total_projects}
          />
        )}
      </main>

      {exportDoc && (
        <Modal title={exportDoc.title} maxWidth={820} onClose={() => setExportDoc(null)}>
          <pre className="code" style={{ maxHeight: "60vh", overflowY: "auto" }}>{exportDoc.md}</pre>
        </Modal>
      )}
    </section>
  );
}
