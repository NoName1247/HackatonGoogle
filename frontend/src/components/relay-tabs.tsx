"use client";

import React, { useState } from "react";
import { EmptyState, Modal, ScoreRing } from "./ui";
import { IconBox, IconCheck, IconCopy, IconDownload, IconFlag, IconFunction, IconRefresh } from "./icons";
import { claimStatusChipClass, claimStatusLabel, macroCategoryColor } from "@/lib/format";
import { claimProjectBatonApi, fetchProjectSynergy, generateHandoverPackageApi } from "@/lib/api_and_sse";
import SynergyGraph from "./SynergyGraph";

export function PassportTab({ detail, onNavigate }: { detail: any; onNavigate: (tab: string) => void }) {
  const passport = detail.passport || {};
  const scoring = passport.scoring || detail.scoring || {};
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
      </section>

      <section className="card" style={{ gridColumn: "span 9" }}>
        <h2 className="lbl" style={{ marginBottom: 12 }}>Что уже сделано (Supply)</h2>
        <p className="mu">{supply.code_summary || supply.data_summary || "Описание активов не извлечено."}</p>
        <button type="button" className="lnk sm" style={{ marginTop: 12 }} onClick={() => onNavigate("supply")}>
          Смотреть активы →
        </button>
        <hr className="hl" />
        <h2 className="lbl" style={{ marginBottom: 12 }}>Что осталось сделать (Demand)</h2>
        <p className="mu">{demand.bottleneck_cluster_label || "Кластер узкого места не определён."}</p>
        <p className="sm mu" style={{ marginTop: 6 }}>
          Открытых задач: <span className="tx">{openDemand}</span> из {demandItems.length}
        </p>
        <button type="button" className="lnk sm" style={{ marginTop: 12 }} onClick={() => onNavigate("demand")}>
          Взять задачу →
        </button>
      </section>
    </div>
  );
}

