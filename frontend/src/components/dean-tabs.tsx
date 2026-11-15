"use client";

import React from "react";
import { EmptyState } from "./ui";
import { IconDownload } from "./icons";
import { formatScore100 } from "@/lib/format";
import { GoldenBubbleChart, TreemapChart } from "./DeanCharts";

export function TreemapTab({
  treemapHierarchy,
  selectedCluster,
  onSelectCluster,
  onExportGrant,
  busy,
}: {
  treemapHierarchy: any[];
  selectedCluster: any | null;
  onSelectCluster: (cluster: any) => void;
  onExportGrant: (clusterId: string) => void;
  busy: boolean;
}) {
  return (
    <div className="stack">
      <section className="card">
        <h3 className="h3">Карта узких мест (7 макро-категорий → HDBSCAN микро-кластеры)</h3>
        <p className="xs fa" style={{ marginTop: 4, marginBottom: 12 }}>
          Клик по кластеру открывает карточку ROI и генератор обоснования гранта
        </p>
        {(!treemapHierarchy || treemapHierarchy.length === 0) ? (
          <EmptyState>Кластеры узких мест ещё не рассчитаны.</EmptyState>
        ) : (
          <TreemapChart treemapHierarchy={treemapHierarchy} onSelectCluster={onSelectCluster} />
        )}
      </section>

      {selectedCluster && (
        <section className="card" style={{ borderColor: "rgba(122,162,255,.4)", background: "rgba(var(--acr),.06)" }}>
          <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 16 }}>
            <div>
              <div className="xs fa" style={{ marginBottom: 4 }}>🎯 Карточка ROI — [{selectedCluster.macro_category}]</div>
              <h3 className="h3">{selectedCluster.cluster_label}</h3>
              <p className="sm" style={{ color: "var(--ok)", marginTop: 4 }}>{selectedCluster.estimated_unlock_roi}</p>
              <p className="sm mu" style={{ marginTop: 4 }}>
                Кафедры: {selectedCluster.departments_list?.join(", ")} · Руководители: {selectedCluster.supervisors_list?.slice(0, 4).join(", ")}
              </p>
            </div>
            {!String(selectedCluster.cluster_id).startsWith("emerging_") && (
              <button type="button" className="btn btn-p" disabled={busy} onClick={() => onExportGrant(selectedCluster.cluster_id)}>
                Заявка на целевую закупку / грант
              </button>
            )}
          </div>
        </section>
      )}
    </div>
  );
}

export function GoldenTab({
  goldenReserveMatrix,
  selectedTopicIds,
  onToggle,
}: {
  goldenReserveMatrix: any[];
  selectedTopicIds: string[];
  onToggle: (id: string) => void;
}) {
  return (
    <section className="card">
      <h3 className="h3">«Золотой резерв» (ценность актива × горизонт продолжения)</h3>
      <p className="xs fa" style={{ marginTop: 4, marginBottom: 12 }}>
        Красные точки справа сверху — ценные работы, которые ещё не взяли по эстафете. Клик добавляет в банк тем.
      </p>
      {(!goldenReserveMatrix || goldenReserveMatrix.length === 0) ? (
        <EmptyState>Нет данных для матрицы золотого резерва.</EmptyState>
      ) : (
        <GoldenBubbleChart goldenReserveMatrix={goldenReserveMatrix} onSelectProjectBubble={onToggle} />
      )}
      {selectedTopicIds.length > 0 && (
        <p className="xs fa mono" style={{ marginTop: 12 }}>Выбрано для банка тем: {selectedTopicIds.length}</p>
      )}
    </section>
  );
}

