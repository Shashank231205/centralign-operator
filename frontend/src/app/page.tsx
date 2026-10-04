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
    <div className="grid gap-16 lg:grid-cols-12">
      <div className="lg:col-span-7">
        <TaskInput onSubmit={submit} />
      </div>
      <aside className="lg:col-span-4 lg:col-start-9">
        <RunList runs={runs} loading={loading} error={error} onRetry={() => void reload()} />
      </aside>
    </div>
  );
}
