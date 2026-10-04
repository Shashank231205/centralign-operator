import { EmptyState } from "@/components/ui/EmptyState";
import { KeyValueTable } from "@/components/ui/KeyValueTable";
import { Section } from "@/components/ui/Section";
import type { RunDetail } from "@/types/api";

export function VerificationReport({ run }: { run: RunDetail }) {
  return (
    <Section label="Outcome">
      {run.summary && (
        <p className="max-w-prose font-serif text-lead leading-snug">{run.summary}</p>
      )}
      {run.failure_reason && <p className="mt-2 text-negative">{run.failure_reason}</p>}

      <h3 className="mt-8 font-mono text-label uppercase tracking-[0.14em] text-muted">
        Independent verification
      </h3>
      {run.verification.length === 0 ? (
        <div className="mt-2">
          <EmptyState message="Checked against the system of record once the work is done." />
        </div>
      ) : (
        <ul className="mt-2">
          {run.verification.map((result) => (
            <li
              key={result.criterion_id}
              className="grid grid-cols-[3.5rem_1fr] gap-3 border-b border-rule py-2 last:border-0"
            >
              <span
                className={`font-mono text-label uppercase leading-6 ${result.passed ? "text-positive" : "text-negative"}`}
              >
                {result.passed ? "Pass" : "Fail"}
              </span>
              <div>
                <p>{result.description}</p>
                <p className="font-mono text-label text-faint">{result.detail}</p>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-8 grid gap-8 xl:grid-cols-2">
        <div>
          <h3 className="mb-2 font-mono text-label uppercase tracking-[0.14em] text-muted">
            Key results
          </h3>
          <KeyValueTable values={run.key_results} emptyMessage="None yet." />
        </div>
        <div>
          <h3 className="mb-2 font-mono text-label uppercase tracking-[0.14em] text-muted">
            Facts discovered
          </h3>
          <KeyValueTable values={run.facts} emptyMessage="None yet." />
        </div>
      </div>
    </Section>
  );
}
