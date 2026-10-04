import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { RunEvent } from "@/types/api";

const HIGHLIGHT: Record<string, string> = {
  action_retried: "text-amber-700",
  policy_blocked: "text-red-700",
  approval_requested: "text-amber-800 font-medium",
  input_requested: "text-amber-800 font-medium",
  idempotent_skip: "text-teal-700",
  plan_revised: "text-purple-700",
  run_failed: "text-red-700 font-medium",
  run_completed: "text-green-700 font-medium",
  memory_written: "text-sky-700",
};

export function EventTimeline({ events, connected }: { events: RunEvent[]; connected: boolean }) {
  return (
    <Card
      title="Timeline"
      actions={
        <span className={`text-xs ${connected ? "text-green-700" : "text-slate-400"}`}>
          {connected ? "● live" : "○ reconnecting"}
        </span>
      }
    >
      {events.length === 0 && <EmptyState message="Waiting for the first event…" />}
      <ol className="max-h-[32rem] space-y-1 overflow-y-auto font-mono text-xs">
        {events.map((event) => (
          <li key={event.id} className={HIGHLIGHT[event.type] ?? "text-slate-700"}>
            <span className="text-slate-400">
              {new Date(event.created_at).toLocaleTimeString()}{" "}
            </span>
            <span className="text-slate-500">[{event.type}]</span> {event.message}
          </li>
        ))}
      </ol>
    </Card>
  );
}
