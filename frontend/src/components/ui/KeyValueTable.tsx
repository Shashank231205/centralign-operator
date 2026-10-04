import { EmptyState } from "@/components/ui/EmptyState";

interface KeyValueTableProps {
  values: Record<string, string>;
  emptyMessage: string;
}

export function KeyValueTable({ values, emptyMessage }: KeyValueTableProps) {
  const entries = Object.entries(values);
  if (entries.length === 0) return <EmptyState message={emptyMessage} />;
  return (
    <dl className="grid grid-cols-[minmax(8rem,1fr)_2fr] gap-x-6">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="border-b border-rule py-2 text-muted">{key.replaceAll("_", " ")}</dt>
          <dd className="border-b border-rule py-2 font-mono text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
