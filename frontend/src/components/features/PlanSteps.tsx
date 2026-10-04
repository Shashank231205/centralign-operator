import { EmptyState } from "@/components/ui/EmptyState";
import { Section } from "@/components/ui/Section";
import type { Plan, StepStatus } from "@/types/api";

const STATUS_LABEL: Record<StepStatus, string> = {
  pending: "todo",
  in_progress: "active",
  done: "done",
  skipped: "skipped",
  failed: "failed",
};

const STATUS_TONE: Record<StepStatus, string> = {
  pending: "text-faint",
  in_progress: "text-accent",
  done: "text-positive",
  skipped: "text-faint",
  failed: "text-negative",
};

export function PlanSteps({ plan }: { plan: Plan | null }) {
  return (
    <Section label={plan ? `Plan, version ${plan.version}` : "Plan"}>
      {!plan && <EmptyState message="The plan appears once the request is understood." />}
      {plan && (
        <>
          <p className="max-w-prose text-muted">{plan.rationale}</p>
          <ol className="mt-4">
            {plan.steps.map((step, index) => (
              <li
                key={step.id}
                className="grid grid-cols-[2rem_1fr_4.5rem] gap-3 border-b border-rule py-2 last:border-0"
              >
                <span className="font-mono text-label leading-6 text-faint">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className={step.status === "done" ? "text-muted" : "text-ink"}>
                  {step.intent}
                  {step.risk !== "read" && (
                    <span className="ml-2 font-mono text-label uppercase text-accent">
                      {step.risk}
                    </span>
                  )}
                </span>
                <span
                  className={`text-right font-mono text-label uppercase leading-6 ${STATUS_TONE[step.status]}`}
                >
                  {STATUS_LABEL[step.status]}
                </span>
              </li>
            ))}
          </ol>
          <h3 className="mt-6 font-mono text-label uppercase tracking-[0.14em] text-muted">
            Done means
          </h3>
          <ul className="mt-2 space-y-1">
            {plan.success_criteria.map((criterion) => (
              <li key={criterion.id} className="text-muted">
                {criterion.description}
              </li>
            ))}
          </ul>
        </>
      )}
    </Section>
  );
}
