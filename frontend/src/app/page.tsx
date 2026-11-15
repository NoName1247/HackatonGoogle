"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  buildSampleDemoPdfFile,
  fetchAndSetProjectDetail,
  fetchProjectSynergy,
  fetchProjectsCatalog,
  uploadThesisAndSubscribeSSE,
  validatePdfFilePreflight,
} from "@/lib/api_and_sse";
import { useHorizonStore } from "@/lib/store";
import { IconCheck, IconClose, IconFile, IconShield, IconSpinner, IconUpload } from "@/components/icons";
import { formatScore100 } from "@/lib/format";

const TOTAL_STEPS = 6;

function stripStepPrefix(title: string): string {
  return title.replace(/^Step \d+\/\d+:\s*/, "");
}

export default function CommissionMainPage() {
  const router = useRouter();
  const {
    uploadPhase,
    progressPercent,
    progressStep,
    progressTitle,
    progressHistory,
    uploadError,
    resetUploadState,
  } = useHorizonStore();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [repoUrl, setRepoUrl] = useState("");
  const [thesisTitle, setThesisTitle] = useState("");
  const [catalogProjects, setCatalogProjects] = useState<any[]>([]);

  useEffect(() => {
    fetchProjectsCatalog({ limit: 15 }).then(setCatalogProjects);
  }, []);

  useEffect(() => {
    if (uploadPhase === "COMPLETED") {
      router.push("/dossier");
    }
  }, [uploadPhase, router]);

  const onFileChange = async (file: File | null) => {
    setFileError(null);
    setSelectedFile(file);
    if (file) {
      const check = await validatePdfFilePreflight(file);
      if (!check.valid) setFileError(check.error || "Файл не прошёл проверку.");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile || fileError) return;
    await uploadThesisAndSubscribeSSE(selectedFile, repoUrl, thesisTitle);
  };

  const handleRunLiveDemo = async () => {
    const demoFile = buildSampleDemoPdfFile();
    setSelectedFile(demoFile);
    setFileError(null);
    await uploadThesisAndSubscribeSSE(
      demoFile,
      "https://github.com/example/weld-xray-seg",
      "Automated Defect Segmentation in X-Ray Radiographs of Welded Joints"
    );
  };

  const handleSelectCatalogProject = async (pid: string) => {
    if (!pid) return;
    await fetchAndSetProjectDetail(pid);
    await fetchProjectSynergy(pid);
    router.push("/dossier");
  };

  const isBusy = uploadPhase === "PREFLIGHT" || uploadPhase === "UPLOADING" || uploadPhase === "STREAMING";

  if (isBusy) {
    return <ProgressScreen onCancel={resetUploadState} />;
  }

  return (
    <section className="screen">
      <main className="wrap">
        <div className="phead">
          <div>
            <div className="eyebrow">
              <IconShield size={14} />
              Комиссия · X-Ray
            </div>
            <h1 className="h1">X-Ray аудит диплома</h1>
            <p className="sub">
              Загрузите PDF — получите досье: оценки, разрывы между выводами и данными, проверку репозитория и 3
              вопроса для защиты.
            </p>
          </div>
        </div>

        {uploadError && (
          <div
            className="card"
            style={{ marginBottom: 20, borderColor: "rgba(248,113,113,.3)", background: "rgba(248,113,113,.05)" }}
          >
            <span className="c-er xs mono">{uploadError}</span>
          </div>
        )}

        <div className="bento">
          <form
            onSubmit={handleSubmit}
            className="card"
            style={{ gridColumn: "span 8", gridRow: "span 2", display: "flex", flexDirection: "column", gap: 20 }}
          >
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 14,
                minHeight: 300,
                border: "1.5px dashed rgba(var(--acr),.45)",
                borderRadius: 16,
                background: "rgba(var(--acr),.04)",
                textAlign: "center",
                padding: 32,
              }}
            >
              <span className="ico ac" style={{ width: 56, height: 56, borderRadius: 16 }}>
                <IconFile size={24} />
              </span>
              <span className="h2" style={{ overflowWrap: "anywhere" }}>
                {selectedFile ? selectedFile.name : "Загрузите PDF диплома"}
              </span>
              <span className="wrapr" style={{ justifyContent: "center" }}>
                {selectedFile && (
                  <span className="chip">{(selectedFile.size / 1024 / 1024).toFixed(1)} МБ</span>
                )}
                {selectedFile && !fileError && (
                  <span className="chip c-ok">
                    <IconCheck size={13} />
                    PDF проверен
                  </span>
                )}
                {fileError && (
                  <span className="chip c-er">
                    <IconClose size={13} />
                    {fileError}
                  </span>
                )}
              </span>
              <label htmlFor="pdf-input" className="btn btn-g" style={{ marginTop: 4 }}>
                <IconUpload size={16} />
                {selectedFile ? "Выбрать другой файл" : "Выбрать файл"}
              </label>
              <input
                id="pdf-input"
                type="file"
                accept=".pdf,application/pdf"
                hidden
                onChange={(e) => onFileChange(e.target.files?.[0] || null)}
              />
            </div>

            <div className="field">
              <label htmlFor="repo-input">Репозиторий / датасет (опционально)</label>
              <input
                id="repo-input"
                className="inp"
                type="url"
                placeholder="https://github.com/…"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="title-input">Название работы (опционально)</label>
              <input
                id="title-input"
                className="inp"
                type="text"
                placeholder="Например, «Распознавание эмоций в речи…»"
                value={thesisTitle}
                onChange={(e) => setThesisTitle(e.target.value)}
              />
            </div>

            <div className="row" style={{ gap: 8 }}>
              <button type="submit" className="btn btn-p" disabled={!selectedFile || !!fileError}>
                Загрузить и проанализировать
                <IconCheck size={16} />
              </button>
              <button type="button" className="btn btn-g" onClick={handleRunLiveDemo}>
                ⚡ 1-клик демо-аудит
              </button>
            </div>
          </form>

          <section className="card" style={{ gridColumn: "span 4" }}>
            <div className="ch">
              <h2 className="lbl">Что произойдёт</h2>
              <span className="xs fa">≈ 1 мин</span>
            </div>
            <ol className="ol" style={{ gap: 14 }}>
              <li>
                <div>
                  <div className="tx sm" style={{ fontWeight: 500 }}>Парсинг PDF</div>
                  <div className="xs fa">Текст по зонам, главы, поиск дубликатов</div>
                </div>
              </li>
              <li>
                <div>
                  <div className="tx sm" style={{ fontWeight: 500 }}>Верификация артефактов</div>
                  <div className="xs fa">5 проверок репозитория</div>
                </div>
              </li>
              <li>
                <div>
                  <div className="tx sm" style={{ fontWeight: 500 }}>Аудит / извлечение паспорта</div>
                  <div className="xs fa">Структурированный паспорт работы</div>
                </div>
              </li>
              <li>
                <div>
                  <div className="tx sm" style={{ fontWeight: 500 }}>Скоринг и оценка</div>
                  <div className="xs fa">Handover score, разрывы, вопросы</div>
                </div>
              </li>
              <li>
                <div>
                  <div className="tx sm" style={{ fontWeight: 500 }}>Поиск синергий</div>
                  <div className="xs fa">Связь с задачами других работ</div>
                </div>
              </li>
              <li>
                <div>
                  <div className="tx sm" style={{ fontWeight: 500 }}>Готово</div>
                  <div className="xs fa">Досье и вопросы для защиты</div>
                </div>
              </li>
            </ol>
          </section>

          <section className="card" style={{ gridColumn: "span 4" }}>
            <h2 className="lbl" style={{ marginBottom: 12 }}>Проверим до отправки</h2>
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 6 }}>
              {["Расширение .pdf", "Размер до 25 МБ", "Файл начинается с %PDF-", "Файл не пустой"].map((t) => (
                <li key={t} className="row sm mu" style={{ gap: 10, minHeight: 28 }}>
                  <IconCheck size={16} style={{ color: "var(--fa)" }} />
                  {t}
                </li>
              ))}
            </ul>
          </section>

          {catalogProjects.length > 0 && (
            <section className="card" style={{ gridColumn: "span 4" }}>
              <h2 className="lbl" style={{ marginBottom: 12 }}>Открыть ранее проверенную работу</h2>
              <div className="sel">
                <select className="inp" defaultValue="" onChange={(e) => handleSelectCatalogProject(e.target.value)}>
                  <option value="" disabled>
                    Выбрать из {catalogProjects.length} проверенных…
                  </option>
                  {catalogProjects.map((p) => (
                    <option key={p.project_id} value={p.project_id}>
                      [{formatScore100(p.final_handover_score)}] {String(p.title).slice(0, 60)}
                    </option>
                  ))}
                </select>
              </div>
            </section>
          )}
        </div>
      </main>
    </section>
  );
}

