import type {
  OperatorTask,
  PromotionCandidate,
  TaskAction,
} from "@/lib/operator-types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class OperatorApiError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message);
    this.name = "OperatorApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = init
    ? await fetch(`${API_BASE}${path}`, init)
    : await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    const detail = await response.text();
    throw new OperatorApiError(
      detail || `Operator API error: ${response.status}`,
      response.status
    );
  }
  return response.json() as Promise<T>;
}

const post = <T>(path: string) =>
  request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });

export const operatorApi = {
  listTasks: () => request<OperatorTask[]>("/api/tasks"),
  transitionTask: (taskId: string, action: TaskAction) =>
    post<OperatorTask>(`/api/tasks/${taskId}/${action}`),
  listCandidates: () =>
    request<PromotionCandidate[]>("/api/adapt/candidates"),
  promoteCandidate: (candidateId: string) =>
    post<PromotionCandidate>(`/api/adapt/candidates/${candidateId}/promote`),
  rollbackCandidate: (candidateId: string) =>
    post<PromotionCandidate>(`/api/adapt/candidates/${candidateId}/rollback`),
};
