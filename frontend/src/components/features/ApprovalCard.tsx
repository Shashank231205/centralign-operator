"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import type { ApprovalDecision, PendingApproval } from "@/types/api";

// Bookkeeping fields the policy engine adds; not editable business data.
const HIDDEN_FIELD_PREFIX = "_";
const LABEL_SUFFIX = "_label";

interface ApprovalCardProps {
  approval: PendingApproval;
  onResolve: (
    decision: ApprovalDecision,
    comment: string,
    edits: Record<string, string> | null,
  ) => Promise<void>;
}

export function ApprovalCard({ approval, onResolve }: ApprovalCardProps) {
  const fields = Object.entries(approval.assessment.payload).filter(
    ([key]) => !key.startsWith(HIDDEN_FIELD_PREFIX) && !key.endsWith(LABEL_SUFFIX),
  );
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(fields.map(([key, value]) => [key, String(value)])),
  );
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const edits = Object.fromEntries(
    Object.entries(values).filter(
      ([key, value]) => String(approval.assessment.payload[key]) !== value,
    ),
  );
  const edited = Object.keys(edits).length > 0;

  async function resolve(decision: ApprovalDecision) {
    setBusy(true);
    setError(null);
    try {
      await onResolve(decision, comment, decision === "approve_with_edits" ? edits : null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not record the decision");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Approval required" tone="attention">
      <p className="text-sm text-slate-800">{approval.reason}</p>
      <p className="mt-1 text-xs text-slate-600">
        {approval.assessment.description} · system: {approval.assessment.system ?? "unknown"} ·
        risk: {approval.assessment.risk}
      </p>
      <p className="mt-1 text-xs text-slate-600">Why: {approval.action.rationale}</p>
      <h3 className="mt-3 text-xs font-semibold text-slate-700">Data to be written</h3>
      <div className="mt-1 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {fields.map(([key]) => (
          <label key={key} className="text-xs text-slate-600">
            {key}
            <input
              className="mt-0.5 w-full rounded border border-slate-300 bg-white p-1 font-mono text-sm text-slate-900"
              value={values[key] ?? ""}
              onChange={(event) => setValues({ ...values, [key]: event.target.value })}
            />
          </label>
        ))}
      </div>
      <textarea
        aria-label="Comment"
        className="mt-3 h-16 w-full rounded border border-slate-300 p-2 text-sm"
        placeholder="Comment (required context for a rejection)"
        value={comment}
        onChange={(event) => setComment(event.target.value)}
      />
      {error && <ErrorState message={error} />}
      <div className="mt-2 flex flex-wrap justify-end gap-2">
        <Button variant="danger" disabled={busy} onClick={() => void resolve("reject")}>
          Reject
        </Button>
        {edited ? (
          <Button disabled={busy} onClick={() => void resolve("approve_with_edits")}>
            Approve with edits
          </Button>
        ) : (
          <Button disabled={busy} onClick={() => void resolve("approve")}>
            Approve
          </Button>
        )}
      </div>
    </Card>
  );
}
