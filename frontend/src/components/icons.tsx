"use client";

import React from "react";

type IP = React.SVGProps<SVGSVGElement> & { size?: number };

function base(size = 16) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.75,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
}

export function IconUser({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c0-4 4-6 8-6s8 2 8 6" />
    </svg>
  );
}

export function IconSupervisor({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20c0-3.5 3-5.5 6.5-5.5s6.5 2 6.5 5.5" />
      <path d="M16 4h6M16 8h6M18 12h4" />
    </svg>
  );
}

export function IconCalendar({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <rect x="4" y="5" width="16" height="15" rx="2" />
      <path d="M4 10h16M9 3v4M15 3v4" />
    </svg>
  );
}

export function IconBuilding({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M4 21V8l8-5 8 5v13" />
      <path d="M9 21v-6h6v6" />
      <path d="M3 21h18" />
    </svg>
  );
}

export function IconWaveform({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M3 12h2M7 8v8M11 5v14M15 9v6M19 11v2" />
    </svg>
  );
}

export function IconCheck({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="m5 12.5 4.5 4.5L19 7.5" />
    </svg>
  );
}

export function IconArrowRight({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </svg>
  );
}

export function IconArrowLeft({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M19 12H5" />
      <path d="m11 6-6 6 6 6" />
    </svg>
  );
}

export function IconClose({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}

export function IconSpinner({ size, className, ...p }: IP) {
  return (
    <svg {...base(size)} className={`spin ${className || ""}`} {...p}>
      <path d="M12 3a9 9 0 1 0 9 9" />
    </svg>
  );
}

export function IconChevronDown({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

export function IconUpload({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M12 15V3" />
      <path d="m7 8 5-5 5 5" />
      <path d="M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6" />
    </svg>
  );
}

export function IconDownload({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M12 4v11" />
      <path d="m7 10 5 5 5-5" />
      <path d="M5 20h14" />
    </svg>
  );
}

export function IconRefresh({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M20 12a8 8 0 1 1-2.34-5.66" />
      <path d="M20 4v5h-5" />
    </svg>
  );
}

export function IconFile({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </svg>
  );
}

export function IconAlert({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M12 4 3 20h18z" />
      <path d="M12 10v4" />
      <path d="M12 17.5v.01" />
    </svg>
  );
}

export function IconShield({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M4 8V5a1 1 0 0 1 1-1h3" />
      <path d="M16 4h3a1 1 0 0 1 1 1v3" />
      <path d="M20 16v3a1 1 0 0 1-1 1h-3" />
      <path d="M8 20H5a1 1 0 0 1-1-1v-3" />
      <path d="M4 12h16" />
    </svg>
  );
}

export function IconRelay({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="m2 9 10-5 10 5-10 5z" />
      <path d="M6 11v5c0 1.5 3 3 6 3s6-1.5 6-3v-5" />
      <path d="M22 9v6" />
    </svg>
  );
}

export function IconAnalytics({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M5 20V11" />
      <path d="M11 20V5" />
      <path d="M17 20v-7" />
      <path d="M3 20h18" />
    </svg>
  );
}

export function IconBaton({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M4 20 15 9" />
      <path d="m13 5 6 6" />
      <path d="m15 3 6 6" />
      <circle cx="5.5" cy="18.5" r="1.5" />
    </svg>
  );
}

export function IconLock({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

export function IconCopy({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <rect x="8" y="8" width="12" height="12" rx="2" />
      <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
    </svg>
  );
}

export function IconTarget({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M12 21s-6-5.6-6-11a6 6 0 0 1 12 0c0 5.4-6 11-6 11z" />
      <circle cx="12" cy="10" r="2.2" />
    </svg>
  );
}

export function IconFunction({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M5 6h7l-4 6 4 6H5" />
      <path d="M15 9l5 6M20 9l-5 6" />
    </svg>
  );
}

export function IconFlag({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M3 17 17 3l4 4L7 21z" />
      <path d="m7 13 2 2M10 10l2 2M13 7l2 2" />
    </svg>
  );
}

export function IconBox({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z" />
      <path d="m4 7.5 8 4.5 8-4.5" />
      <path d="M12 12v9" />
    </svg>
  );
}

export function IconSearch({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m20 20-4.2-4.2" />
    </svg>
  );
}

export function IconPlus({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function IconLogo({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M3 15a9 9 0 0 1 18 0" />
      <path d="M7 15a5 5 0 0 1 10 0" />
      <circle cx="12" cy="15" r="1.6" fill="currentColor" stroke="none" />
      <path d="M3 19h18" />
    </svg>
  );
}

export function IconInfo({ size, ...p }: IP) {
  return (
    <svg {...base(size)} {...p}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <path d="M12 7.5v.01" />
    </svg>
  );
}
