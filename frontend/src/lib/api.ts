import type {
  ApiErrorBody,
  ApprovalDecision,
  EvidenceItem,
  Page,
  RunDetail,
  RunListItem,
  TaskAccepted,
} from "@/types/api";

export const API_BASE = "/api/operator";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(
      response.status,
      body?.error.code ?? "http_error",
      body?.error.message ?? `Request failed (${response.status})`,
    );
  }
  return (await response.json()) as T;
}

export const api = {
  createTask: (text: string, idempotencyKey: string) =>
    request<TaskAccepted>("/tasks", {
      method: "POST",
      body: JSON.stringify({ request: text }),
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  listRuns: () => request<Page<RunListItem>>("/runs?limit=20"),
  getRun: (runId: string) => request<RunDetail>(`/runs/${runId}`),
  listEvidence: (runId: string) => request<EvidenceItem[]>(`/runs/${runId}/evidence`),
  answer: (runId: string, answer: string) =>
    request<RunDetail>(`/runs/${runId}/input`, {
      method: "POST",
      body: JSON.stringify({ answer }),
    }),
  cancel: (runId: string) => request<RunDetail>(`/runs/${runId}/cancel`, { method: "POST" }),
  resolveApproval: (
    approvalId: string,
    decision: ApprovalDecision,
    comment: string,
    editedPayload: Record<string, string> | null,
  ) =>
    request<RunDetail>(`/approvals/${approvalId}`, {
      method: "POST",
      body: JSON.stringify({ decision, comment, edited_payload: editedPayload }),
    }),
};

export function eventsUrl(runId: string): string {
  return `${API_BASE}/runs/${runId}/events`;
}

export function evidenceFileUrl(item: EvidenceItem): string {
  // Evidence URLs are relative to the API root, which the proxy mounts at API_BASE.
  return `${API_BASE}${item.url}`;
}