function ProgressScreen({ onCancel }: { onCancel: () => void }) {
  const { progressPercent, progressStep, progressTitle, progressHistory, currentJobId } = useHorizonStore();

  const slots = Array.from({ length: TOTAL_STEPS }, (_, i) => i + 1);

  return (
    <section className="screen">
      <main className="wrap">
        <div className="phead">
          <div>
            <div className="eyebrow">
              <IconShield size={14} />
              Комиссия · X-Ray
            </div>
            <h1 className="h1">Анализ в процессе</h1>
            <p className="sub">Можно не ждать на этой странице — досье откроется само, когда анализ закончится.</p>
          </div>
          <button type="button" className="btn btn-g" onClick={onCancel}>
            <IconClose size={16} />
            Отменить
          </button>
        </div>

        <div className="bento">
          <section className="card" style={{ gridColumn: "span 8" }}>
            <div className="between" style={{ alignItems: "flex-end", flexWrap: "wrap" }}>
              <div>
                <div className="lbl">Общий прогресс</div>
                <div className="num" style={{ fontSize: 64, lineHeight: 1.05, marginTop: 6 }}>
                  {progressPercent}
                  <span className="fa" style={{ fontSize: 32 }}>%</span>
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div className="sm mu">Шаг {progressStep} из {TOTAL_STEPS}</div>
                <div className="h3" style={{ marginTop: 2 }}>{stripStepPrefix(progressTitle || "Запуск пайплайна…")}</div>
              </div>
            </div>
            <div className="bar" style={{ height: 10, marginTop: 20 }}>
              <i style={{ width: `${Math.max(2, progressPercent)}%`, background: "var(--ac)" }} />
            </div>

            <hr className="hl" />
            <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
              {slots.map((i) => {
                const ev = progressHistory.find((e) => e.step === i);
                const isActive = !ev && i === progressStep;
                const isDone = !!ev;
                const isPending = !ev && !isActive;
                return (
                  <li
                    key={i}
                    className="between"
                    style={{
                      padding: "12px 14px",
                      borderRadius: 14,
                      border: "1px solid transparent",
                      background: isActive ? "var(--s2)" : undefined,
                      borderColor: isActive ? "rgba(var(--acr),.3)" : undefined,
                    }}
                  >
                    <div className="row" style={{ gap: 14 }}>
                      <span
                        className={isActive ? "ico ac" : "ico"}
                        style={
                          isDone
                            ? { width: 32, height: 32, borderRadius: 10, background: "rgba(74,222,128,.1)", color: "var(--ok)" }
                            : { width: 32, height: 32, borderRadius: 10 }
                        }
                      >
                        {isDone ? (
                          <IconCheck size={16} />
                        ) : isActive ? (
                          <IconSpinner size={16} />
                        ) : (
                          <span className="xs">{i}</span>
                        )}
                      </span>
                      <div>
                        <div className={isPending ? "fa" : "tx"} style={{ fontWeight: isDone ? 400 : 500 }}>
                          {ev ? stripStepPrefix(ev.title) : isActive ? stripStepPrefix(progressTitle) : `Шаг ${i}`}
                        </div>
                      </div>
                    </div>
                    {isActive && (
                      <span className="chip c-ac">
                        <span className="d" />
                        идёт
                      </span>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>

          <div className="stack" style={{ gridColumn: "span 4" }}>
            <section className="card">
              <div className="row" style={{ gap: 12, marginBottom: 16 }}>
                <span className="ico">
                  <IconFile size={18} />
                </span>
                <div style={{ minWidth: 0 }}>
                  <div className="h3" style={{ fontSize: 14 }}>PDF диплома</div>
                  <div className="xs fa">проверка пройдена</div>
                </div>
              </div>
              <dl className="kv">
                <dt>Задача</dt>
                <dd className="mono fa" style={{ fontSize: 12 }}>
                  {currentJobId ? `job ${currentJobId.slice(0, 12)}…` : "—"}
                </dd>
              </dl>
            </section>
            <section className="card">
              <div className="between">
                <h2 className="lbl">Соединение</h2>
                <span className="chip c-ok">
                  <span className="d pulse" />
                  В реальном времени
                </span>
              </div>
              <p className="sm mu" style={{ marginTop: 12 }}>
                Если связь прервётся, переподключимся автоматически. Прогресс не потеряется.
              </p>
            </section>
          </div>
        </div>
      </main>
    </section>
  );
}
