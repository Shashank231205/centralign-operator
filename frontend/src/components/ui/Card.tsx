import type { ReactNode } from "react";

interface CardProps {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  tone?: "default" | "attention";
}

export function Card({ title, actions, children, tone = "default" }: CardProps) {
  const border =
    tone === "attention" ? "border-amber-400 bg-amber-50" : "border-slate-200 bg-white";
  return (
    <section className={`rounded-lg border ${border} p-4 shadow-sm`}>
      {(title || actions) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold text-slate-800">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}
