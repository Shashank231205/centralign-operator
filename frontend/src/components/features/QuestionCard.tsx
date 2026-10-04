"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";

interface QuestionCardProps {
  question: string;
  onAnswer: (answer: string) => Promise<void>;
}

export function QuestionCard({ question, onAnswer }: QuestionCardProps) {
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await onAnswer(answer.trim());
      setAnswer("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not send the answer");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="The operator needs your input" tone="attention">
      <p className="text-sm text-slate-800">{question}</p>
      <textarea
        aria-label="Answer"
        className="mt-2 h-20 w-full rounded border border-slate-300 p-2 text-sm"
        value={answer}
        onChange={(event) => setAnswer(event.target.value)}
      />
      {error && <ErrorState message={error} />}
      <div className="mt-2 flex justify-end">
        <Button disabled={busy || !answer.trim()} onClick={() => void submit()}>
          Send answer
        </Button>
      </div>
    </Card>
  );
}
