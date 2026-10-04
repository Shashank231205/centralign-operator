import type { RunStatus } from "@/types/api";

// Colour encodes state family only: in progress, needs a human, done, failed.
const TONE: Record<RunStatus, string> = {
  pending: "text-muted",
  understanding: "text-ink",
  planning: "text-ink",
  executing: "text-ink",
  replanning: "text-ink",
  verifying: "text-ink",
  awaiting_input: "text-pending",
  awaiting_approval: "text-pending",
  completed: "text-positive",
  failed: "text-negative",
  cancelled: "text-muted",
};

export function StatusText({ status }: { status: RunStatus }) {
  return (
    <span className={`font-mono text-label uppercase tracking-[0.14em] ${TONE[status]}`}>
      {status.replace("_", " ")}
    </span>
  );
}
