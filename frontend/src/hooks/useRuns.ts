"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { RunListItem } from "@/types/api";

export function useRuns() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(
    () =>
      api
        .listRuns()
        .then((page) => {
          setRuns(page.items);
          setError(null);
        })
        .catch((caught: unknown) => {
          setError(caught instanceof Error ? caught.message : "Failed to load runs");
        })
        .finally(() => setLoading(false)),
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  return { runs, error, loading, reload: load };
}
