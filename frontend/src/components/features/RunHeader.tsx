"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { StatusText } from "@/components/ui/StatusText";
import type { RunDetail } from "@/types/api";

const FINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

interface RunHeaderProps {
  run: RunDetail;
  onCancel: () => Promise<void>;
}

export function RunHeader({ run, onCancel }: RunHeaderProps) {
  const [cancelling, setCancelling] = useState(false);
  const counters = run.counters;
  const metrics: [string, number][] = [
    ["steps", counters.steps],
    ["retries", counters.retries],
    ["re-plans", counters.replans],
    ["model calls", counters.llm_calls],
    ["tokens", counters.prompt_tokens + counters.completion_tokens],
  ];

  async function cancel() {
    setCancelling(true);
    try {
      await onCancel();
    } finally {
      setCancelling(false);
    }
  }

  return (
    <header className="grid gap-6 lg:grid-cols-12">
      <div className="lg:col-span-8">
        <StatusText status={run.status} />
        <h1 className="mt-3 font-serif text-title leading-tight">{run.request}</h1>
        {run.goal && (
          <p className="mt-3 text-lead text-muted">
            <span className="italic">Outcome — </span>
            {run.goal.intended_outcome}
          </p>
        )}
      </div>
      <dl className="grid grid-cols-2 content-start gap-x-6 gap-y-3 lg:col-span-4 lg:border-l lg:border-rule lg:pl-6">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <dt className="font-mono text-label uppercase tracking-[0.14em] text-faint">{label}</dt>
            <dd className="font-mono text-lead tabular-nums">{value.toLocaleString()}</dd>
          </div>
        ))}
        {!FINAL_STATUSES.has(run.status) && (
          <div className="col-span-2">
            <Button variant="danger" disabled={cancelling} onClick={() => void cancel()}>
              Cancel run
            </Button>
          </div>
        )}
      </dl>
    </header>
  );
}
