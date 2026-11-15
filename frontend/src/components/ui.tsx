"use client";

import React, { useEffect } from "react";
import {
  IconAlert,
  IconBuilding,
  IconCalendar,
  IconClose,
  IconSupervisor,
  IconUser,
  IconWaveform,
} from "./icons";
import {
  domainProfileColor,
  domainProfileLabel,
  modalityLabel,
  scoreBarColor,
} from "@/lib/format";

export function ScoreRing({
  score100,
  size = 176,
  stroke = 12,
  label,
}: {
  score100: number;
  size?: number;
  stroke?: number;
  label?: string;
}) {
  const r = size / 2 - stroke / 2 - 2;
  const c = 2 * Math.PI * r;
  const frac = Math.max(0, Math.min(1, (score100 || 0) / 100));
  const color = scoreBarColor(frac);
  return (
    <div style={{ position: "relative", width: size, height: size, flex: "none" }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1F2328" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${frac * c} ${c}`}
        />
      </svg>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div className="num" style={{ fontSize: size * 0.26, lineHeight: 1 }}>
          {Math.round(score100 || 0)}
        </div>
        {label !== undefined && <div className="fa xs" style={{ marginTop: 4 }}>{label}</div>}
      </div>
    </div>
  );
}

export interface SegNavItem {
  key: string;
  label: string;
  badge?: string | number;
}

export function SegNav({
  items,
  active,
  onChange,
  ariaLabel,
}: {
  items: SegNavItem[];
  active: string;
  onChange: (key: string) => void;
  ariaLabel: string;
}) {
  return (
    <nav className="seg" aria-label={ariaLabel}>
      {items.map((it) => (
        <button
          key={it.key}
          type="button"
          className={active === it.key ? "on" : ""}
          aria-current={active === it.key ? "page" : undefined}
          onClick={() => onChange(it.key)}
        >
          {it.label}
          {it.badge !== undefined && <span className="n">{it.badge}</span>}
        </button>
      ))}
    </nav>
  );
}

export function MetaChipsRow({
  author,
  supervisor,
  year,
  department,
  domainProfile,
  modality,
  language,
  archetypeChip,
}: {
  author?: string;
  supervisor?: string;
  year?: number;
  department?: string;
  domainProfile?: string;
  modality?: string;
  language?: string;
  archetypeChip?: React.ReactNode;
}) {
  return (
    <div className="wrapr" style={{ marginTop: 14 }}>
      {author && (
        <span className="chip">
          <IconUser size={13} />
          {author}
        </span>
      )}
      {supervisor && (
        <span className="chip">
          <IconSupervisor size={13} />
          Рук. {supervisor}
        </span>
      )}
      {year && (
        <span className="chip">
          <IconCalendar size={13} />
          {year}
        </span>
      )}
      {department && (
        <span className="chip">
          <IconBuilding size={13} />
          {department}
        </span>
      )}
      {domainProfile && (
        <span className="chip">
          <span className="d" style={{ background: domainProfileColor(domainProfile) }} />
          {domainProfileLabel(domainProfile)}
        </span>
      )}
      {modality && (
        <span className="chip">
          <IconWaveform size={13} />
          {modalityLabel(modality)}
        </span>
      )}
      {language && <span className="chip">{language}</span>}
      {archetypeChip}
    </div>
  );
}

export function Modal({
  title,
  subtitle,
  icon,
  onClose,
  children,
  maxWidth = 560,
}: {
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
  maxWidth?: number;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 50 }}>
      <div
        onClick={onClose}
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(5,6,8,.74)",
          backdropFilter: "blur(3px)",
        }}
      />
      <div
        role="dialog"
        aria-modal="true"
        style={{
          position: "absolute",
          left: "50%",
          top: 80,
          transform: "translateX(-50%)",
          width: `min(${maxWidth}px, calc(100% - 32px))`,
          maxHeight: "calc(100vh - 120px)",
          overflowY: "auto",
          background: "var(--s1)",
          border: "1px solid var(--ln2)",
          borderRadius: 24,
          boxShadow: "0 30px 80px rgba(0,0,0,.6)",
        }}
      >
        <div style={{ padding: 28, display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="between" style={{ alignItems: "flex-start" }}>
            <div className="row" style={{ gap: 12 }}>
              {icon && <span className="ico ac">{icon}</span>}
              <div>
                <h2 className="h2">{title}</h2>
                {subtitle && <p className="xs fa">{subtitle}</p>}
              </div>
            </div>
            <button type="button" className="btn btn-g ib" aria-label="Закрыть" onClick={onClose}>
              <IconClose size={18} />
            </button>
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}

export function AlertBanner({ children, tone = "er" }: { children: React.ReactNode; tone?: "er" | "wa" }) {
  const color = tone === "er" ? "248,113,113" : "251,191,36";
  return (
    <div
      className="card"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        flexWrap: "wrap",
        borderColor: `rgba(${color},.3)`,
        background: `rgba(${color},.05)`,
      }}
    >
      <span className="ico" style={{ background: `rgba(${color},.12)`, color: `var(--${tone})` }}>
        <IconAlert size={18} />
      </span>
      <div style={{ flex: "1 1 360px" }}>{children}</div>
    </div>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="xs mu" style={{ padding: 16, borderRadius: 12, background: "var(--s2)" }}>
      {children}
    </div>
  );
}
