import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Loading } from "@/components/ui/Loading";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { RunListItem } from "@/types/api";

interface RunListProps {
  runs: RunListItem[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

export function RunList({ runs, loading, error, onRetry }: RunListProps) {
  return (
    <Card title="Recent runs">
      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={onRetry} />}
      {!loading && !error && runs.length === 0 && <EmptyState message="No runs yet." />}
      <ul className="divide-y divide-slate-100">
        {runs.map((run) => (
          <li key={run.id} className="py-2">
            <Link href={`/runs/${run.id}`} className="flex items-start justify-between gap-3">
              <span className="text-sm text-slate-800">{run.request}</span>
              <StatusBadge status={run.status} />
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
