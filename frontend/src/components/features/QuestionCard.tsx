"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { ErrorState } from "@/components/ui/ErrorState";
import { TextArea } from "@/components/ui/TextArea";

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
    <Callout label="The operator has a question">
      <p className="font-serif text-lead leading-snug">{question}</p>
      <TextArea
        aria-label="Answer"
        rows={3}
        className="mt-4"
        placeholder="Your answer"
        value={answer}
        onChange={(event) => setAnswer(event.target.value)}
      />
      {error && (
        <div className="mt-3">
          <ErrorState message={error} />
        </div>
      )}
      <div className="mt-4">
        <Button disabled={busy || !answer.trim()} onClick={() => void submit()}>
          Send answer
        </Button>
      </div>
    </Callout>
  );
}
