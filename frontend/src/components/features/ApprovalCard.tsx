"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { ErrorState } from "@/components/ui/ErrorState";
import { TextArea } from "@/components/ui/TextArea";
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
  const payload = approval.assessment.payload;
  const fields = Object.keys(payload).filter(
    (key) => !key.startsWith(HIDDEN_FIELD_PREFIX) && !key.endsWith(LABEL_SUFFIX),
  );
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(fields.map((key) => [key, String(payload[key] ?? "")])),
  );
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const edits = Object.fromEntries(
    Object.entries(values).filter(([key, value]) => String(payload[key] ?? "") !== value),
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
    <Callout label="Approval required">
      <p className="font-serif text-lead leading-snug">{approval.reason}</p>
      <p className="mt-2 text-muted">{approval.action.rationale}</p>
      <p className="mt-1 font-mono text-label text-faint">
        {approval.assessment.description} · {approval.assessment.system ?? "unknown system"} ·{" "}
        {approval.assessment.risk}
      </p>

      <div className="mt-6 grid gap-x-8 gap-y-4 sm:grid-cols-2">
        {fields.map((key) => {
          const changed = values[key] !== String(payload[key] ?? "");
          return (
            <label key={key} className="block">
              <span className="font-mono text-label uppercase tracking-[0.14em] text-muted">
                {key.replaceAll("_", " ")}
                {changed && <span className="ml-2 text-accent">edited</span>}
              </span>
              <input
                className="mt-1 w-full border-0 border-b border-rule bg-transparent py-1 font-mono text-ink focus:border-ink focus:outline-none"
                value={values[key] ?? ""}
                onChange={(event) => setValues({ ...values, [key]: event.target.value })}
              />
            </label>
          );
        })}
      </div>

      <TextArea
        aria-label="Comment"
        rows={2}
        className="mt-6"
        placeholder="Comment for the operator (explain a rejection)"
        value={comment}
        onChange={(event) => setComment(event.target.value)}
      />
      {error && (
        <div className="mt-3">
          <ErrorState message={error} />
        </div>
      )}
      <div className="mt-4 flex items-center gap-6">
        <Button
          disabled={busy}
          onClick={() => void resolve(edited ? "approve_with_edits" : "approve")}
        >
          {edited ? "Approve with edits" : "Approve"}
        </Button>
        <Button variant="danger" disabled={busy} onClick={() => void resolve("reject")}>
          Reject
        </Button>
      </div>
    </Callout>
  );
}
