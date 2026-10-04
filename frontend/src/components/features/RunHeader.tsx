"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { RunDetail } from "@/types/api";

const FINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

interface RunHeaderProps {
  run: RunDetail;
  onCancel: () => Promise<void>;
}

export function RunHeader({ run, onCancel }: RunHeaderProps) {
  const [cancelling, setCancelling] = useState(false);
  const counters = run.counters;
  const tokens = counters.prompt_tokens + counters.completion_tokens;

  async function cancel() {
    setCancelling(true);
    try {
      await onCancel();
    } finally {
      setCancelling(false);
    }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm text-slate-900">{run.request}</p>
          {run.goal && (
            <p className="mt-1 text-xs text-slate-500">Goal: {run.goal.intended_outcome}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={run.status} />
          {!FINAL_STATUSES.has(run.status) && (
            <Button variant="secondary" disabled={cancelling} onClick={() => void cancel()}>
              Cancel
            </Button>
          )}
        </div>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        {counters.steps} steps · {counters.retries} retries · {counters.replans} re-plans ·{" "}
        {counters.llm_calls} LLM calls · {tokens.toLocaleString()} tokens
      </p>
    </Card>
  );
}
