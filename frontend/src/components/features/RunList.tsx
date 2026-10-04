import Link from "next/link";

import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Loading } from "@/components/ui/Loading";
import { Section } from "@/components/ui/Section";
import { StatusText } from "@/components/ui/StatusText";
import type { RunListItem } from "@/types/api";

interface RunListProps {
  runs: RunListItem[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

export function RunList({ runs, loading, error, onRetry }: RunListProps) {
  return (
    <Section label="Recent runs">
      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={onRetry} />}
      {!loading && !error && runs.length === 0 && <EmptyState message="Nothing run yet." />}
      <ul>
        {runs.map((run) => (
          <li key={run.id} className="border-b border-rule last:border-0">
            <Link
              href={`/runs/${run.id}`}
              className="block py-3 transition-colors duration-100 hover:text-accent"
            >
              <span className="line-clamp-2">{run.request}</span>
              <span className="mt-1 flex items-baseline justify-between gap-3">
                <StatusText status={run.status} />
                <time className="font-mono text-label text-faint" dateTime={run.created_at}>
                  {new Date(run.created_at).toLocaleString()}
                </time>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Section>
  );
}
