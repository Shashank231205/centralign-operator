import { EmptyState } from "@/components/ui/EmptyState";
import { Section } from "@/components/ui/Section";
import type { RunEvent } from "@/types/api";

// Tone follows meaning: humans needed, recovery, outcome. Everything else stays ink.
const TONE: Record<string, string> = {
  approval_requested: "text-pending",
  input_requested: "text-pending",
  action_retried: "text-accent",
  plan_revised: "text-accent",
  policy_blocked: "text-negative",
  run_failed: "text-negative",
  idempotent_skip: "text-positive",
  run_completed: "text-positive",
};

export function EventTimeline({ events, connected }: { events: RunEvent[]; connected: boolean }) {
  return (
    <Section
      label="Timeline"
      aside={
        <span
          className={`font-mono text-label uppercase tracking-[0.14em] ${connected ? "text-positive" : "text-faint"}`}
        >
          {connected ? "Live" : "Reconnecting"}
        </span>
      }
    >
      {events.length === 0 && <EmptyState message="Waiting for the first event." />}
      <ol className="max-h-[36rem] overflow-y-auto">
        {events.map((event) => (
          <li
            key={event.id}
            className="grid grid-cols-[4.5rem_1fr] gap-3 border-b border-rule py-2 last:border-0"
          >
            <time className="font-mono text-label leading-6 text-faint" dateTime={event.created_at}>
              {new Date(event.created_at).toLocaleTimeString([], { hour12: false })}
            </time>
            <div>
              <span className="font-mono text-label uppercase tracking-[0.08em] text-faint">
                {event.type.replaceAll("_", " ")}
              </span>
              <p className={`break-words ${TONE[event.type] ?? "text-ink"}`}>{event.message}</p>
            </div>
          </li>
        ))}
      </ol>
    </Section>
  );
}