export function SupplyTab({ detail }: { detail: any }) {
  const supplyItems: any[] = detail.atomic_supply_items || [];
  return (
    <section>
      <div className="between" style={{ marginBottom: 16 }}>
        <div>
          <h2 className="h2">Доступные активы</h2>
          <p className="sm mu" style={{ marginTop: 4 }}>Что можно взять из этой работы и использовать в своей</p>
        </div>
      </div>
      {supplyItems.length === 0 ? (
        <EmptyState>Активы для передачи не найдены.</EmptyState>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(360px,100%),1fr))", gap: 16 }}>
          {supplyItems.map((s) => (
            <article key={s.id} className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
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
              {s.operating_envelope?.hard_preconditions?.length > 0 && (
                <div className="row sm mu" style={{ gap: 10, alignItems: "flex-start" }}>
                  <IconFlag size={16} style={{ color: "var(--fa)", marginTop: 2, flex: "none" }} />
                  <span>{s.operating_envelope.hard_preconditions.join(", ")}</span>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export function DemandTab({ detail, onClaim }: { detail: any; onClaim: (item: any) => void }) {
  const demandItems: any[] = detail.atomic_demand_items || [];
  const counts = ["OPEN", "RESERVED_PENDING", "ASSIGNED", "COMPLETED"].map((s) => ({
    status: s,
    n: demandItems.filter((d) => d.claim_status === s).length,
  }));

  return (
    <section>
      <div className="between" style={{ marginBottom: 16, flexWrap: "wrap" }}>
        <div>
          <h2 className="h2">Открытые задачи</h2>
          <p className="sm mu" style={{ marginTop: 4 }}>Возьмите задачу как тему своей работы — со ссылкой на оригинал</p>
        </div>
        <div className="wrapr">
          {counts.map((c) => (
            <React.Fragment key={c.status}>
              <span className={`chip ${claimStatusChipClass(c.status)}`}>
                <span className="d" />
                {claimStatusLabel(c.status)}
              </span>
              <span className="sm fa">{c.n}</span>
            </React.Fragment>
          ))}
        </div>
      </div>

      {demandItems.length === 0 ? (
        <EmptyState>Открытых задач не найдено.</EmptyState>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(420px,100%),1fr))", gap: 16 }}>
          {demandItems.map((d) => (
            <article key={d.id} className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
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
              <div className="wrapr" style={{ marginTop: "auto", paddingTop: 4 }}>
                {d.claim_status === "OPEN" ? (
                  <button type="button" className="btn btn-p" onClick={() => onClaim(d)}>
                    Взять эстафету
                  </button>
                ) : (
                  <button type="button" className="btn" disabled>
                    {claimStatusLabel(d.claim_status)}
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export function SynergyTab({
  detail,
  synergyGraph,
  onGenerateMergeSpec,
}: {
  detail: any;
  synergyGraph: any;
  onGenerateMergeSpec: (match: any) => void;
}) {
  const [bountyQuery, setBountyQuery] = useState("");
  const matches: any[] = synergyGraph?.internal_matches || [];

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    await fetchProjectSynergy(detail.project_id, bountyQuery);
  };

  return (
    <div className="stack">
      <section className="card">
        <h2 className="h3" style={{ marginBottom: 12 }}>Corporate Bounty Funnel</h2>
        <form onSubmit={handleSearch} className="row" style={{ gap: 8 }}>
          <input
            className="inp"
            type="text"
            placeholder="Индустриальная задача, например «подавление шума на 2D-матрицах»…"
            value={bountyQuery}
            onChange={(e) => setBountyQuery(e.target.value)}
          />
          <button type="submit" className="btn btn-p" style={{ flex: "none" }}>Найти активы</button>
        </form>
      </section>

      <SynergyGraph projectDetail={detail} synergyGraph={synergyGraph} viewMode="SYNERGY" />

      <section>
        <h2 className="lbl" style={{ marginBottom: 12 }}>Synergy Bridge — сопоставление Demand A → Supply B</h2>
        {matches.length === 0 ? (
          <EmptyState>Подходящих активов с других кафедр пока не найдено.</EmptyState>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {matches.map((m, idx) => (
              <div key={idx} className="card" style={{ borderColor: "rgba(74,222,128,.3)" }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(260px,100%),1fr))", gap: 12, alignItems: "center" }}>
                  <div className="tile" style={{ borderColor: "rgba(248,113,113,.3)" }}>
                    <div className="xs" style={{ color: "var(--er)", marginBottom: 4 }}>Demand (эта работа)</div>
                    <div className="sm tx" style={{ fontWeight: 600 }}>{m.demand_task_description}</div>
                  </div>
                  <div style={{ textAlign: "center" }}>
                    <span className="chip c-ok">{Math.round((m.formula?.synergy_score || 0) * 100)}% match</span>
                  </div>
                  <div className="tile" style={{ borderColor: "rgba(74,222,128,.3)" }}>
                    <div className="xs" style={{ color: "var(--ok)", marginBottom: 4 }}>
                      Supply ({m.donor_department}, {m.donor_year})
                    </div>
                    <div className="sm tx" style={{ fontWeight: 600 }}>{m.donor_title}</div>
                    <div className="sm mu" style={{ marginTop: 4 }}>{m.donor_supply_text}</div>
                  </div>
                </div>
                <div className="between" style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--ln)", flexWrap: "wrap" }}>
                  <span className="xs fa mono">
                    P_rerank={m.formula?.p_rerank_calibrated} · cos={m.formula?.cosine_similarity} · M_env={m.formula?.m_envelope}
                  </span>
                  <button type="button" className="lnk sm" onClick={() => onGenerateMergeSpec(m)}>
                    Сформировать ТЗ на объединение
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

export function LineageTab({ detail, synergyGraph }: { detail: any; synergyGraph: any }) {
  const nodes = detail.lineage_graph?.nodes || [];
  return (
    <section className="card" style={{ padding: 0, overflow: "hidden" }}>
      <div style={{ padding: 20 }}>
        <h2 className="lbl" style={{ marginBottom: 4 }}>«Git for Science» — дерево поколений</h2>
      </div>
      {nodes.length <= 1 ? (
        <div style={{ padding: "0 20px 20px" }}>
          <EmptyState>Эта работа пока не передавалась по эстафете.</EmptyState>
        </div>
      ) : (
        <SynergyGraph projectDetail={detail} synergyGraph={synergyGraph} viewMode="LINEAGE" />
      )}
    </section>
  );
}

export function PackageTab({ detail }: { detail: any }) {
  const [pkg, setPkg] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    setLoading(true);
    try {
      const res = await generateHandoverPackageApi(detail.project_id);
      setPkg(res);
    } catch (err: any) {
      alert(err?.message || "Не удалось сгенерировать пакет передачи");
    } finally {
      setLoading(false);
    }
  };

  const download = (filename: string, content: string) => {
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section>
      <div className="between" style={{ marginBottom: 16, flexWrap: "wrap" }}>
        <div>
          <h2 className="h2">Пакет передачи</h2>
          <p className="sm mu" style={{ marginTop: 4 }}>HANDOVER_PASSPORT.md и CITATION.cff, готовые для нового исполнителя</p>
        </div>
        <button type="button" className="btn btn-p" disabled={loading} onClick={generate}>
          <IconRefresh size={16} />
          {pkg ? "Сгенерировать заново" : "Сгенерировать пакет"}
        </button>
      </div>

      {!pkg ? (
        <EmptyState>Пакет ещё не сгенерирован.</EmptyState>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(420px,100%),1fr))", gap: 16 }}>
          <DocBlock title="HANDOVER_PASSPORT.md" content={pkg.handover_passport_md} onDownload={() => download("HANDOVER_PASSPORT.md", pkg.handover_passport_md)} />
          <DocBlock title="CITATION.cff" content={pkg.citation_cff} onDownload={() => download("CITATION.cff", pkg.citation_cff)} />
        </div>
      )}
    </section>
  );
}

function DocBlock({ title, content, onDownload }: { title: string; content: string; onDownload: () => void }) {
  return (
    <section className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="between">
        <h3 className="h3">{title}</h3>
        <div className="row" style={{ gap: 4 }}>
          <button type="button" className="btn btn-g ib" aria-label="Копировать" onClick={() => navigator.clipboard?.writeText(content)}>
            <IconCopy size={16} />
          </button>
          <button type="button" className="btn btn-g ib" aria-label="Скачать" onClick={onDownload}>
            <IconDownload size={16} />
          </button>
        </div>
      </div>
      <pre className="code" style={{ maxHeight: 360, overflowY: "auto" }}>{content}</pre>
    </section>
  );
}

export function ClaimModal({
  detail,
  demandItem,
  matches,
  onClose,
  onClaimed,
}: {
  detail: any;
  demandItem: any;
  matches: any[];
  onClose: () => void;
  onClaimed: (msg: string) => void;
}) {
  const [followerName, setFollowerName] = useState("");
  const [supervisorName, setSupervisorName] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [agree, setAgree] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const valid = followerName.trim().length >= 2 && supervisorName.trim().length >= 2 && agree;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setSubmitting(true);
    try {
      const firstMatch = matches[0];
      const res = await claimProjectBatonApi(detail.project_id, {
        demand_item_id: demandItem.id,
        donor_supply_item_id: firstMatch?.donor_supply_item_id,
        follower_student_name: followerName.trim(),
        approving_supervisor_name: supervisorName.trim(),
        new_project_title: newTitle.trim() || undefined,
        accept_citation_contract: true,
      });
      setDone(
        `✅ Эстафета принята! Создан слот поколения Gen+1 (${String(res.child_project_id || "").slice(0, 8)}) с подписанным контрактом цитирования.`
      );
    } catch (err: any) {
      alert(err?.message || "Не удалось зарезервировать задачу (возможно, её уже забрали).");
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    return (
      <Modal title="Эстафета принята" onClose={() => onClaimed(done)} icon={<IconCheck size={20} />}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", gap: 14, padding: "16px 0" }}>
          <p className="mu" style={{ maxWidth: 380 }}>{done}</p>
          <span className="chip c-wa">
            <span className="d" />
            Зарезервировано
          </span>
          <button type="button" className="btn btn-p" onClick={() => onClaimed(done)}>Готово</button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal title="Взять эстафету" subtitle="Задача будет зарезервирована за вами" onClose={onClose} icon={<IconCheck size={20} />}>
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <div className="tile" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div className="xs fa">Вы берёте задачу</div>
          <p style={{ fontWeight: 500 }}>{demandItem.task_description}</p>
          <div className="sm mu">
            Из проекта «{detail.title}» · автор оригинала <span className="tx">{detail.author}</span>
          </div>
        </div>
        <div className="field">
          <label htmlFor="clm-student">
            ФИО студента <span style={{ color: "var(--ac)" }}>*</span>
          </label>
          <input id="clm-student" className="inp" required value={followerName} onChange={(e) => setFollowerName(e.target.value)} placeholder="Например, Сидоров А.В." />
        </div>
        <div className="field">
          <label htmlFor="clm-sup">
            ФИО научного руководителя <span style={{ color: "var(--ac)" }}>*</span>
          </label>
          <input id="clm-sup" className="inp" required value={supervisorName} onChange={(e) => setSupervisorName(e.target.value)} placeholder="Например, Козлов К.К." />
        </div>
        <div className="field">
          <label htmlFor="clm-title">
            Название новой работы <span className="fa">· необязательно</span>
          </label>
          <input id="clm-title" className="inp" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="Можно указать позже" />
        </div>
        <label className="cb tile" style={{ alignItems: "flex-start", padding: "14px 16px" }}>
          <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} style={{ marginTop: 2 }} />
          <span className="sm">
            <span style={{ fontWeight: 500 }}>Обязуюсь указать ссылку на оригинальную работу</span>
            <span className="fa"> · Citation contract</span> <span style={{ color: "var(--ac)" }}>*</span>
          </span>
        </label>
        <div className="between" style={{ flexWrap: "wrap" }}>
          <span className="xs fa">{valid ? "Всё заполнено" : "Заполните обязательные поля и примите условие цитирования"}</span>
          <div className="row" style={{ gap: 8 }}>
            <button type="button" className="btn btn-g" onClick={onClose}>Отмена</button>
            <button type="submit" className="btn btn-p" disabled={!valid || submitting}>
              {submitting ? "…" : "Принять эстафету"}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

export function MergeSpecModal({ content, onClose }: { content: string; onClose: () => void }) {
  return (
    <Modal title="Synergy Merge Specification" maxWidth={720} onClose={onClose}>
      <pre className="code" style={{ maxHeight: 420, overflowY: "auto" }}>{content}</pre>
    </Modal>
  );
}