export function TRLTab({ projects }: { projects: any[] }) {
  return (
    <section>
      <h2 className="lbl" style={{ marginBottom: 12 }}>🚀 TRL 6–7 — готовы к передаче в индустрию / патентованию</h2>
      {projects.length === 0 ? (
        <EmptyState>Пока нет проектов, достигших TRL 6–7.</EmptyState>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(380px,100%),1fr))", gap: 12 }}>
          {projects.map((p) => (
            <div key={p.project_id} className="card" style={{ borderColor: "rgba(251,191,36,.4)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
              <div>
                <span className="chip c-wa">TRL 6–7 · индустрия / патент</span>
                <div className="tx" style={{ fontWeight: 600, marginTop: 8 }}>{p.title}</div>
                <div className="xs fa" style={{ marginTop: 4 }}>
                  {p.department} · {p.author} · рук. {p.supervisor}
                </div>
              </div>
              <div className="num" style={{ fontSize: 22, color: "var(--wa)", flex: "none" }}>{formatScore100(p.final_handover_score)}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function ExportTab({
  items,
  selectedTopicIds,
  onToggle,
  onSelectAll,
  onExport,
  busy,
  previewDoc,
}: {
  items: any[];
  selectedTopicIds: string[];
  onToggle: (id: string) => void;
  onSelectAll: (ids: string[]) => void;
  onExport: () => void;
  busy: boolean;
  previewDoc: { title: string; md: string } | null;
}) {
  const topics = items.slice(0, 30);
  return (
    <div className="bento">
      <section className="card" style={{ gridColumn: "span 7", display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="between" style={{ flexWrap: "wrap" }}>
          <div>
            <h2 className="h3">Темы для банка ВКР</h2>
            <p className="xs fa" style={{ marginTop: 2 }}>Открытые задачи из анализа узких мест и золотого резерва</p>
          </div>
          <div className="row" style={{ gap: 4 }}>
            <button type="button" className="btn btn-g" onClick={() => onSelectAll(topics.map((t) => t.project_id))}>Выбрать все</button>
            <button type="button" className="btn btn-g" onClick={() => onSelectAll([])}>Снять выбор</button>
          </div>
        </div>
        {topics.length === 0 ? (
          <EmptyState>Нет тем для формирования банка.</EmptyState>
        ) : (
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
            {topics.map((item) => (
              <li key={item.project_id}>
                <label className="cb tile" style={{ padding: "12px 16px", alignItems: "flex-start" }}>
                  <input type="checkbox" checked={selectedTopicIds.includes(item.project_id)} onChange={() => onToggle(item.project_id)} style={{ marginTop: 3 }} />
                  <span style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
                    <span style={{ fontWeight: 500 }}>{item.title}</span>
                    <span className="xs mu">
                      {item.department} · {item.author}, {item.year} · {formatScore100(item.final_handover_score)} баллов
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
        <div className="between" style={{ flexWrap: "wrap" }}>
          <span className="sm mu">
            Выбрано: <span className="num tx" style={{ fontSize: 16 }}>{selectedTopicIds.length}</span>
          </span>
          <button type="button" className="btn btn-p" disabled={busy || selectedTopicIds.length === 0} onClick={onExport}>
            <IconDownload size={16} />
            Экспорт банка тем
          </button>
        </div>
      </section>

      <section className="card" style={{ gridColumn: "span 5", display: "flex", flexDirection: "column", gap: 16 }}>
        <h2 className="h3">Последний экспорт</h2>
        {previewDoc ? (
          <div>
            <p className="sm mu" style={{ marginBottom: 8 }}>{previewDoc.title}</p>
            <div className="md" style={{ background: "var(--bg)", border: "1px solid var(--ln)", borderRadius: 14, padding: 20, maxHeight: 320, overflowY: "auto" }}>
              <pre className="code" style={{ background: "none", border: "none", padding: 0 }}>{previewDoc.md}</pre>
            </div>
          </div>
        ) : (
          <EmptyState>Экспортируйте банк тем, чтобы увидеть документ здесь.</EmptyState>
        )}
      </section>
    </div>
  );
}

export function ModerationTab({
  domains,
  onApprove,
  busy,
}: {
  domains: any[];
  onApprove: (id: string) => void;
  busy: boolean;
}) {
  return (
    <section className="card">
      <h2 className="lbl" style={{ marginBottom: 12 }}>Модерация внешних доменов</h2>
      {domains.length === 0 ? (
        <EmptyState>Нет неизвестных внешних доменов, ожидающих модерации.</EmptyState>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {domains.map((d) => (
            <div key={d.id} className="tile between">
              <div className="sm">
                <span className="tx mono" style={{ fontWeight: 600 }}>{d.domain}</span>
                <span className="fa"> — пример: {d.sample_url}</span>
              </div>
              <button type="button" className="btn btn-p" disabled={busy} onClick={() => onApprove(d.id)}>
                Одобрить и перепроверить
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function FinOpsTab({
  dailySpend,
  dailyBudget,
  totalProjects,
}: {
  dailySpend: number;
  dailyBudget: number;
  totalProjects: number;
}) {
  const pct = dailyBudget > 0 ? (dailySpend / dailyBudget) * 100 : 0;
  const perProject = totalProjects > 0 ? dailySpend / totalProjects : 0;
  return (
    <div className="bento">
      <section className="card" style={{ gridColumn: "span 8" }}>
        <div className="lbl">Расход бюджета LLM</div>
        <div className="row" style={{ gap: 12, alignItems: "baseline", marginTop: 10, flexWrap: "wrap" }}>
          <span className="num" style={{ fontSize: 56, lineHeight: 1 }}>${dailySpend.toFixed(2)}</span>
          <span className="mu">из ${dailyBudget.toFixed(2)}</span>
        </div>
        <div className="bar" style={{ height: 12, marginTop: 20 }}>
          <i style={{ width: `${Math.min(100, pct)}%`, background: "var(--ac)" }} />
        </div>
        <div className="between sm" style={{ marginTop: 10 }}>
          <span className="mu">Использовано {pct.toFixed(1)}%</span>
          <span className="mu">
            Осталось <span className="tx" style={{ fontWeight: 600 }}>${Math.max(0, dailyBudget - dailySpend).toFixed(2)}</span>
          </span>
        </div>
      </section>
      <div className="stack" style={{ gridColumn: "span 4" }}>
        <section className="card" style={{ flex: 1 }}>
          <div className="lbl">Обработано проектов</div>
          <div className="num" style={{ fontSize: 34, marginTop: 6 }}>{totalProjects}</div>
        </section>
        <section className="card" style={{ flex: 1 }}>
          <div className="lbl">Средняя стоимость</div>
          <div className="num" style={{ fontSize: 34, marginTop: 6 }}>${perProject.toFixed(3)}</div>
          <div className="xs fa">за один проект</div>
        </section>
      </div>
    </div>
  );
}
