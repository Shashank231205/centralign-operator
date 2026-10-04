import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { KeyValueTable } from "@/components/ui/KeyValueTable";
import type { RunDetail } from "@/types/api";

export function VerificationReport({ run }: { run: RunDetail }) {
  return (
    <Card title="Outcome">
      {run.summary && <p className="mb-3 text-sm text-slate-800">{run.summary}</p>}
      {run.failure_reason && (
        <p className="mb-3 text-sm text-red-700">Failed: {run.failure_reason}</p>
      )}
      <h3 className="text-xs font-semibold text-slate-600">Independent verification</h3>
      {run.verification.length === 0 ? (
        <EmptyState message="Not verified yet." />
      ) : (
        <ul className="mb-3 space-y-1">
          {run.verification.map((result) => (
            <li key={result.criterion_id} className="text-sm">
              <span className={result.passed ? "text-green-700" : "text-red-700"}>
                {result.passed ? "✓ PASS" : "✕ FAIL"}
              </span>{" "}
              {result.description}
              <div className="pl-12 text-xs text-slate-500">{result.detail}</div>
            </li>
          ))}
        </ul>
      )}
      <h3 className="mt-2 text-xs font-semibold text-slate-600">Key results</h3>
      <KeyValueTable values={run.key_results} emptyMessage="No results yet." />
      <h3 className="mt-3 text-xs font-semibold text-slate-600">Facts discovered</h3>
      <KeyValueTable values={run.facts} emptyMessage="No facts recorded yet." />
    </Card>
  );
}
