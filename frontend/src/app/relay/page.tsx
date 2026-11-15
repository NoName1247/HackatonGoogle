"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchAndSetProjectDetail, fetchProjectSynergy, fetchProjectsCatalog } from "@/lib/api_and_sse";
import { useHorizonStore } from "@/lib/store";
import { IconRelay, IconSearch, IconBox } from "@/components/icons";
import { domainProfileColor, domainProfileLabel, formatScore100 } from "@/lib/format";
import { archetypeChipClass, archetypeLabel } from "@/lib/format";

const DOMAIN_OPTIONS = [
  { value: "all", label: "Все домены" },
  { value: "IT_AND_DATA_SCIENCE", label: "ИТ и Data Science" },
  { value: "ENGINEERING_AND_HARDWARE", label: "Инженерия и оборудование" },
  { value: "NATURAL_AND_BIOMEDICAL", label: "Биомедицина и естественные науки" },
  { value: "ECONOMICS_AND_MANAGEMENT", label: "Экономика и менеджмент" },
  { value: "HUMANITIES_SOCIAL_AND_LAW", label: "Гуманитарные, социальные и право" },
];

const MODALITY_OPTIONS = [
  { value: "all", label: "Все модальности" },
  { value: "image", label: "Изображения" },
  { value: "audio", label: "Аудио" },
  { value: "text", label: "Текст / NLP" },
  { value: "tabular", label: "Табличные данные" },
  { value: "signal", label: "Сигналы" },
  { value: "hardware", label: "Оборудование" },
  { value: "empirical_survey", label: "Эмпирическое исследование" },
  { value: "legal_normative", label: "Правовые / нормативные" },
  { value: "multimodal", label: "Мультимодальные" },
];

