import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { Plan, StepStatus } from "@/types/api";

const MARKERS: Record<StepStatus, string> = {
  pending: "○",
  in_progress: "◐",
  done: "●",
  skipped: "–",
  failed: "✕",
};

export function PlanSteps({ plan }: { plan: Plan | null }) {
  return (
    <Card title={plan ? `Plan (v${plan.version})` : "Plan"}>
      {!plan && <EmptyState message="The plan appears once the request is understood." />}
      {plan && (
        <>
          <p className="mb-2 text-xs text-slate-500">{plan.rationale}</p>
          <ol className="space-y-1">
            {plan.steps.map((step) => (
              <li key={step.id} className="flex gap-2 text-sm">
                <span aria-label={step.status} className="w-4 text-slate-500">
                  {MARKERS[step.status]}
                </span>
                <span className={step.status === "done" ? "text-slate-500" : "text-slate-900"}>
                  {step.intent}
                  {step.risk !== "read" && (
                    <span className="ml-2 rounded bg-amber-100 px-1 text-xs text-amber-900">
                      {step.risk}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ol>
          <h3 className="mt-3 text-xs font-semibold text-slate-600">Success criteria</h3>
          <ul className="list-disc pl-5 text-xs text-slate-600">
            {plan.success_criteria.map((criterion) => (
              <li key={criterion.id}>{criterion.description}</li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
