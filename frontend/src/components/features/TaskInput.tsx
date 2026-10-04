"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { TextArea } from "@/components/ui/TextArea";
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
    <div>
      <h1 className="font-serif text-display leading-[1.05] tracking-tight">What needs doing?</h1>
      <p className="mt-3 max-w-xl text-lead text-muted">
        Describe the outcome. The operator works out the steps from company procedures, does the
        work in your systems, and verifies it before reporting back.
      </p>
      <TextArea
        aria-label="Request"
        rows={4}
        className="mt-10"
        placeholder="e.g. Record the latest Acme Corp invoice in the ERP"
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      <div className="mt-4 flex items-center justify-between gap-4">
        <span className="font-mono text-label text-faint">{text.trim().length} characters</span>
        <Button disabled={submitting || text.trim().length < 3} onClick={() => void submit()}>
          {submitting ? "Submitting" : "Start"}
        </Button>
      </div>
      {error && (
        <div className="mt-4">
          <ErrorState message={error} />
        </div>
      )}
      <h2 className="mt-14 font-mono text-label uppercase tracking-[0.14em] text-muted">
        Examples
      </h2>
      <ol className="mt-2">
        {EXAMPLE_REQUESTS.map((example, index) => (
          <li key={example} className="border-b border-rule">
            <button
              type="button"
              className="grid w-full grid-cols-[2rem_1fr] py-3 text-left text-ink transition-colors duration-100 hover:text-accent"
              onClick={() => setText(example)}
            >
              <span className="font-mono text-label text-faint">0{index + 1}</span>
              <span>{example}</span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
