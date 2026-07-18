export interface ProofSource {
  externalId: string;
  title: string;
  text: string;
}

export interface IngestSourceInput {
  tenantId: string;
  externalId: string;
  text: string;
}

export interface IndexMutation {
  generation_id: string;
  source_id: string;
  index_version: string;
  changed: boolean;
  chunk_count: number;
}

export interface IndexHealth {
  status: string;
  active_generation_id: string | null;
  active_index_version: string | null;
  building_count: number;
  chunk_count: number;
}

export interface KnowledgeHit {
  tenant_id: string;
  source_id: string;
  chunk_id: string;
  citation_id: string;
  content_hash: string;
  text: string;
  fusion_score: number;
  dense_score: number;
  lexical_score: number;
  dense_rank: number | null;
  lexical_rank: number | null;
  index_version: string;
  embedding_fingerprint: string;
}

export interface KnowledgeSearchResponse {
  hits: KnowledgeHit[];
}

export type ResearchStepName = "plan" | "retrieve" | "synthesize" | "verify";
export type ResearchStepStatus = "pending" | "active" | "completed";
export type ResearchRunStatus =
  | "active"
  | "completed"
  | "replan_required"
  | "escalated";

export interface ResearchStep {
  name: ResearchStepName;
  status: ResearchStepStatus;
  attempt: number;
}

export interface ResearchRun {
  id: string;
  goal: string;
  execution_mode: ResearchMode;
  adapter_fingerprint: string;
  steps: ResearchStep[];
  status: ResearchRunStatus;
  cursor: number;
  version: number;
  plan_version: number;
  action_budget: number;
  actions_used: number;
  terminal_reason: string | null;
  artifacts: {
    plan: { queries: string[] } | null;
    retrieval: Array<{
      citation_id: string | null;
      text: string;
      source_id?: string | null;
      content_hash?: string | null;
      fusion_score?: number | null;
      dense_score?: number | null;
      lexical_score?: number | null;
      dense_rank?: number | null;
      lexical_rank?: number | null;
      index_version?: string | null;
      embedding_fingerprint?: string | null;
    }>;
    synthesis: { answer: string; citation_ids: string[] } | null;
    verification: {
      passed: boolean;
      evidence_citation_ids: string[];
      reason: string;
    } | null;
  };
}

export interface CreateResearchRunInput {
  runId: string;
  goal: string;
  actionBudget: number;
  mode: ResearchMode;
}

export interface ExecuteResearchRunInput {
  workerId: string;
  injectCrashAfter?: "retrieve";
  mode: ResearchMode;
}

export type ResearchMode = "deterministic" | "live";

export interface ProofCrashDetail {
  message: string;
  step: "retrieve";
  effect_key: string;
}

export type ProofStage =
  | "loading"
  | "empty"
  | "ready"
  | "ingesting"
  | "running"
  | "crashed"
  | "resuming"
  | "completed"
  | "offline"
  | "unauthorized"
  | "error";
