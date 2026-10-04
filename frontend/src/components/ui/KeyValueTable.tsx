import { EmptyState } from "@/components/ui/EmptyState";

interface KeyValueTableProps {
  values: Record<string, unknown>;
  emptyMessage: string;
}

export function KeyValueTable({ values, emptyMessage }: KeyValueTableProps) {
  const entries = Object.entries(values);
  if (entries.length === 0) return <EmptyState message={emptyMessage} />;
  return (
    <table className="w-full text-sm">
      <tbody>
        {entries.map(([key, value]) => (
          <tr key={key} className="border-b border-slate-100 last:border-0">
            <th className="w-1/3 py-1 pr-3 text-left font-medium text-slate-600">{key}</th>
            <td className="py-1 font-mono text-slate-900">{String(value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
