export const DOMAIN_PROFILE_META: Record<string, { label: string; color: string }> = {
  IT_AND_DATA_SCIENCE: { label: "ИТ и Data Science", color: "#60A5FA" },
  ENGINEERING_AND_HARDWARE: { label: "Инженерия и оборудование", color: "#FB923C" },
  NATURAL_AND_BIOMEDICAL: { label: "Биомедицина и естественные науки", color: "#4ADE80" },
  ECONOMICS_AND_MANAGEMENT: { label: "Экономика и менеджмент", color: "#FACC15" },
  HUMANITIES_SOCIAL_AND_LAW: { label: "Гуманитарные, социальные и право", color: "#F472B6" },
};

export function domainProfileLabel(v?: string | null): string {
  if (!v) return "—";
  return DOMAIN_PROFILE_META[v]?.label || v;
}

export function domainProfileColor(v?: string | null): string {
  return (v && DOMAIN_PROFILE_META[v]?.color) || "#878E96";
}

export const MODALITY_LABELS: Record<string, string> = {
  image: "Изображения",
  audio: "Аудио",
  text: "Текст / NLP",
  tabular: "Табличные данные",
  signal: "Сигналы",
  hardware: "Оборудование",
  empirical_survey: "Эмпирическое исследование",
  legal_normative: "Правовые / нормативные",
  multimodal: "Мультимодальные",
};

export function modalityLabel(v?: string | null): string {
  if (!v) return "—";
  return MODALITY_LABELS[v] || v;
}

export const ARCHETYPE_META: Record<string, { label: string; chipClass: string }> = {
  RELAY_CANDIDATE: { label: "Кандидат на эстафету", chipClass: "c-ok" },
  GOLD_STANDARD_COMPLETED: { label: "Золотой стандарт · завершено", chipClass: "c-gold" },
  DEAD_END_ARCHIVE: { label: "Архив (тупиковая ветка)", chipClass: "" },
};

export function archetypeLabel(v?: string | null): string {
  if (!v) return "—";
  return ARCHETYPE_META[v]?.label || v;
}

export function archetypeChipClass(v?: string | null): string {
  return (v && ARCHETYPE_META[v]?.chipClass) ?? "";
}

export const CLAIM_STATUS_META: Record<string, { label: string; chipClass: string }> = {
  OPEN: { label: "Открыто", chipClass: "c-ok" },
  RESERVED_PENDING: { label: "Зарезервировано", chipClass: "c-wa" },
  ASSIGNED: { label: "Назначено", chipClass: "c-in" },
  COMPLETED: { label: "Завершено", chipClass: "" },
};

export function claimStatusLabel(v?: string | null): string {
  if (!v) return "—";
  return CLAIM_STATUS_META[v]?.label || v;
}

export function claimStatusChipClass(v?: string | null): string {
  return (v && CLAIM_STATUS_META[v]?.chipClass) ?? "";
}

export const MACRO_CATEGORY_COLORS: Record<string, string> = {
  "Compute & Hardware": "#60A5FA",
  "Data Scarcity & Annotation": "#FB923C",
  "Algorithmic Limitations": "#A78BFA",
  "System Integration & Prod": "#FACC15",
  "Legal, Privacy & Access": "#F472B6",
  "Domain Validation": "#4ADE80",
  "Scope Overrun & Unfinished Dev": "#F87171",
};

export function macroCategoryColor(v?: string | null): string {
  return (v && MACRO_CATEGORY_COLORS[v]) || "#878E96";
}

export const GAP_SEVERITY_META: Record<string, { label: string; chipClass: string }> = {
  NONE: { label: "Нет", chipClass: "c-ok" },
  LOW: { label: "Низкая", chipClass: "c-ok" },
  MEDIUM: { label: "Средняя", chipClass: "c-or" },
  HIGH: { label: "Высокая", chipClass: "c-er" },
};

export function gapSeverityLabel(v?: string | null): string {
  if (!v) return "Низкая";
  return GAP_SEVERITY_META[v]?.label || v;
}

export function gapSeverityChipClass(v?: string | null): string {
  return (v && GAP_SEVERITY_META[v]?.chipClass) || "c-ok";
}

export const PROBE_STATUS_LABELS: Record<string, string> = {
  VERIFIED: "Проверено",
  UNVERIFIED: "Не проверено",
  DEFERRED_RETRY: "Повторная попытка",
  PENDING_DOMAIN: "Ожидает модерации домена",
  NO_REPO_METHODOLOGY_ONLY: "Без репозитория (только методология)",
};

export function probeStatusLabel(v?: string | null): string {
  if (!v) return "—";
  return PROBE_STATUS_LABELS[v] || v;
}

export function scoreBarColor(fraction: number): string {
  if (fraction >= 0.75) return "var(--ok)";
  if (fraction >= 0.5) return "var(--wa)";
  return "var(--er)";
}

export function formatScore100(v?: number | null): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  return String(Math.round(v));
}
