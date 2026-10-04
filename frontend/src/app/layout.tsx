import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Operator",
  description: "Give the operator a company request; it does the work and verifies it.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <div className="mx-auto max-w-7xl px-6 lg:px-10">
          <header className="flex items-baseline justify-between border-b border-ink py-5">
            <Link href="/" className="font-serif text-lead italic">
              Operator
            </Link>
            <nav className="font-mono text-label uppercase tracking-[0.14em] text-muted">
              Autonomous company operator
            </nav>
          </header>
          <main className="py-12">{children}</main>
        </div>
      </body>
    </html>
  );
}
