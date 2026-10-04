// Mirrors backend/app/api/v1/schemas and domain models.

export type RunStatus =
  | "pending"
  | "understanding"
  | "planning"
  | "executing"
  | "replanning"
  | "awaiting_input"
  | "awaiting_approval"
  | "verifying"
  | "completed"
  | "failed"
  | "cancelled";

export type StepStatus = "pending" | "in_progress" | "done" | "skipped" | "failed";
export type RiskLevel = "read" | "write" | "irreversible";
export type ApprovalDecision = "approve" | "reject" | "approve_with_edits";

export interface Goal {
  intended_outcome: string;
  entities: Record<string, string>;
  target_systems: string[];
  procedure_ids: string[];
  assumptions: string[];
  open_questions: { question: string; blocking: boolean }[];
}

export interface PlanStep {
  id: string;
  intent: string;
  tool_hint: string;
  expected_observation: string;
  risk: RiskLevel;
  status: StepStatus;
}

export interface SuccessCriterion {
  id: string;
  description: string;
  check: Record<string, unknown>;
}

export interface Plan {
  rationale: string;
  steps: PlanStep[];
  success_criteria: SuccessCriterion[];
  version: number;
}

export interface CriterionResult {
  criterion_id: string;
  description: string;
  passed: boolean;
  detail: string;
  observed: Record<string, unknown>;
}

export interface ArtifactRef {
  kind: string;
  path: string;
  description: string;
}

export interface PendingApproval {
  approval_id: string;
  action: { tool: string; args: Record<string, unknown>; rationale: string };
  assessment: {
    risk: RiskLevel;
    system: string | null;
    payload: Record<string, unknown>;
    description: string;
  };
  rule_ids: string[];
  reason: string;
  evidence: ArtifactRef[];
}

export interface RunCounters {
  steps: number;
  replans: number;
  retries: number;
  llm_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
}

export interface RunDetail {
  id: string;
  status: RunStatus;
  request: string;
  goal: Goal | null;
  plan: Plan | null;
  facts: Record<string, string>;
  key_results: Record<string, string>;
  verification: CriterionResult[];
  summary: string | null;
  failure_reason: string | null;
  pending_question: string | null;
  pending_approval: PendingApproval | null;
  counters: RunCounters;
  location: string | null;
  started_at: string;
}

export interface RunListItem {
  id: string;
  status: RunStatus;
  request: string;
  summary: string | null;
  created_at: string;
  updated_at: string;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface RunEvent {
  id: number;
  type: string;
  status: RunStatus;
  message: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface EvidenceItem {
  id: string;
  kind: string;
  description: string;
  created_at: string;
  url: string;
}

export interface TaskAccepted {
  run_id: string;
  status_url: string;
  events_url: string;
  replayed: boolean;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> };
}
