"use client";

import { useRouter } from "next/navigation";

import { RunList } from "@/components/features/RunList";
import { TaskInput } from "@/components/features/TaskInput";
import { useRuns } from "@/hooks/useRuns";
import { api } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  const { runs, loading, error, reload } = useRuns();

  async function submit(request: string) {
    // One key per click: a double-submit or network retry maps to the same run.
    const accepted = await api.createTask(request, crypto.randomUUID());
    router.push(`/runs/${accepted.run_id}`);
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
      <TaskInput onSubmit={submit} />
      <RunList runs={runs} loading={loading} error={error} onRetry={() => void reload()} />
    </div>
  );
}
