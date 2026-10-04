export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <p role="status" className="animate-pulse text-sm text-slate-500">
      {label}
    </p>
  );
}
