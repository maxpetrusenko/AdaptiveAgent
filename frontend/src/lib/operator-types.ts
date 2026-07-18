export type TaskStatus =
  | "active"
  | "paused"
  | "completed"
  | "cancelled"
  | "escalated"
  | "replan_required";

export type TaskAction = "pause" | "resume" | "cancel";

export interface TaskEvidence {
  summary: string;
  artifact_ref: string | null;
  digest: string | null;
  source: string;
  verifier: string;
  status: "unverified" | "verified";
  recorded_at: string;
}

export interface TaskCriterion {
  id: string;
  description: string;
  evidence: TaskEvidence[];
}

export interface TaskStep {
  id: string;
  title: string;
  status: "pending" | "active" | "completed";
}

export interface OperatorTask {
  id: string;
  goal: string;
  constraints: string[];
  acceptance_criteria: TaskCriterion[];
  steps: TaskStep[];
  status: TaskStatus;
  plan_version: number;
  current_step_index: number;
  stall_count: number;
  stall_threshold: number;
  action_budget: number;
  actions_used: number;
  replan_reason: string | null;
  escalation_reason: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  checkpoint: {
    sequence: number;
    operation: string;
    idempotency_key: string | null;
    updated_at: string;
  };
}

export interface EvaluationResult {
  baseline: number;
  candidate: number;
}

export interface PromotionCandidate {
  id: string;
  title: string;
  status: "ready" | "promoted" | "rejected" | "rolled_back";
  parent_hash: string;
  candidate_hash: string;
  rationale: string;
  decision: "promote" | "reject";
  results: {
    training: EvaluationResult;
    validation: EvaluationResult;
    protected: EvaluationResult;
  };
  lower_confidence_bound: number;
  latency_ratio: number;
  cost_ratio: number;
  mutations: {
    kind: string;
    target: string;
    summary: string;
  }[];
}
