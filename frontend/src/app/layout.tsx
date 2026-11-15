"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { IconAnalytics, IconLogo, IconRelay, IconShield } from "@/components/icons";
import "./globals.css";

const ROLES: { href: string; r: "C" | "S" | "D"; color: string; label: string; fa: string; icon: React.ReactNode }[] = [
  { href: "/", r: "C", color: "#7AA2FF", label: "Комиссия", fa: "X-Ray", icon: <IconShield size={16} /> },
  { href: "/relay", r: "S", color: "#3DD6C3", label: "Студент", fa: "Relay", icon: <IconRelay size={16} /> },
  { href: "/dean", r: "D", color: "#B49CFF", label: "Деканат", fa: "Analytics", icon: <IconAnalytics size={16} /> },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const active =
    ROLES.find((r) => (r.href === "/" ? pathname === "/" || pathname.startsWith("/dossier") : pathname.startsWith(r.href))) ||
    ROLES[0];

  return (
    <html lang="ru">
      <body>
        <div className="hr" style={{ "--ac": active.color, "--acr": hexToRgbList(active.color) } as React.CSSProperties}>
          <header className="top">
            <Link className="logo" href="/">
              <span className="logo-m">
                <IconLogo size={20} />
              </span>
              Horizon Relay
            </Link>
            <nav className="roles" aria-label="Роль">
              {ROLES.map((r) => (
                <Link
                  key={r.href}
                  href={r.href}
                  className={`role ${active.href === r.href ? "on" : ""}`}
                  aria-current={active.href === r.href ? "page" : undefined}
                >
                  <span style={{ color: r.color }}>{r.icon}</span>
                  {r.label}
                  <span className="fa">{r.fa}</span>
                </Link>
              ))}
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}

function hexToRgbList(hex: string): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `${r}, ${g}, ${b}`;
}
