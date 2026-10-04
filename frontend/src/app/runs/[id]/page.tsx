"use client";

import { useParams } from "next/navigation";

import { ApprovalCard } from "@/components/features/ApprovalCard";
import { EventTimeline } from "@/components/features/EventTimeline";
import { EvidenceGallery } from "@/components/features/EvidenceGallery";
import { PlanSteps } from "@/components/features/PlanSteps";
import { QuestionCard } from "@/components/features/QuestionCard";
import { RunHeader } from "@/components/features/RunHeader";
import { VerificationReport } from "@/components/features/VerificationReport";
import { ErrorState } from "@/components/ui/ErrorState";
import { Loading } from "@/components/ui/Loading";
import { useRun } from "@/hooks/useRun";
import { api } from "@/lib/api";
import type { ApprovalDecision } from "@/types/api";

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const { run, events, evidence, error, loading, connected, refresh } = useRun(id);

  if (loading) return <Loading label="Loading run" />;
  if (!run) return <ErrorState message={error ?? "Run not found"} onRetry={() => void refresh()} />;

  async function resolve(
    decision: ApprovalDecision,
    comment: string,
    edits: Record<string, string> | null,
  ) {
    if (!run?.pending_approval) return;
    await api.resolveApproval(run.pending_approval.approval_id, decision, comment, edits);
    await refresh();
  }

  async function answer(text: string) {
    await api.answer(id, text);
    await refresh();
  }

  async function cancel() {
    await api.cancel(id);
    await refresh();
  }

  return (
    <div className="space-y-14">
      <RunHeader run={run} onCancel={cancel} />
      {error && <ErrorState message={error} onRetry={() => void refresh()} />}
      {run.status === "awaiting_approval" && run.pending_approval && (
        <div className="lg:w-8/12">
          <ApprovalCard approval={run.pending_approval} onResolve={resolve} />
        </div>
      )}
      {run.status === "awaiting_input" && run.pending_question && (
        <div className="lg:w-8/12">
          <QuestionCard question={run.pending_question} onAnswer={answer} />
        </div>
      )}
      <div className="grid gap-x-16 gap-y-14 lg:grid-cols-12">
        <div className="space-y-14 lg:col-span-7">
          <VerificationReport run={run} />
          <PlanSteps plan={run.plan} />
        </div>
        <div className="space-y-14 lg:col-span-5">
          <EvidenceGallery items={evidence} />
          <EventTimeline events={events} connected={connected} />
        </div>
      </div>
    </div>
  );
}
