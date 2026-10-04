"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, eventsUrl } from "@/lib/api";
import type { EvidenceItem, RunDetail, RunEvent } from "@/types/api";

// Events arrive in bursts (one step emits several); coalesce detail refreshes.
const REFRESH_DEBOUNCE_MS = 400;

export interface RunView {
  run: RunDetail | null;
  events: RunEvent[];
  evidence: EvidenceItem[];
  error: string | null;
  loading: boolean;
  connected: boolean;
  refresh: () => Promise<void>;
}

export function useRun(runId: string): RunView {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(
    () =>
      Promise.all([api.getRun(runId), api.listEvidence(runId)])
        .then(([detail, items]) => {
          setRun(detail);
          setEvidence(items);
          setError(null);
        })
        .catch((caught: unknown) => {
          setError(caught instanceof Error ? caught.message : "Failed to load run");
        })
        .finally(() => setLoading(false)),
    [runId],
  );

  useEffect(() => {
    void refresh();
    const source = new EventSource(eventsUrl(runId));
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.addEventListener("run_event", (message) => {
      const event = JSON.parse((message as MessageEvent<string>).data) as RunEvent;
      setEvents((previous) =>
        previous.some((existing) => existing.id === event.id) ? previous : [...previous, event],
      );
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => void refresh(), REFRESH_DEBOUNCE_MS);
    });
    return () => {
      source.close();
      if (timer.current) clearTimeout(timer.current);
    };
  }, [runId, refresh]);

  return { run, events, evidence, error, loading, connected, refresh };
}
