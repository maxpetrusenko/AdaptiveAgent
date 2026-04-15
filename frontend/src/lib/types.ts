export interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  tool_calls?: ToolCall[];
  created_at: string;
}

export interface ToolCall {
  id: string;
  name: string;
  input: Record<string, unknown>;
  output?: string;
  is_error?: boolean;
}

export interface EvalCase {
  id: string;
  name: string;
  input: string;
  expected_output: string;
  tags: string[];
  source: "manual" | "generated";
  created_at: string;
}

export interface EvalRun {
  id: string;
  prompt_version_id: string;
  started_at: string;
  completed_at?: string;
  status: "running" | "completed" | "failed";
  pass_rate?: number;
  total: number;
  passed: number;
  failed: number;
}

export interface EvalResult {
  id: string;
  eval_run_id: string;
  eval_case_id: string;
  status: "pass" | "fail" | "error";
  actual_output: string;
  score?: number;
  error?: string;
  latency_ms: number;
}

export interface PromptVersion {
  id: string;
  version: number;
  content: string;
  parent_id?: string;
  created_at: string;
  is_active: boolean;
  change_reason?: string;
}

export interface AdaptationRun {
  id: string;
  started_at: string;
  completed_at?: string;
  status: "running" | "completed" | "failed" | "rejected";
  before_version_id: string;
  after_version_id?: string;
  before_pass_rate: number;
  after_pass_rate?: number;
  accepted: boolean;
}

export interface DashboardMetrics {
  pass_rate: number | null;
  hallucination_rate: number | null;
  avg_cost: number | null;
  total_eval_cases: number;
  total_eval_runs: number;
  total_adaptations: number;
  consistency_score: number | null;
  recent_runs: {
    date: string;
    pass_rate: number;
    total: number;
    passed: number;
    failed: number;
  }[];
}
