import type { RunStatus } from "@/types/api";

const COLORS: Record<RunStatus, string> = {
  pending: "bg-slate-100 text-slate-700",
  understanding: "bg-sky-100 text-sky-800",
  planning: "bg-sky-100 text-sky-800",
  executing: "bg-indigo-100 text-indigo-800",
  replanning: "bg-purple-100 text-purple-800",
  awaiting_input: "bg-amber-100 text-amber-900",
  awaiting_approval: "bg-amber-100 text-amber-900",
  verifying: "bg-teal-100 text-teal-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  cancelled: "bg-slate-200 text-slate-700",
};

export function StatusBadge({ status }: { status: RunStatus }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${COLORS[status]}`}>
      {status.replace("_", " ")}
    </span>
  );
}
