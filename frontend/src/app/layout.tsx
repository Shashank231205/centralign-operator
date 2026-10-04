import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Operator Console",
  description: "Give the AI operator a company request and watch it complete and verify the work.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen text-slate-900 antialiased">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <Link href="/" className="font-semibold">
              Operator Console
            </Link>
            <span className="text-xs text-slate-500">Autonomous company operator</span>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
