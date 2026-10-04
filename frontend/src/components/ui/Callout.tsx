import type { ReactNode } from "react";

interface CalloutProps {
  label: string;
  children: ReactNode;
}

// Draws attention with a single accent rule on the left instead of a coloured box.
export function Callout({ label, children }: CalloutProps) {
  return (
    <section className="border-l-2 border-accent py-1 pl-6">
      <h2 className="font-mono text-label uppercase tracking-[0.14em] text-accent">{label}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}
