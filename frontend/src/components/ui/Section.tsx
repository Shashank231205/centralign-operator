import type { ReactNode } from "react";

interface SectionProps {
  label: string;
  aside?: ReactNode;
  children: ReactNode;
}

// A titled region separated by a hairline rule — structure from whitespace, not boxes.
export function Section({ label, aside, children }: SectionProps) {
  return (
    <section className="border-t border-rule pt-4">
      <header className="mb-4 flex items-baseline justify-between gap-4">
        <h2 className="font-mono text-label uppercase tracking-[0.14em] text-muted">{label}</h2>
        {aside}
      </header>
      {children}
    </section>
  );
}
