"use client";

import React from "react";
import { ScoreRing, EmptyState } from "./ui";
import {
  IconArrowRight,
  IconBox,
  IconCheck,
  IconClose,
  IconFunction,
  IconFlag,
  IconLock,
} from "./icons";
import {
  claimStatusChipClass,
  claimStatusLabel,
  gapSeverityChipClass,
  gapSeverityLabel,
  macroCategoryColor,
  probeStatusLabel,
} from "@/lib/format";
import SynergyGraph from "./SynergyGraph";

function Bar({ label, value, max }: { label: string; value: number; max: number }) {
  const frac = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
  const color = frac >= 0.75 ? "var(--ok)" : frac >= 0.5 ? "var(--wa)" : "var(--er)";
  return (
    <div>
      <div className="between">
        <span className="sm mu">{label}</span>
        <span className="num sm">
          {value}/{max}
        </span>
      </div>
      <div className="bar" style={{ marginTop: 8 }}>
        <i style={{ width: `${frac * 100}%`, background: color }} />
      </div>
    </div>
  );
}

export function PassportTab({ detail, onNavigate }: { detail: any; onNavigate: (tab: string) => void }) {
  const passport = detail.passport || {};
  const scoring = passport.scoring || detail.scoring || {};
  const audit = passport.deep_harvest_audit || {};
  const supply = passport.supply_assets || {};
  const demand = passport.demand_horizon || {};
  const demandItems: any[] = detail.atomic_demand_items || [];
  const openDemand = demandItems.filter((d) => d.claim_status === "OPEN").length;

  return (
    <div className="bento">
      <section
        className="card"
        style={{ gridColumn: "span 3", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14, textAlign: "center" }}
      >
        <div className="lbl">Handover score</div>
        <ScoreRing score100={scoring.final_handover_score ?? detail.final_handover_score ?? 0} size={176} stroke={12} label="из 100" />
        <div className="xs fa">Готовность передать работу дальше</div>
      </section>

      <section className="card" style={{ gridColumn: "span 5" }}>
        <h2 className="lbl" style={{ marginBottom: 18 }}>Из чего складывается оценка</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Bar label="Код / методология" value={scoring.raw_code_score ?? 0} max={25} />
          <Bar label="Данные" value={scoring.raw_data_score ?? 0} max={25} />
          <Bar label="Валидность (аудит)" value={scoring.validity_score ?? 0} max={20} />
          <Bar label="Горизонт / зрелость" value={scoring.roadmap_or_maturity_score ?? 0} max={30} />
        </div>
        {scoring.time_decay_code !== undefined && (
          <p className="xs fa mono" style={{ marginTop: 14 }}>
            Временной коэффициент: код ×{scoring.time_decay_code} · данные ×{scoring.time_decay_data}
          </p>
        )}
      </section>

      <div className="stack" style={{ gridColumn: "span 4" }}>
        <section className="card" style={{ flex: 1 }}>
          <div className="between">
            <h2 className="lbl">Серьёзность разрывов</h2>
            <span className={`chip ${gapSeverityChipClass(audit.reality_vs_conclusion_gap?.gap_severity)}`}>
              <span className="d" />
              {gapSeverityLabel(audit.reality_vs_conclusion_gap?.gap_severity)}
            </span>
          </div>
          <p style={{ marginTop: 14, textWrap: "pretty" } as React.CSSProperties}>
            {audit.reality_vs_conclusion_gap?.conclusion_claim
              ? "Есть разрыв между утверждением в выводах и данными из средних глав."
              : "Разрывы не обнаружены."}
          </p>
          <button type="button" className="lnk sm" style={{ marginTop: 12 }} onClick={() => onNavigate("reality")}>
            Смотреть разрывы
            <IconArrowRight size={14} />
          </button>
        </section>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <section className="card" style={{ padding: 18 }}>
            <div className="row fa xs" style={{ gap: 6 }}>
              <IconLock size={14} />
              Безопасность
            </div>
            <div className="num" style={{ fontSize: 28, marginTop: 6 }}>{detail.security_alert ? "1" : "0"}</div>
            <div className="xs" style={{ color: detail.security_alert ? "var(--er)" : "var(--ok)" }}>
              {detail.security_alert ? "угроза найдена" : "угроз нет"}
            </div>
          </section>
          <section className="card" style={{ padding: 18 }}>
            <div className="row fa xs" style={{ gap: 6 }}>
              <IconFlag size={14} />
              Плагиат
            </div>
            <div className="num" style={{ fontSize: 28, marginTop: 6 }}>{detail.plagiarism_alert ? "1" : "0"}</div>
            <div className="xs" style={{ color: detail.plagiarism_alert ? "var(--er)" : "var(--ok)" }}>
              {detail.plagiarism_alert ? "совпадение найдено" : "совпадений нет"}
            </div>
          </section>
        </div>
      </div>

      {(supply.code_summary || supply.data_summary) && (
        <section className="card" style={{ gridColumn: "span 6" }}>
          <h2 className="lbl" style={{ marginBottom: 12 }}>Что уже сделано (Supply)</h2>
          {supply.code_summary && <p className="mu" style={{ marginBottom: 8 }}>{supply.code_summary}</p>}
          {supply.data_summary && <p className="mu">{supply.data_summary}</p>}
          <button type="button" className="lnk sm" style={{ marginTop: 12 }} onClick={() => onNavigate("supply-demand")}>
            Смотреть активы
            <IconArrowRight size={14} />
          </button>
        </section>
      )}

      <section className="card" style={{ gridColumn: "span 6" }}>
        <h2 className="lbl" style={{ marginBottom: 12 }}>Что осталось сделать (Demand)</h2>
        <p className="mu">{demand.bottleneck_cluster_label || "Кластер узкого места не определён"}</p>
        <p className="sm mu" style={{ marginTop: 6 }}>
          Открытых задач: <span className="tx">{openDemand}</span> из {demandItems.length}
        </p>
        <button type="button" className="lnk sm" style={{ marginTop: 12 }} onClick={() => onNavigate("supply-demand")}>
          Смотреть задачи
          <IconArrowRight size={14} />
        </button>
      </section>

      {scoring.improvement_recipes?.length > 0 && (
        <section className="card" style={{ gridColumn: "span 12" }}>
          <h2 className="lbl" style={{ marginBottom: 12 }}>Как поднять оценку</h2>
          <ul className="ul ac">
            {scoring.improvement_recipes.map((r: string, i: number) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export function QuestionsTab({ detail, activeRole }: { detail: any; activeRole: string }) {
  const passport = detail.passport || {};
  const questions: string[] = passport.deep_harvest_audit?.commission_defense_questions || [];
  return (
    <section className="card">
      <div className="ch">
        <h2 className="lbl">
          {activeRole === "STUDENT" ? "Вопросы, которые задаст комиссия" : "Вопросы для защиты (ГАК)"}
        </h2>
        <span className="xs fa">Из разрыва между выводами и главами 2–3</span>
      </div>
      {questions.length === 0 ? (
        <EmptyState>Вопросы не были сгенерированы для этой работы.</EmptyState>
      ) : (
        <ol className="ol">
          {questions.map((q, i) => (
            <li key={i}>
              <span>{q}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export function RealityTab({ detail }: { detail: any }) {
  const passport = detail.passport || {};
  const audit = passport.deep_harvest_audit || {};
  const gap = audit.reality_vs_conclusion_gap;
  const linterItems: any[] = audit.future_work_linter_items || [];
  const discarded: any[] = audit.discarded_approaches || [];

  return (
    <div className="stack">
      {gap && (
        <section className="card">
          <div className="between" style={{ flexWrap: "wrap", marginBottom: 20 }}>
            <div>
              <div className="lbl">Разрыв: вывод vs данные</div>
            </div>
            <span className={`chip ${gapSeverityChipClass(gap.gap_severity)}`}>
              {gapSeverityLabel(gap.gap_severity).toUpperCase()} (стр. {gap.source_page})
            </span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(420px,100%),1fr))" }}>
            <div style={{ padding: "0 24px 12px 0" }} className="lbl">Утверждение в выводах</div>
            <div style={{ padding: "0 0 12px 24px" }} className="lbl">Что показывают данные</div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(420px,100%),1fr))", borderTop: "1px solid var(--ln)" }}>
            <div style={{ padding: "20px 24px 20px 0" }}>
              <p style={{ font: "500 16px/1.5 Manrope,Inter,sans-serif" } as React.CSSProperties}>«{gap.conclusion_claim}»</p>
            </div>
            <div style={{ padding: "20px 0 20px 24px", borderLeft: "1px solid var(--ln)" }}>
              <p className="mu">{gap.middle_chapter_reality}</p>
            </div>
          </div>
        </section>
      )}

      <section className="card">
        <h3 className="h3" style={{ marginBottom: 4 }}>Диф-линтер «будущей работы»</h3>
        <p className="xs fa" style={{ marginBottom: 16 }}>
          Отделяет общие маркетинговые формулировки от конкретных инженерных задач
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }} className="mono xs">
          {linterItems.length === 0 && <EmptyState>Линтер не нашёл пунктов для разбора.</EmptyState>}
          {linterItems.map((item: any, idx: number) => {
            const isFluff = item.verdict === "FLUFF";
            const isWeak = item.verdict === "WEAK_SPECIFICITY";
            const chipClass = isFluff ? "c-er" : isWeak ? "c-wa" : "c-ok";
            return (
              <div
                key={idx}
                className="row"
                style={{ justifyContent: "space-between", padding: 12, borderRadius: 12, background: "var(--s2)", border: "1px solid var(--ln)", flexWrap: "wrap", gap: 10 }}
              >
                <span style={{ textDecoration: isFluff ? "line-through" : undefined, opacity: isFluff ? 0.75 : 1 }}>
                  {item.original_sentence}
                </span>
                <span className={`chip ${chipClass}`}>{item.reason_badge}</span>
              </div>
            );
          })}
        </div>
      </section>

      {discarded.length > 0 && (
        <section className="card" style={{ borderColor: "rgba(248,113,113,.4)", background: "rgba(248,113,113,.05)" }}>
          <div className="row" style={{ gap: 8, marginBottom: 12 }}>
            <IconClose size={16} style={{ color: "var(--er)" }} />
            <h3 className="h3" style={{ color: "var(--er)" }}>Отказались от этих подходов — не повторять</h3>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {discarded.map((d: any, i: number) => (
              <div key={i} className="sm tile">
                <span className="tx" style={{ fontWeight: 600 }}>{d.method}</span>{" "}
                <span className="fa">({d.source_location}):</span> {d.failure_reason}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export function PriorArtTab({ detail }: { detail: any }) {
  const passport = detail.passport || {};
  const priorArt: any[] = passport.deep_harvest_audit?.prior_art_radar?.similar_past_projects || [];
  return (
    <section className="card">
      <h2 className="lbl" style={{ marginBottom: 4 }}>Prior Art Radar (5 лет архива)</h2>
      <p className="xs fa" style={{ marginBottom: 16 }}>
        Похожие темы, защищённые на других кафедрах — чтобы не изобретать велосипед
      </p>
      {priorArt.length === 0 ? (
        <EmptyState>Совпадений с прошлыми работами не найдено.</EmptyState>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {priorArt.map((pa, i) => (
            <div key={i} className="tile">
              <div className="between" style={{ flexWrap: "wrap" }}>
                <span className="tx sm" style={{ fontWeight: 600 }}>
                  {pa.title} ({pa.year})
                </span>
                {pa.similarity_score > 0 && <span className="chip c-wa">{Math.round(pa.similarity_score * 100)}% похоже</span>}
              </div>
              <div className="xs fa" style={{ marginTop: 4 }}>
                {pa.department} {pa.author && `· ${pa.author}`}
              </div>
              <div className="sm mu" style={{ marginTop: 6 }}>{pa.similarity_note}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function SupplyDemandTab({ detail, synergyGraph }: { detail: any; synergyGraph: any }) {
  const passport = detail.passport || {};
  const supplyItems: any[] = detail.atomic_supply_items || [];
  const demandItems: any[] = detail.atomic_demand_items || [];
  const matches: any[] = synergyGraph?.internal_matches || [];

  return (
    <div className="stack">
      <section className="card">
        <h2 className="h2" style={{ marginBottom: 4 }}>Supply — доступные активы</h2>
        <p className="sm mu" style={{ marginBottom: 16 }}>Что можно взять из этой работы и использовать в своей</p>
        {supplyItems.length === 0 ? (
          <EmptyState>Активы для передачи не найдены.</EmptyState>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(360px,100%),1fr))", gap: 16 }}>
            {supplyItems.map((s) => (
              <article key={s.id} className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <div className="between">
                  <div className="row">
                    <span className="ico ac">
                      <IconBox size={18} />
                    </span>
                    <div className="h3">{s.asset_type}</div>
                  </div>
                  {s.effective_asset_score !== undefined && (
                    <div style={{ textAlign: "right" }}>
                      <div className="num" style={{ fontSize: 20 }}>{Number(s.effective_asset_score).toFixed(2)}</div>
                      <div className="xs fa">качество</div>
                    </div>
                  )}
                </div>
                <p>{s.domain_specific_text}</p>
                {s.abstract_math_function && (
                  <div className="tile row" style={{ gap: 10, alignItems: "flex-start" }}>
                    <IconFunction size={16} style={{ color: "var(--fa)", marginTop: 2, flex: "none" }} />
                    <code className="mono" style={{ fontSize: "12.5px", overflowWrap: "anywhere" }}>{s.abstract_math_function}</code>
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="card">
        <h2 className="h2" style={{ marginBottom: 4 }}>Demand — открытые задачи</h2>
        <p className="sm mu" style={{ marginBottom: 16 }}>Каждый пункт может стать темой для следующей работы</p>
        {demandItems.length === 0 ? (
          <EmptyState>Открытых задач не найдено.</EmptyState>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(380px,100%),1fr))", gap: 16 }}>
            {demandItems.map((d) => (
              <article key={d.id} className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div className="between" style={{ alignItems: "flex-start", flexWrap: "wrap" }}>
                  <span className="chip">
                    <span className="d" style={{ background: macroCategoryColor(d.macro_category) }} />
                    {d.macro_category}
                  </span>
                  <span className={`chip ${claimStatusChipClass(d.claim_status)}`}>
                    <span className="d" />
                    {claimStatusLabel(d.claim_status)}
                  </span>
                </div>
                <p className="h3" style={{ fontWeight: 600 }}>{d.task_description}</p>
                {d.operating_envelope?.hard_preconditions?.length > 0 && (
                  <div className="row sm mu" style={{ gap: 10, alignItems: "flex-start" }}>
                    <IconFlag size={16} style={{ color: "var(--fa)", marginTop: 2, flex: "none" }} />
                    <span>{d.operating_envelope.hard_preconditions.join(", ")}</span>
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      {matches.length > 0 && (
        <section className="card">
          <h2 className="h2" style={{ marginBottom: 4, color: "var(--ok)" }}>Готовые решения для узких мест</h2>
          <p className="sm mu" style={{ marginBottom: 16 }}>
            Активы с других кафедр, закрывающие Demand этой работы (асимметричный TRIZ-матчинг)
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {matches.slice(0, 3).map((m, i) => (
              <div key={i} className="tile" style={{ borderColor: "rgba(74,222,128,.3)" }}>
                <div className="between">
                  <span className="chip c-ok">{Math.round((m.formula?.synergy_score || 0) * 100)}% match</span>
                  <span className="xs fa mono">{m.donor_department}</span>
                </div>
                <div className="sm tx" style={{ fontWeight: 600, marginTop: 6 }}>{m.donor_title}</div>
                <div className="sm mu" style={{ marginTop: 4 }}>
                  <span className="c-ok">Supply:</span> {m.donor_supply_text}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export function VerificationTab({ detail }: { detail: any }) {
  const verif = detail.passport?.artifact_verification || {};
  const checks = [
    { label: "Репозиторий доступен (> 5 файлов)", ok: verif.repo_alive },
    { label: "Зависимости описаны (requirements/Dockerfile)", ok: verif.has_dependencies },
    { label: "Чистые относительные пути, выполненные ноутбуки", ok: verif.has_clean_paths },
    { label: "Проверенные данные / веса (не LFS-указатель)", ok: verif.has_data_artifact },
    { label: "Открытая академическая лицензия", ok: verif.has_license },
  ];
  return (
    <div className="stack">
      <section className="card">
        <div className="ch">
          <h2 className="lbl">Автоматическая верификация артефактов</h2>
          <span className="chip c-in">{probeStatusLabel(verif.probe_status)}</span>
        </div>
        <p className="xs fa mono" style={{ marginBottom: 16, overflowWrap: "anywhere" }}>
          {verif.repo_url || "Только методология из текста документа (без репозитория)"}
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }} className="mono xs">
          {checks.map((c, i) => (
            <div key={i} className="between tile">
              <span className="sm mu">{c.label}</span>
              <span className={c.ok ? "c-ok" : "c-er"} style={{ fontWeight: 700 }}>
                {c.ok ? <IconCheck size={14} /> : <IconClose size={14} />}
              </span>
            </div>
          ))}
        </div>
      </section>
      {verif.detected_stack?.length > 0 && (
        <section className="card">
          <h2 className="lbl" style={{ marginBottom: 12 }}>Определённый технологический стек</h2>
          <div className="wrapr">
            {verif.detected_stack.map((s: string, i: number) => (
              <span key={i} className="chip">{s}</span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export function LineageTab({ detail, synergyGraph }: { detail: any; synergyGraph: any }) {
  const nodes = detail.lineage_graph?.nodes || [];
  return (
    <section className="card" style={{ padding: 0, overflow: "hidden" }}>
      <div style={{ padding: 20 }}>
        <h2 className="lbl" style={{ marginBottom: 4 }}>«Git for Science» — дерево поколений</h2>
        <p className="xs fa">Gen 1 → Gen 2 → Gen 3, с подписанным контрактом цитирования на каждом шаге</p>
      </div>
      {nodes.length <= 1 ? (
        <div style={{ padding: "0 20px 20px" }}>
          <EmptyState>Эта работа пока не передавалась по эстафете — она единственный узел в дереве.</EmptyState>
        </div>
      ) : (
        <SynergyGraph projectDetail={detail} synergyGraph={synergyGraph} viewMode="LINEAGE" />
      )}
    </section>
  );
}