export default function RelayMarketplacePage() {
  const router = useRouter();
  const {
    filterProfile,
    filterModality,
    filterHasDataset,
    filterPureDonorOnly,
    filterSearchQuery,
    setFilter,
  } = useHorizonStore();

  const [projects, setProjects] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const items = await fetchProjectsCatalog({
        domain_profile: filterProfile,
        modality: filterModality,
        has_dataset: filterHasDataset,
        archetype: filterPureDonorOnly ? "GOLD_STANDARD_COMPLETED" : undefined,
        q: filterSearchQuery,
        limit: 50,
      });
      setProjects(items);
      setTotal(items.length);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterProfile, filterModality, filterHasDataset, filterPureDonorOnly]);

  const handleReset = () => {
    setFilter("filterProfile", "all");
    setFilter("filterModality", "all");
    setFilter("filterHasDataset", false);
    setFilter("filterPureDonorOnly", false);
    setFilter("filterSearchQuery", "");
  };

  const handleOpen = async (pid: string) => {
    await fetchAndSetProjectDetail(pid);
    await fetchProjectSynergy(pid);
    router.push("/relay/project");
  };

  return (
    <section className="screen">
      <main className="wrap">
        <div className="phead">
          <div>
            <div className="eyebrow">
              <IconRelay size={14} />
              Студент · Relay
            </div>
            <h1 className="h1">Relay маркетплейс</h1>
            <p className="sub">Ни один диплом не заканчивается в столе. Найдите работу, чьи результаты станут стартом для вашей.</p>
          </div>
        </div>

        <section className="card" style={{ padding: 16, marginBottom: 20 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
            <div className="field" style={{ flex: "2 1 320px" }}>
              <label htmlFor="mk-q" className="flabel">Поиск</label>
              <div className="inpw">
                <IconSearch size={16} />
                <input
                  id="mk-q"
                  className="inp"
                  type="search"
                  placeholder="Название или автор"
                  value={filterSearchQuery}
                  onChange={(e) => setFilter("filterSearchQuery", e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && load()}
                />
              </div>
            </div>
            <div style={{ flex: "1 1 220px" }}>
              <div className="field">
                <label htmlFor="mk-dom">Домен</label>
                <div className="sel">
                  <select id="mk-dom" className="inp" value={filterProfile} onChange={(e) => setFilter("filterProfile", e.target.value)}>
                    {DOMAIN_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
            <div style={{ flex: "1 1 220px" }}>
              <div className="field">
                <label htmlFor="mk-mod">Модальность</label>
                <div className="sel">
                  <select id="mk-mod" className="inp" value={filterModality} onChange={(e) => setFilter("filterModality", e.target.value)}>
                    {MODALITY_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
            <div className="row" style={{ gap: 20, padding: "0 4px", flexWrap: "wrap" }}>
              <label className="cb sm">
                <input type="checkbox" checked={filterHasDataset} onChange={(e) => setFilter("filterHasDataset", e.target.checked)} />
                Есть датасет
              </label>
              <label className="cb sm">
                <input type="checkbox" checked={filterPureDonorOnly} onChange={(e) => setFilter("filterPureDonorOnly", e.target.checked)} />
                Только доноры (TRL 6–7)
              </label>
            </div>
            <button type="button" className="btn btn-g" onClick={handleReset}>Сбросить</button>
            <button type="button" className="btn btn-p" onClick={load}>Найти</button>
          </div>
        </section>

        <div className="between" style={{ marginBottom: 16, flexWrap: "wrap" }}>
          <span className="sm mu">
            {loading ? "Загрузка…" : <>Показано <span className="tx">{total}</span> работ</>}
          </span>
        </div>

        {!loading && projects.length === 0 && (
          <div className="card xs mu">Ничего не найдено — попробуйте изменить фильтры.</div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(min(380px,100%),1fr))", gap: 16 }}>
          {projects.map((p) => {
            const score = p.final_handover_score ?? 0;
            const demandTasks: any[] = p.demand_summary?.tasks || [];
            const openCount = demandTasks.filter((t: any) => t.claim_status === "OPEN").length;
            return (
              <article key={p.project_id} className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div className="wrapr">
                  <span className="chip">
                    <span className="d" style={{ background: domainProfileColor(p.domain_profile) }} />
                    {domainProfileLabel(p.domain_profile)}
                  </span>
                  <span className={`chip ${archetypeChipClass(p.lifecycle_archetype)}`}>
                    <span className="d" />
                    {archetypeLabel(p.lifecycle_archetype)}
                  </span>
                </div>
                <div>
                  <h3 className="h3 clamp2" style={{ fontSize: 17, minHeight: 46 }}>{p.title}</h3>
                  <div className="row sm mu" style={{ marginTop: 8, gap: 12, flexWrap: "wrap" }}>
                    <span>{p.author}</span>
                    <span>{p.year}</span>
                  </div>
                </div>
                <div>
                  <div className="between">
                    <span className="xs fa">Handover score</span>
                    <span className="num">{formatScore100(score)}</span>
                  </div>
                  <div className="bar" style={{ marginTop: 8 }}>
                    <i style={{ width: `${Math.min(100, score)}%`, background: "var(--ok)" }} />
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <div className="tile" style={{ padding: "12px 14px" }}>
                    <div className="xs fa">Supply</div>
                    <div className="num" style={{ fontSize: 20 }}>
                      {p.supply_summary?.items_count ?? 0}
                      <span className="sm fa" style={{ fontWeight: 500 }}> актива</span>
                    </div>
                  </div>
                  <div className="tile" style={{ padding: "12px 14px" }}>
                    <div className="xs fa">Demand</div>
                    <div className="num" style={{ fontSize: 20, color: "var(--ok)" }}>
                      {openCount}
                      <span className="sm fa" style={{ fontWeight: 500 }}> из {demandTasks.length} открыто</span>
                    </div>
                  </div>
                </div>
                {p.supply_summary?.data_summary && (
                  <div className="row sm mu" style={{ gap: 10, alignItems: "flex-start" }}>
                    <IconBox size={16} style={{ color: "var(--ac)", marginTop: 2, flex: "none" }} />
                    <span className="clamp2">{p.supply_summary.data_summary}</span>
                  </div>
                )}
                <button type="button" className="btn" style={{ marginTop: "auto" }} onClick={() => handleOpen(p.project_id)}>
                  Подробнее
                </button>
              </article>
            );
          })}
        </div>
      </main>
    </section>
  );
}
