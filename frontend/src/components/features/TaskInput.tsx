"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { EXAMPLE_REQUESTS } from "@/lib/examples";

interface TaskInputProps {
  onSubmit: (request: string) => Promise<void>;
}

export function TaskInput({ onSubmit }: TaskInputProps) {
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(text.trim());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create the task");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card title="What should the operator do?">
      <textarea
        aria-label="Request"
        className="h-28 w-full rounded-md border border-slate-300 p-2 text-sm"
        placeholder="Describe the outcome you need, in plain language."
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      <div className="mt-2 flex flex-wrap gap-2">
        {EXAMPLE_REQUESTS.map((example) => (
          <button
            key={example}
            type="button"
            className="rounded-full border border-slate-200 px-3 py-1 text-left text-xs text-slate-600 hover:bg-slate-50"
            onClick={() => setText(example)}
          >
            {example}
          </button>
        ))}
      </div>
      {error && (
        <div className="mt-3">
          <ErrorState message={error} />
        </div>
      )}
      <div className="mt-3 flex justify-end">
        <Button disabled={submitting || text.trim().length < 3} onClick={() => void submit()}>
          {submitting ? "Submitting…" : "Run"}
        </Button>
      </div>
    </Card>
  );
}
