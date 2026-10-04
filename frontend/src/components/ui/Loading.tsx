export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <output className="block font-mono text-label uppercase tracking-[0.14em] text-muted">
      {label}
    </output>
  );
}
