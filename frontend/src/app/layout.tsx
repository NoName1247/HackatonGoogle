"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useHorizonStore, UserRole } from "@/lib/store";
import "./globals.css";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { activeRole, setActiveRole } = useHorizonStore();

  const navLinks = [
    { href: "/", label: "Mode 1: Pre-Defense X-Ray & Prior Art Radar" },
    { href: "/relay", label: "Mode 2: Relay Marketplace & Synergy Stitcher" },
    { href: "/dean", label: "Mode 3: Dean's R&D Resource Control" },
  ];

  const roles: { id: UserRole; label: string }[] = [
    { id: "COMMISSION", label: "🏛️ Examination Board (ГАК)" },
    { id: "STUDENT", label: "🧑🎓 Graduate / R&D Fellow" },
    { id: "DEAN", label: "📊 Dean's Office" },
  ];

  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
        <header className="border-b border-slate-800 bg-slate-900/90 sticky top-0 z-40 backdrop-blur">
          <div className="max-w-7xl mx-auto px-4 py-3 flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-lg bg-emerald-500/20 border border-emerald-500/50 flex items-center justify-center font-mono font-bold text-emerald-400">
                HR
              </div>
              <div>
                <div className="font-bold tracking-tight text-white flex items-center gap-2">
                  <span>HORIZON RELAY</span>
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-emerald-400 border border-slate-700">
                    v2.0 Zero-Trust Audit
                  </span>
                </div>
                <p className="text-xs text-slate-400">
                  University Technical Audit, Data Rescue & Asymmetric R&D Synergy Engine
                </p>
              </div>
            </div>

            <nav className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
              {navLinks.map((item) => {
                const isActive = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                      isActive
                        ? "bg-emerald-600 text-white shadow"
                        : "text-slate-300 hover:text-white hover:bg-slate-800"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>

            <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
              {roles.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => setActiveRole(r.id)}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition ${
                    activeRole === r.id
                      ? "bg-indigo-600 text-white"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>
        </header>

        <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6">{children}</main>
      </body>
    </html>
  );
}

